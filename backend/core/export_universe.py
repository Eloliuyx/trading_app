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
def nz(x, default: float = 0.0) -> float:
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)):
            return default
        return float(x)
    except Exception:
        return default


def percent_rank(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce").fillna(0.0)
    return s.rank(pct=True, method="average").fillna(0.0)


def ma(series: pd.Series, n: int) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").rolling(n, min_periods=n).mean()


def read_symbols(meta_path: Path) -> pd.DataFrame:
    df = pd.read_csv(meta_path)
    cols = {c.lower(): c for c in df.columns}
    sym = cols.get("symbol") or cols.get("ts_code") or list(df.columns)[0]
    name = cols.get("name") or cols.get("security_name") or "name"
    ind = cols.get("industry") or "industry"
    mkt = cols.get("market") or "market"
    df = df.rename(columns={sym: "symbol", name: "name", ind: "industry", mkt: "market"})
    df["industry"] = df["industry"].fillna("未分类").astype(str)
    return df[["symbol", "name", "industry", "market"]]


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

    # 先按“手”估算：元 ≈ Close × Volume × 100
    est = df["Close"] * df["Volume"] * 100.0

    # 量级自检：若 95 分位 >= 1e9（元）说明已经像“股口径×价格”
    # 再粗看 volume 的 95 分位，如果 volume 本身很大（>=1e9），可能你的 Volume 已是“股”
    q95_amt = np.nanpercentile(est.to_numpy(dtype=float), 95) if est.notna().any() else 0.0
    q95_vol = (
        np.nanpercentile(df["Volume"].to_numpy(dtype=float), 95)
        if df["Volume"].notna().any()
        else 0.0
    )

    # 经验：多数 A 股个股日额在 1e7~1e10 元；若估算 q95 远高（>1e11），试着把 K=100 调回 1
    if q95_amt > 1e11 or q95_vol > 1e9:
        est = df["Close"] * df["Volume"] * 1.0  # 假设 Volume 已是“股”

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

    # 指标
    df["MA5"] = ma(df["Close"], 5)
    df["MA13"] = ma(df["Close"], 13)
    df["MA39"] = ma(df["Close"], 39)
    df["VMA10"] = ma(df["Volume"], 10)
    df["VMA50"] = ma(df["Volume"], 50)
    df["VR"] = df["VMA10"] / df["VMA50"]
    df["AMT60"] = ma(df["AmountY"], 60)  # 60日均成交额（元）
    df["RS20"] = df["Close"] / df["Close"].shift(20) - 1.0

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

        amt60 = nz(df["AMT60"].iloc[-1])
        amt_t = nz(last["AmountY"])

        rows.append(
            {
                "symbol": sym,
                "name": str(r["name"]),
                "industry": str(r["industry"]),
                "market": str(r["market"]),
                # 顶层字段（兼容你现有的简版 schema）
                "last_date": str(last["Date"]),
                "amt60_avg": amt60,  # 元
                # 细分 features（兼容你之前在前端读取 features.* 的写法）
                "features": {
                    "close": nz(last["Close"]),
                    "amt60_avg": amt60,  # 元
                    "amount_t": amt_t,  # 元（当日）
                    "vr": nz(last["VR"]),
                    "rs20_raw": nz(last["RS20"]),
                    "ma5": nz(df["MA5"].iloc[-1], float("nan")),
                    "ma13": nz(df["MA13"].iloc[-1], float("nan")),
                    "ma39": nz(df["MA39"].iloc[-1], float("nan")),
                    # 规则（单位统一为元）
                    "f_liquid_strong": amt60 >= 20_000_000,  # 2000 万元
                    "f_price_floor": nz(last["Close"]) >= 3.0,
                    "f_exclude_st": (
                        ("ST" not in str(r["name"]).upper()) and ("ST" not in sym.upper())
                    ),
                },
            }
        )

    if not rows:
        raise RuntimeError("没有可用标的（CSV 太短或列缺失）")

    # 分位 & 行业强度（给 features 增益；若前端不读取也不影响）
    dfu = pd.DataFrame(
        [{"symbol": it["symbol"], "industry": it["industry"], **it["features"]} for it in rows]
    )
    dfu["pct_amt"] = percent_rank(dfu["amount_t"])
    dfu["pct_vr"] = percent_rank(dfu["vr"])
    dfu["pct_rs20"] = percent_rank(dfu["rs20_raw"])
    ind_strength = (
        dfu.groupby("industry", as_index=False)["pct_rs20"]
        .median()
        .rename(columns={"pct_rs20": "industry_rs20"})
    )
    ind_strength["industry_rs20"] = percent_rank(ind_strength["industry_rs20"])
    dfu = dfu.merge(ind_strength[["industry", "industry_rs20"]], on="industry", how="left")
    dfu["industry_rs20"] = dfu["industry_rs20"].fillna(0.0)

    # 写回到 rows.features（不改变顶层结构）
    strength_map = dfu.set_index("symbol")["industry_rs20"].to_dict()
    for it in rows:
        it["features"]["industry_rs20"] = nz(strength_map.get(it["symbol"], 0.0))

    # 选择 asof
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
