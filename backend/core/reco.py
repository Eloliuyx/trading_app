# backend/core/reco.py
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict

import numpy as np
import pandas as pd

# 与新版规则对应的版本号
RULES_VERSION = "trend-v1.0-core"


@dataclass
class MetaRow:
    symbol: str
    name: str
    industry: str
    market: str
    is_st: bool = False
    is_delisting: bool = False
    is_suspended: bool = False
    float_shares: float | None = None


def ma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def select_today(df: pd.DataFrame, meta: MetaRow) -> Dict[str, Any]:
    """
    基于单票日线，在最后一根K上应用 F1–F4（不含横截面板块部分）。
    若不满足核心条件，返回 {}。
    """
    if len(df) < 60:
        return {}

    df = df.copy()
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    close = df["Close"]
    high = df["High"]
    vol = df["Volume"]

    t = len(df) - 1
    if t < 1:
        return {}

    last_close = float(close.iloc[t])
    prev_close = float(close.iloc[t - 1])

    ma5 = ma(close, 5)
    ma13 = ma(close, 13)
    ma39 = ma(close, 39)
    ma5_shift_5 = ma5.shift(5)

    # ===== F1: 强流动性_v2（本地估算版） =====
    if "Amount" in df.columns:
        amt = pd.to_numeric(df["Amount"], errors="coerce")
    else:
        # 粗估：Price * Volume * 100
        amt = close * vol * 100.0
    amt60 = amt.rolling(60, min_periods=60).mean()
    amt60_last = float(amt60.iloc[t]) if not math.isnan(amt60.iloc[t]) else 0.0

    if meta.float_shares and meta.float_shares > 0:
        turnover_d = float(vol.iloc[t]) / meta.float_shares
        turnover60_avg = (
            vol.iloc[t - 59 : t + 1].mean() / meta.float_shares if t >= 59 else math.nan
        )
    else:
        turnover_d = math.nan
        turnover60_avg = math.nan

    def f1() -> bool:
        if amt60_last < 5_000_000:
            return False
        if not math.isnan(turnover60_avg) and turnover60_avg < 0.008:
            return False
        if not math.isnan(turnover_d) and turnover_d < 0.006:
            return False
        return True

    pass_f1 = f1()

    # ===== F2: 价格 & 合规 =====
    pass_f2 = (
        3.0 <= last_close <= 50.0
        and not meta.is_st
        and not meta.is_delisting
        and not meta.is_suspended
    )

    # ===== F3: 多头趋势结构 =====
    ma5_last = float(ma5.iloc[t]) if not math.isnan(ma5.iloc[t]) else math.nan
    ma13_last = float(ma13.iloc[t]) if not math.isnan(ma13.iloc[t]) else math.nan
    ma39_last = float(ma39.iloc[t]) if not math.isnan(ma39.iloc[t]) else math.nan
    ma5_shift_5_last = (
        float(ma5_shift_5.iloc[t]) if not math.isnan(ma5_shift_5.iloc[t]) else math.nan
    )

    def f3() -> bool:
        vals = [ma5_last, ma13_last, ma39_last, ma5_shift_5_last]
        if any(math.isnan(v) for v in vals):
            return False
        if not (ma5_last >= ma13_last >= ma39_last):
            return False
        if not (last_close > ma13_last):
            return False
        if ma5_shift_5_last <= 0:
            return False
        return (ma5_last - ma5_shift_5_last) / ma5_shift_5_last >= 0.015

    pass_f3 = f3()

    # ===== F4: 放量确认（仅用自身20日均量；横截面分位在 export_universe） =====
    vol_ma20 = ma(vol, 20)
    if not math.isnan(vol_ma20.iloc[t]) and vol_ma20.iloc[t] > 0:
        vol_ratio20 = float(vol.iloc[t]) / float(vol_ma20.iloc[t])
    else:
        vol_ratio20 = 0.0
    price_ok = last_close >= prev_close
    pass_f4 = (vol_ratio20 >= 1.2) and price_ok

    all_core = pass_f1 and pass_f2 and pass_f3 and pass_f4
    if not all_core:
        return {}

    # 简单打分用于排序（强动能 + 强流动性）
    if t >= 20 and close.iloc[t - 20] > 0:
        rs20 = float(last_close / close.iloc[t - 20] - 1.0)
    else:
        rs20 = 0.0
    score = 0.5 * (rs20 + 1.0) + 0.3 * min(amt60_last / 50_000_000.0, 1.0) + 0.2 * min(
        vol_ratio20 / 2.0, 1.0
    )
    score = round(float(score), 4)

    reasons = [
        "强流动性：60日均额≥500万，换手结构健康",
        "价格/合规：3~50元，非 ST/退市/停牌",
        "多头趋势：MA5≥MA13≥MA39，收盘站上 MA13，短期均线上拱",
        "放量确认：相对20日均量放大，且价格不弱于前一日",
    ]

    checks: Dict[str, Any] = {
        "pass_f1_liquidity_v2": pass_f1,
        "pass_f2_price_compliance": pass_f2,
        "pass_f3_trend": pass_f3,
        "pass_f4_volume_confirm": pass_f4,
        "amt60_avg": round(amt60_last, 2),
        "turnover_d": round(turnover_d, 6) if not math.isnan(turnover_d) else None,
        "turnover60_avg": round(turnover60_avg, 6)
        if not math.isnan(turnover60_avg)
        else None,
        "vol_ratio20": round(vol_ratio20, 3),
        "rs20": round(rs20, 4),
    }

    return {
        "score": score,
        "checks": checks,
        "reasons": reasons,
    }


def analyze_symbol(df: pd.DataFrame, meta: MetaRow) -> Dict[str, Any]:
    item = select_today(df, meta)
    if not item:
        return {}
    return {
        "symbol": meta.symbol,
        "name": meta.name,
        "industry": meta.industry,
        "market": meta.market,
        **item,
    }
