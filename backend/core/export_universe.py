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
Trading_App universe 导出脚本（F1-F6 专用版本）
============================================================

目标：
- 从本地 CSV 日线数据构建 universe.json；
- 只输出与当前前端版本一致的关键信息：
    F1: 剔除风险股/ST          -> is_st (由前端规则使用)
    F2: 强流动性               -> pass_liquidity_v2
    F3: 合理价格区间           -> pass_price_compliance
    F4: 放量确认               -> pass_volume_confirm
    F5: 多头趋势结构           -> pass_trend
    F6: 强板块龙头             -> pass_industry_leader
- 其他数值指标作为 features 提供给前端展示 / debug 使用；
- 不再输出 F7-F9、pass_rs_market_strong 等未使用字段；
- 缺数据一律 fail-closed，保持确定性与可解释性。
"""

ROOT = Path(__file__).resolve().parents[1]  # .../backend
CANDIDATES = [
    ROOT.parent / "frontend" / "public",
    ROOT.parent / "public",
]


def pick_public() -> Path:
    """
    选择实际使用的 PUBLIC 目录：
    - 优先 frontend/public
    - 其次 repo 根目录下的 public
    - 要求存在 data/metadata/symbols.csv
    """
    for p in CANDIDATES:
        meta = p / "data" / "metadata" / "symbols.csv"
        if meta.exists():
            print(f"[export_universe] using PUBLIC dir: {p}")
            return p
    raise FileNotFoundError(
        "symbols.csv not found under frontend/public or public"
    )


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
    - is_delisting, is_suspended: 如存在则读取，否则 False
    - float_shares: 流通股本（若存在相应列）
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

    # 退市 & 停牌标记（非 F1-F6 必要，但保留供前端展示）
    if "is_delisting" in cols:
        out["is_delisting"] = df[cols["is_delisting"]].astype(bool)
    else:
        out["is_delisting"] = False

    if "is_suspended" in cols:
        out["is_suspended"] = df[cols["is_suspended"]].astype(bool)
    else:
        out["is_suspended"] = False

    # 流通股本（预留给换手率等计算。当前 F2 主要使用 TurnoverRate）
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


# ============================================================
# 成交额推断（用于 F2 / 量能相关）
# ============================================================

AMOUNT_CANDIDATES = ["Amount", "amount", "成交额", "成交额(元)", "Turnover", "turnover"]


def parse_amount_if_exists(df: pd.DataFrame) -> Optional[pd.Series]:
    """
    若存在成交额列：
    - 清洗千分位符号；
    - 判断单位（若整体偏小则视为“千元”，乘以1000）；
    - 返回统一到「元」的 Series。
    """
    col = None
    for c in AMOUNT_CANDIDATES:
        if c in df.columns:
            col = c
            break
    if col is None:
        return None

    raw = (
        df[col]
        .astype(str)
        .str.replace(",", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace("\u00a0", "", regex=False)
    )
    amt = pd.to_numeric(raw, errors="coerce")

    if not amt.notna().any():
        return None

    # 若 95 分位 < 1e9，视为“千元”为单位 → 乘以 1000
    q95 = np.nanpercentile(amt.to_numpy(dtype=float), 95)
    if q95 < 1e9:
        amt = amt * 1_000.0

    return amt


def infer_amount_from_cv(df: pd.DataFrame) -> pd.Series:
    """
    无成交额列时，使用 Close × Volume 估算成交额（粗略）：
    - 优先假设 Volume 为“手”，不合理时退回为“股”。
    """
    for c in ["Close", "Volume"]:
        if df[c].dtype == "object":
            df[c] = (
                df[c]
                .astype(str)
                .str.replace(",", "", regex=False)
                .str.replace(" ", "", regex=False)
            )
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # 初始假设 Volume 为“手”：元 ≈ Close × Volume × 100
    est = df["Close"] * df["Volume"] * 100.0

    q95_amt = np.nanpercentile(est.to_numpy(dtype=float), 95) if est.notna().any() else 0.0
    q95_vol = (
        np.nanpercentile(df["Volume"].to_numpy(dtype=float), 95)
        if df["Volume"].notna().any()
        else 0.0
    )

    # 若估算过大，尝试假设 Volume 已是“股”
    if q95_amt > 1e11 or q95_vol > 1e9:
        est = df["Close"] * df["Volume"] * 1.0

    return pd.to_numeric(est, errors="coerce")


# ============================================================
# 单股票数据载入 & 特征计算
# ============================================================

def load_one(symbol: str, cutoff: Optional[str]) -> Optional[pd.DataFrame]:
    """
    读取单个 symbol 的日线 CSV，并计算：
    - MA5 / MA13 / MA39
    - VMA10 / VMA20 / VMA50
    - VR（VMA10 / VMA50）
    - VOL_RATIO20（今日量 / VMA20）
    - AMT60（60日均成交额）
    - RS20（20日相对强度）
    - HIGH20 / LOW20（20日高低）
    - ATR14
    要求样本长度 >= 60，否则返回 None（fail-closed）。
    """
    path = DATA / f"{symbol}.csv"
    if not path.exists():
        return None

    df = pd.read_csv(path)
    if "Date" not in df.columns or "Close" not in df.columns or "Volume" not in df.columns:
        return None

    # 排序 + 截止日期（用于回测）
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date")
    if cutoff:
        df = df[df["Date"] <= cutoff]

    # 转数值
    for c in ["Open", "High", "Low", "Close", "Volume"]:
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

    # 成交额（元）
    amt = parse_amount_if_exists(df)
    if amt is None or amt.isna().all():
        amt = infer_amount_from_cv(df)
    df = df.assign(AmountY=amt)

    # 样本不足 60 日，不纳入本次 universe
    if len(df) < 60:
        return None

    # 均线
    df["MA5"] = ma(df["Close"], 5)
    df["MA13"] = ma(df["Close"], 13)
    df["MA39"] = ma(df["Close"], 39)

    # 量能相关
    df["VMA10"] = ma(df["Volume"], 10)
    df["VMA20"] = ma(df["Volume"], 20)
    df["VMA50"] = ma(df["Volume"], 50)
    df["VR"] = df["VMA10"] / df["VMA50"]           # 短期 vs 中期
    df["VOL_RATIO20"] = df["Volume"] / df["VMA20"]  # 今日 vs 20日均量

    # 60日均成交额（元）
    df["AMT60"] = ma(df["AmountY"], 60)

    # RS20：20日相对强度
    df["RS20"] = df["Close"] / df["Close"].shift(20) - 1.0

    # 20日高低（用于部分强度 / 波动率指标）
    df["HIGH20"] = df["High"].rolling(20, min_periods=20).max()
    df["LOW20"] = df["Low"].rolling(20, min_periods=20).min()

    # ATR14：波动率参考（当前 F1-F6 未直接使用，保留在 features）
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
        is_delisting = bool(r.get("is_delisting", False))
        is_suspended = bool(r.get("is_suspended", False))
        float_shares = nz(r.get("float_shares", 0.0), 0.0)

        # TurnoverRate 时间序列（如存在）
        if "TurnoverRate" in df.columns:
            tr_all = pd.to_numeric(df["TurnoverRate"], errors="coerce")
        else:
            tr_all = pd.Series(dtype=float)

        turnover_d = float("nan")
        turnover60_avg = float("nan")

        # 只在最近 180 日中有足够样本时使用换手率
        if not tr_all.empty:
            last_tr = float(tr_all.iloc[-1]) if not math.isnan(float(tr_all.iloc[-1])) else float("nan")
            if not math.isnan(last_tr):
                recent = tr_all.tail(180)
                valid_recent = recent[recent.notna()]
                if len(valid_recent) >= 60:
                    turnover_d = last_tr
                    turnover60_avg = float(valid_recent.tail(60).mean())

        # ---------- F2: 强流动性 ----------
        def pass_liquidity_v2_func() -> bool:
            """
            强流动性条件：
            - 60日均成交额 >= 500万
            - 60日均换手率 >= 0.8%（0.008）
            - 当日换手率 >= 0.6%（0.006）
            条件任一缺失 -> False
            """
            if amt60 < 5_000_000:
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
            - MA5, MA13, MA39, MA5_shift_5, Close 均为有效数值
            - 多头排列: MA5 >= MA13 >= MA39
            - Close > MA13
            - (MA5 - MA5_shift_5) / MA5_shift_5 >= 1.5%
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
                "is_delisting": is_delisting,
                "is_suspended": is_suspended,
                "float_shares": float_shares if float_shares > 0 else None,
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
        raise RuntimeError("没有可用标的（CSV 太短或列缺失）")

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

    # ---------- F4: 放量确认（pass_volume_confirm） ----------
    # 条件：
    #   1) 量能进入全市场前 40%: pct_vr >= 0.6
    #      或 自身放量明显: vol_ratio20 >= 1.2
    #   2) 且 price_ok（收盘价不低于前一日）
    dfu["volume_boost"] = (dfu["pct_vr"] >= 0.6) | (dfu["vol_ratio20"] >= 1.2)
    dfu["pass_volume_confirm"] = dfu["volume_boost"] & dfu["price_ok"].fillna(False)

    # ---------- F6: 强板块龙头（pass_industry_leader） ----------
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

        # 数值特征回写到 features，便于前端展示/调试（可选使用）
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
