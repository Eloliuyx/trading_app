# backend/core/reco.py
from __future__ import annotations
import math, json
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, List
import numpy as np
import pandas as pd

RULES_VERSION = "trend-v0.3"

@dataclass
class MetaRow:
    symbol: str
    name: str
    industry: str
    market: str
    is_st: bool

def ma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()

def stdev(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).std(ddof=0)

def percentile(arr: pd.Series, p: float) -> float:
    if len(arr) == 0:
        return float("nan")
    return np.percentile(arr.to_numpy(), p*100, method="linear")

def clamp(x: float, lo=0.0, hi=1.0) -> float:
    return max(lo, min(hi, x))

def infer_limit_pct(is_st: bool, market: str) -> float:
    if is_st:
        return 0.05
    if market in ("创业板", "科创板"):
        return 0.20
    return 0.10

def select_today(df: pd.DataFrame, meta: MetaRow) -> Dict[str, Any]:
    """
    对单票在最后一根K上做规则判断与打分。
    返回字典（若不满足，返回 {}）。
    """
    if len(df) < 40:
        return {}

    close = df["Close"]
    high  = df["High"]
    vol   = df["Volume"]
    open_ = df["Open"]

    ma5  = ma(close, 5)
    ma13 = ma(close, 13)
    ma39 = ma(close, 39)

    vol_ma5  = ma(vol, 5)
    vol_ma10 = ma(vol, 10)

    t = len(df) - 1
    # --- 趋势 ---
    cond_trend = (
        (ma5.iloc[t]  > ma13.iloc[t]) and
        (ma13.iloc[t] > ma39.iloc[t]) and
        (ma13.iloc[t] > ma13.iloc[t-1]) and
        (close.iloc[t] > ma13.iloc[t])
    )

    # --- 量价 ---
    max_high5 = high.iloc[t-4:t+1].max()
    cond_volume_price = (
        (vol.iloc[t] >= 1.5 * vol_ma5.iloc[t]) and
        (close.iloc[t] >= 0.98 * max_high5)
    )

    # --- 涨幅 ---
    pct = (close.iloc[t] / close.iloc[t-1] - 1) * 100.0
    cond_pct = (pct >= 3.0) and (pct <= 6.0)

    # --- 筹码近似 ---
    vol_active10 = vol.iloc[t] / max(1e-9, vol_ma10.iloc[t])
    std10 = stdev(close, 10).iloc[t]
    std30 = stdev(close, 30).iloc[t]
    std_ratio = (std10 / std30) if std30 and not math.isclose(std30, 0.0) else 9e9
    pos80 = percentile(close.iloc[t-29:t+1], 0.80)
    cond_chips = (vol_active10 >= 1.2) and (std_ratio <= 0.8) and (close.iloc[t] >= pos80)

    # --- 连板 ≥3 剔除 ---
    EPS = 0.002
    lim = infer_limit_pct(meta.is_st, meta.market)
    is_limit = (close.pct_change() >= (lim - EPS)).astype(int)
    streak = 0
    for k in range(t, max(-1, t-10), -1):
        if is_limit.iloc[k] == 1:
            streak += 1
        else:
            break
    cond_limit = (streak < 3)

    # --- 弱转强 ---
    cond_wts = max(open_.iloc[t], close.iloc[t]) > max(open_.iloc[t-1], close.iloc[t-1])

    all_ok = cond_trend and cond_volume_price and cond_pct and cond_chips and cond_limit and cond_wts
    if not all_ok:
        return {}

    # --- 评分（排序用）---
    trend_score = 1.0
    vp_score = 0.5 * clamp(vol.iloc[t] / (1.5 * vol_ma5.iloc[t])) + \
               0.5 * clamp(close.iloc[t] / (0.98 * max_high5))
    chips_score = 0.34 * clamp(vol_active10 / 1.2) + \
                  0.33 * clamp(0.8 / max(1e-9, std_ratio)) + \
                  0.33 * clamp((close.iloc[t] - close.iloc[t-29:t+1].min()) /
                               max(1e-9, close.iloc[t-29:t+1].max() - close.iloc[t-29:t+1].min()))
    score = 0.4 * trend_score + 0.35 * vp_score + 0.25 * chips_score
    score = round(float(score), 4)

    reasons = []
    reasons.append("趋势：MA5>MA13>MA39 且 MA13 上拐，收盘站上MA13")
    reasons.append("量价：量能≥5日1.5倍，收盘接近5日高")
    reasons.append(f"涨幅：{pct:.1f}%，动能健康")
    reasons.append("筹码：活跃度↑、波动收敛、位于近30日上侧区间")
    reasons.append("结构：今日实体区间上移（弱转强）")

    return {
        "score": score,
        "checks": {
            "trend": {"pass": True},
            "volume_price": {
                "pass": True,
                "volume_mult": round(float(vol.iloc[t] / max(1e-9, vol_ma5.iloc[t])), 3),
                "high_5d": round(float(max_high5), 4),
                "close_ratio_to_high5": round(float(close.iloc[t] / max_high5), 4),
            },
            "chips": {
                "pass": True,
                "vol_active10": round(float(vol_active10), 3),
                "std10": round(float(std10), 6) if not pd.isna(std10) else None,
                "std30": round(float(std30), 6) if not pd.isna(std30) else None,
                "std_ratio": round(float(std_ratio), 6) if not pd.isna(std_ratio) else None,
                "position30": round(float(
                    (close.iloc[t] - close.iloc[t-29:t+1].min()) /
                    max(1e-9, close.iloc[t-29:t+1].max() - close.iloc[t-29:t+1].min())
                ), 3)
            },
            "pct_change": round(float(pct), 3),
            "limit_streak": streak,
            "weak_to_strong": True
        },
        "reasons": reasons
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
        **item
    }
