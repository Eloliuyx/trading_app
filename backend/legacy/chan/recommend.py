# core/recommend.py
# rules_version: v1.2.0
from __future__ import annotations

from dataclasses import dataclass
from math import log
from typing import Literal

import pandas as pd

from core.segment import Segment
from core.shi import ShiResult
from core.zhongshu import Zhongshu

RULES_VERSION = "v1.2.0"

# ---------------- configurable thresholds (tune here) ----------------
UPPER_NEAR_PCT = 0.002  # A 条件：上沿“附近”判定带（±0.2%）
LOOKBACK_BARS = 3  # A 条件：近 N 根内需看到一次“触碰上沿”的回踩
C_MARGIN = 0.02  # C 条件：动能相对提升的安全边际（+2%）
BUY_TH = 0.85  # 买入强度阈值（强买点门槛）
CONF_TH = 0.80  # 势（Shi）置信度闸门（买入需 >= 0.80）
HOLD_TH_LOW = 0.70  # “持有”下限（上破进行中，延续但未达强买点）
INVALIDATE_FALL = 0.01  # 无效条件：跌破参考位 1%

Action = Literal["买", "观察买点", "持有", "止盈", "回避"]


@dataclass(frozen=True)
class Recommendation:
    action: Action
    buy_strength: float  # 0..1
    rationale: str  # 简短中文 ≤ 60 字
    invalidate_if: str  # 失效条件
    components: dict[str, float]  # A/B/C/D/E 的 0/1 值


# ---------------- helpers ----------------


def _hl_lists(df_eq: pd.DataFrame):
    highs = df_eq["High"].astype(float).tolist()
    lows = df_eq["Low"].astype(float).tolist()
    return highs, lows


def _last_price_mid(df_eq: pd.DataFrame) -> float:
    last = df_eq.iloc[-1]
    return (float(last["High"]) + float(last["Low"])) / 2.0


def _segment_momentum(seg: Segment, highs: list[float], lows: list[float]) -> float:
    """力度：Δprice / ln(Δbars + 1)，方向化；bars 至少为 1。"""
    if seg.dir == "up":
        dprice = highs[seg.end] - lows[seg.start]
    else:
        dprice = highs[seg.start] - lows[seg.end]
    bars = max(1, seg.end - seg.start)
    return max(0.0, dprice) / log(bars + 1.0)


def _prev_same_dir_index(segments: list[Segment], k: int) -> int | None:
    if k <= 0:
        return None
    d = segments[k].dir
    for j in range(k - 1, -1, -1):
        if segments[j].dir == d:
            return j
    return None


def _mid(h: list[float], lows: list[float], idx: int) -> float:
    return (float(h[idx]) + float(lows[idx])) / 2.0


def _recent_pullback_confirmed_to_upper(
    df_eq: pd.DataFrame,
    upper: float,
    tol: float,
    lookback: int = LOOKBACK_BARS,
) -> bool:
    """
    过去 lookback 根内，出现过“上破→回踩至上沿附近(±tol)且不破”的迹象；
    且当前价仍 ≥ upper - tol。
    """
    highs = df_eq["High"].astype(float).tolist()
    lows = df_eq["Low"].astype(float).tolist()
    n = len(highs)
    if n < 2:
        return False
    last_mid = _mid(highs, lows, n - 1)
    if last_mid < upper - tol:
        return False

    start = max(0, n - 1 - lookback)
    touched = False
    for i in range(start, n - 1):  # 不含最后一根
        m = _mid(highs, lows, i)
        if (upper - tol) <= m <= (upper + tol):
            touched = True
            break
    return touched


# ---------------- scoring per v1.2 (precision tuned) ----------------


def compute_buy_strength(
    df_eq: pd.DataFrame,
    segments: list[Segment],
    zhongshus: list[Zhongshu],
    shi: ShiResult,
    *,
    eps: float = 1e-9,
) -> tuple[float, dict[str, float], list[str], str]:
    """
    返回：
      score ∈ [0,1]，
      components: {"A","B","C","D","E"}
      reasons: 满足项对应短句（按 B→A→C→D→E 排序）
      invalidate_if: 失效条件中文
    """
    highs, lows = _hl_lists(df_eq)
    last_price = _last_price_mid(df_eq)

    # ---- A：上沿附近或“突破后回踩不破” ----
    compA = 0.0
    A_text: str | None = None
    if zhongshus:
        lower, upper = zhongshus[-1].price_range
        tol = max(eps, upper * UPPER_NEAR_PCT)
        near_upper = (upper - tol) <= last_price <= (upper + tol)
        pullback_ok = _recent_pullback_confirmed_to_upper(df_eq, upper, tol, lookback=LOOKBACK_BARS)
        if near_upper:
            compA = 1.0
            A_text = "靠近中枢上沿，回踩不破"
        elif pullback_ok:
            compA = 1.0
            A_text = "突破上沿后回踩确认"

    # ---- B：势转折（上一段 down，本段 up）----
    compB = 0.0
    B_text: str | None = None
    if len(segments) >= 2 and segments[-1].dir == "up" and segments[-2].dir == "down":
        compB = 1.0
        B_text = "由下转上，离开段已成立"

    # ---- C：同向动能提升（较上一同向段强 + 安全边际）----
    compC = 0.0
    C_text: str | None = None
    if len(segments) >= 1:
        k = len(segments) - 1
        prev_same = _prev_same_dir_index(segments, k)
        if prev_same is not None:
            m_now = _segment_momentum(segments[k], highs, lows)
            m_prev = _segment_momentum(segments[prev_same], highs, lows)
            if m_now > m_prev * (1.0 + C_MARGIN):
                compC = 1.0
                C_text = "当前离开段动能强于前段"

    # ---- D：无背驰（Shi 不为“背驰*”）----
    compD = 0.0
    D_text: str | None = None
    if not any(term in shi.class_ for term in ("背驰确立", "背驰待确证")):
        compD = 1.0
        D_text = "内部未见背驰信号"

    # ---- E：主级别中枢（legs ≥ 4 近似）----
    compE = 0.0
    E_text: str | None = None
    if zhongshus and len(zhongshus[-1].legs) >= 4:
        compE = 1.0
        E_text = "基于主级别中枢"

    components = {"A": compA, "B": compB, "C": compC, "D": compD, "E": compE}

    # ---- 加权 ----
    score = 0.35 * compA + 0.25 * compB + 0.15 * compC + 0.15 * compD + 0.10 * compE
    score = max(0.0, min(1.0, score))

    # ---- 理由（B→A→C→D→E）----
    reasons_ordered = [t for t in (B_text, A_text, C_text, D_text, E_text) if t]

    # ---- 无效条件（按势类别细化）----
    if shi.class_ == "下行背驰确立" and segments:
        # 以“背驰确认低点”（最后一段的 end 低点）为锚
        anchor = lows[segments[-1].end]
        invalidate = f"跌破背驰确认低点 -{int(INVALIDATE_FALL*100)}%（{anchor*(1-INVALIDATE_FALL):.3f}）则本买点失效"
    elif zhongshus:
        lower, upper = zhongshus[-1].price_range
        invalidate = f"跌破中枢上沿 -{int(INVALIDATE_FALL*100)}%（{upper*(1-INVALIDATE_FALL):.3f}）则本买点失效"
    elif segments:
        last = segments[-1]
        anchor = lows[last.start] if last.dir == "up" else highs[last.start]
        invalidate = f"跌破参考位 -{int(INVALIDATE_FALL*100)}%（{anchor*(1-INVALIDATE_FALL):.3f}）则本买点失效"
    else:
        invalidate = "跌破最近低点 -1% 则本买点失效"

    return score, components, reasons_ordered, invalidate


def advise_for_today(
    df_eq: pd.DataFrame,
    segments: list[Segment],
    zhongshus: list[Zhongshu],
    shi: ShiResult,
) -> Recommendation:
    """
    依据 v1.2（Precision 优先）：
      - 势 × 买点强度 → 操作建议
      - A/B/C/D/E 生成简短理由与失效条件
      - 使用 Shi 置信度闸门防误报
    """
    score, comps, reasons, invalidate = compute_buy_strength(df_eq, segments, zhongshus, shi)

    # ---- 决策（互斥）----
    if (
        (shi.class_ == "中枢上破进行中" and score >= BUY_TH)
        or (shi.class_ == "下行背驰确立" and score >= BUY_TH)
    ) and shi.confidence >= CONF_TH:
        action: Action = "买"
    elif (
        shi.class_ == "中枢上破进行中"
        and HOLD_TH_LOW <= score < BUY_TH
        and shi.confidence >= HOLD_TH_LOW
    ):
        action = "持有"
    elif shi.class_ == "上行背驰确立":
        action = "止盈"
    elif shi.class_ == "中枢震荡未破" and HOLD_TH_LOW <= score < BUY_TH:
        action = "观察买点"
    else:
        action = "回避"

    rationale = "，".join(reasons) if reasons else "结构尚未满足强买点条件"

    return Recommendation(
        action=action,
        buy_strength=round(score, 4),
        rationale=rationale[:60],
        invalidate_if=invalidate,
        components=comps,
    )


__all__ = [
    "RULES_VERSION",
    "Recommendation",
    "compute_buy_strength",
    "advise_for_today",
]
