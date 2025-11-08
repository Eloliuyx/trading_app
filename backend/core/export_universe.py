# backend/core/export_universe.py
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]  # .../backend
CANDIDATES = [
    ROOT.parent / "frontend" / "public",
    ROOT.parent / "public",
]


def pick_public() -> Path:
    for p in CANDIDATES:
        meta = p / "data" / "metadata" / "symbols.csv"
        if meta.exists():
            print(f"[export_universe] using PUBLIC dir: {p}")
            return p
    raise FileNotFoundError("symbols.csv not found under frontend/public or public")


PUBLIC = pick_public()
DATA = PUBLIC / "data"
META = PUBLIC / "data" / "metadata" / "symbols.csv"
OUT = PUBLIC / "out" / "universe.json"


# --------------- helpers ---------------
def nz(x: Any, default: float = 0.0) -> float:
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return default
        return float(x)
    except Exception:
        return default


def percent_rank(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    return s.rank(pct=True, method="average").fillna(0.0)


def ma(series: pd.Series, n: int) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").rolling(n, min_periods=n).mean()


def read_symbols(meta_path: Path) -> pd.DataFrame:
    """读取 symbols.csv，并归一化出本项目需要的字段。"""
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

    # is_st
    if "is_st" in cols:
        out["is_st"] = df[cols["is_st"]].astype(bool)
    else:
        upper_name = out["name"].str.upper()
        upper_sym = out["symbol"].str.upper()
        out["is_st"] = upper_name.str.contains("ST") | upper_sym.str.contains("ST")

    # 退市 & 停牌，若不存在则默认 False
    if "is_delisting" in cols:
        out["is_delisting"] = df[cols["is_delisting"]].astype(bool)
    else:
        out["is_delisting"] = False

    if "is_suspended" in cols:
        out["is_suspended"] = df[cols["is_suspended"]].astype(bool)
    else:
        out["is_suspended"] = False

    # 流通股本（尽量从多种列名推断；缺失时为 NaN，后面做宽松处理）
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


# --------------- amount normalization ---------------
AMOUNT_CANDIDATES = ["Amount", "amount", "成交额", "成交额(元)", "Turnover", "turnover"]


def parse_amount_if_exists(df: pd.DataFrame) -> Optional[pd.Series]:
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
    if amt.notna().any():
        # 若 95 分位 < 1e9（元），基本是“千元”——乘以 1000 统一到元
        q95 = np.nanpercentile(amt.to_numpy(dtype=float), 95)
        if q95 < 1e9:
            amt = amt * 1_000.0
    return amt


def infer_amount_from_cv(df: pd.DataFrame) -> pd.Series:
    # 先把基础列转数值
    for c in ["Close", "Volume"]:
        if df[c].dtype == "object":
            df[c] = (
                df[c]
                .astype(str)
                .str.replace(",", "", regex=False)
                .str.replace(" ", "", regex=False)
            )
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # 按“手”估算：元 ≈ Close × Volume × 100
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


def load_one(symbol: str, cutoff: Optional[str]) -> Optional[pd.DataFrame]:
    path = DATA / f"{symbol}.csv"
    if not path.exists():
        return None

    df = pd.read_csv(path)
    if "Date" not in df.columns or "Close" not in df.columns or "Volume" not in df.columns:
        return None

    # 排序 + 截止
    df = df.sort_values("Date")
    if cutoff:
        df = df[df["Date"] <= cutoff]

    # 基础列转数值
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

    # 1) 有 Amount → 统一到【元】
    amt = parse_amount_if_exists(df)

    # 2) 无 Amount → 用 Close×Volume 估算到【元】（手→股的自检）
    if amt is None or amt.isna().all():
        amt = infer_amount_from_cv(df)

    df = df.assign(AmountY=amt)

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
    df["VR"] = df["VMA10"] / df["VMA50"]
    df["VOL_RATIO20"] = df["Volume"] / df["VMA20"]

    # 60日均成交额（元）
    df["AMT60"] = ma(df["AmountY"], 60)

    # RS20
    df["RS20"] = df["Close"] / df["Close"].shift(20) - 1.0

    # 20日高低
    df["HIGH20"] = df["High"].rolling(20, min_periods=20).max()
    df["LOW20"] = df["Low"].rolling(20, min_periods=20).min()

    # ATR14
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


# --------------- main ---------------
def main(cutoff: Optional[str]) -> None:
    print(f"[export_universe] DATA={DATA}")
    print(f"[export_universe] META={META}")
    print(f"[export_universe] OUT ={OUT}")
    print(f"[export_universe] CSV count: {len(list(DATA.glob('*.csv')))}")

    base = read_symbols(META)

    rows: List[Dict[str, Any]] = []
    last_dates: List[str] = []

    for _, r in base.iterrows():
        sym = str(r["symbol"])
        df = load_one(sym, cutoff)
        if df is None or df.empty:
            continue
        last = df.iloc[-1]
        last_dates.append(str(last["Date"]))

        close = nz(last["Close"])
        prev_close = nz(df["Close"].iloc[-2]) if len(df) >= 2 else close
        amount_t = nz(last["AmountY"])
        amt60 = nz(last["AMT60"])
        volume = nz(last["Volume"])
        ma5 = nz(last["MA5"], float("nan"))
        ma13 = nz(last["MA13"], float("nan"))
        ma39 = nz(last["MA39"], float("nan"))
        ma5_shift_5 = nz(df["MA5"].shift(5).iloc[-1], float("nan"))
        rs20 = nz(last["RS20"], float("nan"))
        high20 = nz(last["HIGH20"], float("nan"))
        low20 = nz(last["LOW20"], float("nan"))
        atr14 = nz(last["ATR14"], float("nan"))
        vma20 = nz(last["VMA20"], float("nan"))
        vol_ratio20 = nz(last["VOL_RATIO20"], float("nan"))
        vr = nz(last["VR"], float("nan"))

        is_st = bool(r.get("is_st", False))
        is_delisting = bool(r.get("is_delisting", False))
        is_suspended = bool(r.get("is_suspended", False))
        float_shares = nz(r.get("float_shares", float("nan")), float("nan"))

        # ---------- F1: 强流动性_v2 ----------
        if float_shares and not math.isnan(float_shares) and float_shares > 0:
            turnover_d = volume / float_shares
            turnover60_avg = (
                df["Volume"].tail(60).sum() / (60.0 * float_shares)
                if len(df) >= 60
                else float("nan")
            )
        else:
            turnover_d = float("nan")
            turnover60_avg = float("nan")

        def pass_liquidity_v2_func() -> bool:
            if amt60 < 5_000_000:
                return False
            # 若能算换手，则一并判断；否则仅按 amt60 放行，避免误杀缺字段股票
            if not math.isnan(turnover60_avg) and turnover60_avg < 0.008:
                return False
            if not math.isnan(turnover_d) and turnover_d < 0.006:
                return False
            return True

        pass_liquidity_v2 = pass_liquidity_v2_func()

        # ---------- F2: 价格 & 合规 ----------
        pass_price_compliance = (
            (3.0 <= close <= 50.0)
            and (not is_st)
            and (not is_delisting)
            and (not is_suspended)
        )

        # ---------- F3: 多头趋势结构 ----------
        def pass_trend_func() -> bool:
            vals = [ma5, ma13, ma39, ma5_shift_5]
            if any(math.isnan(v) for v in vals):
                return False
            if not (ma5 >= ma13 >= ma39):
                return False
            if not (close > ma13):
                return False
            if ma5_shift_5 <= 0:
                return False
            return (ma5 - ma5_shift_5) / ma5_shift_5 >= 0.015

        pass_trend = pass_trend_func()

        # Day0 基础特征，F4-F9 在二次遍历统一计算
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
            "turnover_d": nz(turnover_d, float("nan")),
            "turnover60_avg": nz(turnover60_avg, float("nan")),
            "price_ok": close >= prev_close,
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
                "float_shares": float_shares if not math.isnan(float_shares) else None,
                "last_date": str(last["Date"]),
                "amt60_avg": amt60,
                # 基础安全层 & 趋势层
                "pass_liquidity_v2": bool(pass_liquidity_v2),
                "pass_price_compliance": bool(pass_price_compliance),
                "pass_trend": bool(pass_trend),
                "features": row_features,
            }
        )

    if not rows:
        raise RuntimeError("没有可用标的（CSV 太短或列缺失）")

    # ---------- 二次遍历：全市场分位、行业强度、F4-F9 ----------
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

    # 市场分位
    dfu["pct_amt"] = percent_rank(dfu["amount_t"])
    base_vr = dfu["vol_ratio20"]
    if base_vr.isna().all():
        base_vr = dfu["vr"]
    dfu["pct_vr"] = percent_rank(base_vr)
    dfu["pct_rs20"] = percent_rank(dfu["rs20_raw"])

    # F4: 放量确认（量价齐升）
    dfu["volume_boost"] = (dfu["pct_vr"] >= 0.6) | (dfu["vol_ratio20"] >= 1.2)
    dfu["pass_volume_confirm"] = dfu["volume_boost"] & dfu["price_ok"].fillna(False)

    # 行业强度 & 行业排名（基于 RS20）
    ind_strength = (
        dfu.groupby("industry", as_index=False)["rs20_raw"]
        .median()
        .rename(columns={"rs20_raw": "industry_rs20"})
    )
    ind_strength["industry_rs20_pct"] = percent_rank(ind_strength["industry_rs20"])
    dfu = dfu.merge(ind_strength, on="industry", how="left")

    dfu["rank_in_industry_by_rs20"] = (
        dfu.groupby("industry")["rs20_raw"]
        .rank(ascending=False, method="min")
        .astype(float)
    )
    dfu["industry_size"] = dfu.groupby("industry")["symbol"].transform("count")

    # F5: 强板块 + 行业前列
    dfu["strong_industry"] = dfu["industry_rs20_pct"] >= 0.6
    dfu["leader_in_industry"] = dfu["rank_in_industry_by_rs20"] <= dfu[
        "industry_size"
    ].clip(upper=5)
    dfu["pass_industry_leader"] = dfu["strong_industry"] & dfu["leader_in_industry"]

    # F6: 全市场强势优先
    dfu["pass_rs_market_strong"] = dfu["pct_rs20"] >= 0.9

    # F7: 20日新高 / 平台突破
    dfu["pass_break_20d_high"] = dfu["close"] > dfu["high20"]

    # F8: 稳健模式（波动率控制）
    atr_pct = dfu["atr14"] / dfu["close"]
    range20 = (dfu["high20"] - dfu["low20"]) / dfu["high20"]
    dfu["pass_low_vol"] = (atr_pct < 0.05) & (range20 < 0.15)

    # F9: 主力资金流入优先（当前无可靠口径，预留为 False）
    dfu["pass_moneyflow"] = False

    # 写回 rows
    dfu = dfu.set_index("symbol")
    for it in rows:
        sym = it["symbol"]
        if sym not in dfu.index:
            continue
        row = dfu.loc[sym]
        feat = it.get("features") or {}

        # 数值特征写回 features
        for k in [
            "pct_amt",
            "pct_vr",
            "pct_rs20",
            "industry_rs20",
            "industry_rs20_pct",
            "rank_in_industry_by_rs20",
            "industry_size",
        ]:
            v = row.get(k)
            if pd.notna(v):
                feat[k] = float(v)

        # 布尔口径写到顶层 & features，供前端直接用
        for fld in [
            "pass_volume_confirm",
            "pass_industry_leader",
            "pass_rs_market_strong",
            "pass_break_20d_high",
            "pass_low_vol",
            "pass_moneyflow",
        ]:
            val = bool(row.get(fld, False))
            it[fld] = val
            feat[fld] = val

        it["features"] = feat

    # 选择 asof（众数）
    try:
        asof = pd.Series(last_dates).mode().iloc[0]
    except Exception:
        asof = ""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        json.dump({"asof": asof, "list": rows}, f, ensure_ascii=False, allow_nan=False)

    print(f"[export_universe] wrote {len(rows)} items -> {OUT}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", dest="cutoff", help="YYYY-MM-DD，回测到此日期（含）", default=None)
    args = ap.parse_args()
    main(args.cutoff)
