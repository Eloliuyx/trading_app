# backend/core/export_universe.py
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

"""
============================================================
Trading_App universe 导出脚本（F1-F6 精简版）
============================================================

目标：
- 从本地 CSV 日线数据构建 universe.json；
- 与前端当前使用的字段保持一致，仅输出所需字段：

    F1: 剔除 ST（由 is_st 提供信息，由上层使用）
    F2: 强流动性           -> pass_liquidity_v2
    F3: 合理价格区间       -> pass_price_compliance
    F4: 放量确认           -> pass_volume_confirm
    F5: 多头趋势结构       -> pass_trend
    F6: 强板块龙头         -> pass_industry_leader

约定（非常重要）：
- CSV 来自 update_data.py（TuShare）且已标准化，包含：
    Date, Open, High, Low, Close, Volume, Amount, TurnoverRate
- Volume 单位：手
- Amount 单位：元（已在 update_data.py 中将 tushare.amount(千元) * 1000，
                  并在缺失时用 Volume * Close * 100 近似补齐）
- 本脚本不再处理单位换算和缺失补齐，若关键数据缺失则该标的 fail-closed。
- features 字段用于前端展示与调试。
"""

# ------------------------------------------------------------
# 路径约定：仅使用 repo 根目录下的 public
# ------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]  # .../backend
PUBLIC_CANDIDATE = ROOT.parent / "public"


def pick_public() -> Path:
    """
    选择实际使用的 PUBLIC 目录：
    - 使用 repo 根目录下的 public
    - 要求存在 data/metadata/symbols.csv
    """
    meta = PUBLIC_CANDIDATE / "data" / "metadata" / "symbols.csv"
    if meta.exists():
        print(f"[export_universe] using PUBLIC dir: {PUBLIC_CANDIDATE}")
        return PUBLIC_CANDIDATE
    raise FileNotFoundError("symbols.csv not found under public")


PUBLIC = pick_public()
DATA = PUBLIC / "data"
META = PUBLIC / "data" / "metadata" / "symbols.csv"
OUT = PUBLIC / "out" / "universe.json"


# ============================================================
# 工具函数
# ============================================================

def nz(x: Any, default: float = 0.0) -> float:
    """
    安全取浮点数：
    - None / NaN / inf -> default
    - 其他尽量转为 float
    """
    try:
        if x is None:
            return default
        if isinstance(x, (np.floating, float)):
            v = float(x)
            if math.isnan(v) or math.isinf(v):
                return default
            return v
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default


def percent_rank(s: pd.Series) -> pd.Series:
    """
    分位数（0~1）：
    - 用于量能强度、行业强度等相对排序；
    - 缺失视为 0。
    """
    s = pd.to_numeric(s, errors="coerce")
    return s.rank(pct=True, method="average").fillna(0.0)


def ma(series: pd.Series, n: int) -> pd.Series:
    """简单移动平均，min_periods=n，样本不足视为 NaN。"""
    return pd.to_numeric(series, errors="coerce").rolling(n, min_periods=n).mean()


def read_symbols(meta_path: Path) -> pd.DataFrame:
    """
    读取标的信息（symbols.csv）并标准化字段：
    - symbol, name, industry, market
    - is_st: 名称包含 "ST"
    - float_shares: 若存在相关列则读入，否则为 NaN
    """
    df = pd.read_csv(meta_path)
    cols = {c.lower(): c for c in df.columns}

    def pick(*names: str, default: Optional[str] = None) -> str:
        for n in names:
            col = cols.get(n.lower())
            if col:
                return col
        if default is not None:
            return default
        raise KeyError(f"Missing required column among: {names}")

    sym_col = pick("symbol", "ts_code", "code")
    name_col = pick("name", "security_name", "sec_name", default="name")
    ind_col = pick("industry", "industry_name", default="industry")
    mkt_col = pick("market", "exchange", default="market")

    out = pd.DataFrame()
    out["symbol"] = df[sym_col].astype(str)
    out["name"] = df[name_col].astype(str)
    out["industry"] = df.get(ind_col, "未分类").fillna("未分类").astype(str)
    out["market"] = df.get(mkt_col, "未知").fillna("未知").astype(str)

    # F1: ST 判定（仅根据名称包含 "ST"）
    upper_name = out["name"].str.upper()
    out["is_st"] = upper_name.str.contains("ST")

    # 流通股本（若存在）
    float_cols = [
        "float_shares",
        "float_share",
        "free_float_shares",
        "free_float",
        "total_share",
        "totals",
    ]
    float_col = None
    for c in float_cols:
        if c in cols:
            float_col = cols[c]
            break
    if float_col:
        out["float_shares"] = pd.to_numeric(df[float_col], errors="coerce")
    else:
        out["float_shares"] = np.nan

    return out


def sanitize_for_json(obj: Any) -> Any:
    """
    确保输出 JSON 可被前端安全解析：
    - NaN/inf -> None
    - numpy 标量 -> Python 标量
    """
    if isinstance(obj, (bool, np.bool_)):
        return bool(obj)

    if isinstance(obj, (float, np.floating)):
        v = float(obj)
        if math.isnan(v) or math.isinf(v):
            return None
        return v

    if isinstance(obj, (int, np.integer)):
        return int(obj)

    if obj is None:
        return None

    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}

    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(v) for v in obj]

    return obj


# ============================================================
# 单股票数据载入 & 特征计算
# ============================================================

def load_one(symbol: str, cutoff: Optional[str]) -> Optional[pd.DataFrame]:
    """
    读取单个 symbol 的日线 CSV，并计算技术指标。

    依赖前置条件：
    - CSV 已由 update_data.py 规范化：
        Date, Open, High, Low, Close, Volume, Amount(元), TurnoverRate
    - 若关键数据严重缺失，则返回 None（fail-closed）。

    计算：
    - MA5 / MA13 / MA39
    - VMA10 / VMA20 / VMA50
    - VR（VMA10 / VMA50）
    - VOL_RATIO20（今日量 / VMA20）
    - AMT60（60日均成交额，基于 Amount，单位：元）
    - RS20（20日相对强度）
    - HIGH20 / LOW20（20日高低）
    - ATR14
    """
    path = DATA / f"{symbol}.csv"
    if not path.exists():
        return None

    df = pd.read_csv(path)

    required = ["Date", "Close", "Volume", "Amount"]
    if any(c not in df.columns for c in required):
        return None

    # 日期 & 截止
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date")
    if cutoff:
        df = df[df["Date"] <= cutoff]

    # 转数值
    for c in ["Open", "High", "Low", "Close", "Volume", "Amount"]:
        if c in df.columns and df[c].dtype == "object":
            df[c] = (
                df[c]
                .astype(str)
                .str.replace(",", "", regex=False)
                .str.replace(" ", "", regex=False)
            )
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # TurnoverRate（如存在，视为小数；否则 NaN）
    if "TurnoverRate" in df.columns:
        df["TurnoverRate"] = pd.to_numeric(df["TurnoverRate"], errors="coerce")
    else:
        df["TurnoverRate"] = np.nan

    # 样本不足 60 日，不纳入本次 universe
    if len(df) < 60:
        return None

    # 成交额（元），此处假定 update_data.py 已确保为“元”且大部分存在。
    df["AmountY"] = pd.to_numeric(df["Amount"], errors="coerce")

    # 若整条时间序列的 AmountY 全为 NaN 或非正数，则视为数据不可信，fail-closed
    if df["AmountY"].isna().all() or (df["AmountY"] <= 0).all():
        print(f"[warn] {symbol}: invalid Amount series, skip in universe")
        return None

    # 均线
    df["MA5"] = ma(df["Close"], 5)
    df["MA13"] = ma(df["Close"], 13)
    df["MA39"] = ma(df["Close"], 39)

    # 量能相关
    df["VMA10"] = ma(df["Volume"], 10)
    df["VMA20"] = ma(df["Volume"], 20)
    df["VMA50"] = ma(df["Volume"], 50)
    df["VR"] = df["VMA10"] / df["VMA50"]
    df["VOL_RATIO20"] = df["Volume"] / df["VMA20"]

    # 60日均成交额（元）
    df["AMT60"] = ma(df["AmountY"], 60)

    # RS20：20日相对强度
    df["RS20"] = df["Close"] / df["Close"].shift(20) - 1.0

    # 20日高低
    df["HIGH20"] = df["High"].rolling(20, min_periods=20).max()
    df["LOW20"] = df["Low"].rolling(20, min_periods=20).min()

    # ATR14：波动率参考
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["ATR14"] = tr.rolling(14, min_periods=14).mean()

    return df


# ============================================================
# 主流程：构建 universe.json
# ============================================================

def main(cutoff: Optional[str]) -> None:
    print(f"[export_universe] DATA={DATA}")
    print(f"[export_universe] META={META}")
    print(f"[export_universe] OUT ={OUT}")
    print(f"[export_universe] CSV count: {len(list(DATA.glob('*.csv')))}")

    base = read_symbols(META)

    rows: List[Dict[str, Any]] = []
    last_dates: List[str] = []

    # ---------- 首轮遍历：逐股计算单票特征 ----------
    for _, r in base.iterrows():
        sym = str(r["symbol"])
        df = load_one(sym, cutoff)
        if df is None or df.empty:
            continue

        last = df.iloc[-1]
        last_dates.append(str(last["Date"].date()))

        # 基础价量
        close = nz(last["Close"])
        prev_close = nz(df["Close"].iloc[-2]) if len(df) >= 2 else close
        amount_t = nz(last["AmountY"])
        amt60 = nz(last["AMT60"])
        volume = nz(last["Volume"])

        # 均线 & 趋势
        ma5 = nz(last["MA5"], 0.0)
        ma13 = nz(last["MA13"], 0.0)
        ma39 = nz(last["MA39"], 0.0)
        ma5_shift_5 = nz(df["MA5"].shift(5).iloc[-1], 0.0)

        # RS & 波动
        rs20 = nz(last["RS20"], 0.0)
        high20 = nz(last["HIGH20"], 0.0)
        low20 = nz(last["LOW20"], 0.0)
        atr14 = nz(last["ATR14"], 0.0)

        # 量能相关
        vma20 = nz(last["VMA20"], 0.0)
        vol_ratio20 = nz(last["VOL_RATIO20"], 0.0)
        vr = nz(last["VR"], 0.0)

        # 元信息
        is_st = bool(r.get("is_st", False))
        float_shares = r.get("float_shares", np.nan)
        if isinstance(float_shares, (str, bytes)):
            try:
                float_shares = float(float_shares)
            except Exception:
                float_shares = np.nan
        float_shares = float(float_shares) if not (pd.isna(float_shares)) else None

        # TurnoverRate 时间序列（如存在）
        if "TurnoverRate" in df.columns:
            tr_all = pd.to_numeric(df["TurnoverRate"], errors="coerce")
        else:
            tr_all = pd.Series(dtype=float)

        turnover_d = float("nan")
        turnover60_avg = float("nan")

        # 只在最近 180 日中有足够样本时使用换手率
        if not tr_all.empty:
            last_tr_raw = tr_all.iloc[-1]
            last_tr = float(last_tr_raw) if not math.isnan(float(last_tr_raw)) else float("nan")
            if not math.isnan(last_tr):
                recent = tr_all.tail(180)
                valid_recent = recent[recent.notna()]
                if len(valid_recent) >= 60:
                    turnover_d = last_tr
                    turnover60_avg = float(valid_recent.tail(60).mean())

        # ---------- F2: 强流动性 ----------
        def pass_liquidity_v2_func() -> bool:
            """
            强流动性条件（全部使用“元”口径）：
            - 60日均成交额 >= 5000 万元
            - 60日均换手率 >= 0.8%（0.008）
            - 当日换手率 >= 0.6%（0.006）
            条件任一缺失 -> False
            """
            if amt60 < 50_000_000:
                return False
            if not (isinstance(turnover60_avg, (int, float)) and isinstance(turnover_d, (int, float))):
                return False
            if math.isnan(turnover60_avg) or math.isnan(turnover_d):
                return False
            if turnover60_avg < 0.008:
                return False
            if turnover_d < 0.006:
                return False
            return True

        pass_liquidity_v2 = pass_liquidity_v2_func()

        # ---------- F3: 合理价格区间 ----------
        pass_price_compliance = 3.0 <= close <= 80.0

        # ---------- F5: 多头趋势结构 ----------
        def pass_trend_func() -> bool:
            """
            F5 多头趋势结构：
            - 多头排列: MA5 >= MA13 >= MA39
            - Close > MA13
            - MA5 相比 5 日前抬升至少 1.5%
            - 所有参与判断的值必须有效
            """
            vals = [ma5, ma13, ma39, ma5_shift_5, close]
            for v in vals:
                if not isinstance(v, (int, float)):
                    return False
                if math.isnan(v):
                    return False

            if not (ma5 >= ma13 >= ma39):
                return False
            if not (close > ma13):
                return False
            if ma5_shift_5 == 0:
                return False

            return (ma5 - ma5_shift_5) / ma5_shift_5 >= 0.015

        pass_trend = pass_trend_func()

        # 收盘价不低于前一日（用于 F4 放量确认）
        price_ok = close >= prev_close

        # features：承载数值指标 + 中间结果（供前端展示/调试）
        row_features: Dict[str, Any] = {
            "close": close,
            "amount_t": amount_t,
            "amt60_avg": amt60,
            "volume": volume,
            "ma5": ma5,
            "ma13": ma13,
            "ma39": ma39,
            "ma5_shift_5": ma5_shift_5,
            "rs20_raw": rs20,
            "vr": vr,
            "vol_ratio20": vol_ratio20,
            "vma20": vma20,
            "high20": high20,
            "low20": low20,
            "atr14": atr14,
            "turnover_d": turnover_d,
            "turnover60_avg": turnover60_avg,
            "price_ok": bool(price_ok),
        }

        rows.append(
            {
                "symbol": sym,
                "name": str(r["name"]),
                "industry": str(r["industry"]),
                "market": str(r["market"]),
                "is_st": is_st,
                "float_shares": float_shares if float_shares and float_shares > 0 else None,
                "last_date": str(last["Date"].date()),
                "amt60_avg": amt60,
                # F2/F3/F5 顶层布尔字段（前端直接读取）
                "pass_liquidity_v2": bool(pass_liquidity_v2),
                "pass_price_compliance": bool(pass_price_compliance),
                "pass_trend": bool(pass_trend),
                "features": row_features,
            }
        )

    if not rows:
        raise RuntimeError("没有可用标的（CSV 太短或关键列缺失）")

    # ---------- 二次遍历：基于全市场 & 行业的衍生特征（F4, F6） ----------
    dfu = pd.DataFrame(
        [
            {
                "symbol": it["symbol"],
                "industry": it["industry"],
                **(it.get("features") or {}),
                "pass_liquidity_v2": it.get("pass_liquidity_v2", False),
                "pass_price_compliance": it.get("pass_price_compliance", False),
                "pass_trend": it.get("pass_trend", False),
            }
            for it in rows
        ]
    )

    # 全市场分位：量能 & 相对强度
    dfu["pct_amt"] = percent_rank(dfu["amount_t"])
    base_vr = dfu["vol_ratio20"]
    if base_vr.isna().all():
        base_vr = dfu["vr"]
    dfu["pct_vr"] = percent_rank(base_vr)
    dfu["pct_rs20"] = percent_rank(dfu["rs20_raw"])

    # ---------- F4: 放量确认 ----------
    # 条件：
    #   1) 量能进入全市场前 40%: pct_vr >= 0.6
    #      或 自身放量明显: vol_ratio20 >= 1.2
    #   2) 且 price_ok（收盘价不低于前一日）
    dfu["volume_boost"] = (dfu["pct_vr"] >= 0.6) | (dfu["vol_ratio20"] >= 1.2)
    dfu["pass_volume_confirm"] = dfu["volume_boost"] & dfu["price_ok"].fillna(False)

    # ---------- F6: 强板块龙头 ----------
    # 行业强度（RS20 中位数）
    ind_strength = (
        dfu.groupby("industry", as_index=False)["rs20_raw"]
        .median()
        .rename(columns={"rs20_raw": "industry_rs20"})
    )
    # 行业在全市场的强度分位（0~1）
    ind_strength["industry_rs20_pct"] = percent_rank(ind_strength["industry_rs20"])
    dfu = dfu.merge(ind_strength, on="industry", how="left")

    # 个股在本行业按 RS20 排名（1 = 最强）
    dfu["rank_in_industry_by_rs20"] = (
        dfu.groupby("industry")["rs20_raw"]
        .rank(ascending=False, method="min")
        .astype(float)
    )
    dfu["industry_size"] = dfu.groupby("industry")["symbol"].transform("count")

    # 强板块：行业 RS20 分位 >= 0.6（前 40%）
    dfu["strong_industry"] = dfu["industry_rs20_pct"] >= 0.6

    # 龙头股：行业内部 RS20 排名 <= min(5, 行业个数)
    dfu["leader_in_industry"] = dfu["rank_in_industry_by_rs20"] <= dfu[
        "industry_size"
    ].clip(upper=5)

    # F6: 强板块龙头
    dfu["pass_industry_leader"] = dfu["strong_industry"] & dfu["leader_in_industry"]

    # ---------- 回写到 rows：仅写入当前版本需要的字段 ----------
    dfu = dfu.set_index("symbol")
    for it in rows:
        sym = it["symbol"]
        if sym not in dfu.index:
            continue
        row = dfu.loc[sym]
        feat = it.get("features") or {}

        # 数值特征回写到 features（便于前端展示/调试）
        for k in [
            "pct_amt",
            "pct_vr",
            "pct_rs20",
            "industry_rs20",
            "industry_rs20_pct",
            "rank_in_industry_by_rs20",
            "industry_size",
            "volume_boost",
            "strong_industry",
            "leader_in_industry",
        ]:
            v = row.get(k)
            if isinstance(v, (int, float)) and not math.isnan(float(v)):
                feat[k] = float(v)
            elif isinstance(v, (bool, np.bool_)):
                feat[k] = bool(v)

        # F4 / F6 布尔信号写回顶层 & features
        for fld in ["pass_volume_confirm", "pass_industry_leader"]:
            val = bool(row.get(fld, False))
            it[fld] = val
            feat[fld] = val

        it["features"] = feat

    # ---------- asof 选择：使用 last_date 众数 ----------
    try:
        asof = pd.Series(last_dates).mode().iloc[0]
    except Exception:
        asof = ""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"asof": asof, "list": rows}
    payload = sanitize_for_json(payload)

    with OUT.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, allow_nan=False)

    print(f"[export_universe] wrote {len(rows)} items -> {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--date",
        dest="cutoff",
        help="YYYY-MM-DD，回测到此日期（含）",
        default=None,
    )
    args = ap.parse_args()
    main(args.cutoff)
