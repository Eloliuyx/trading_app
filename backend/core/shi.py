# core/shi.py
# rules_version: v1.2.0
from __future__ import annotations

from dataclasses import dataclass
from math import log
from typing import Literal

import pandas as pd

from core.segment import Segment
from core.zhongshu import Zhongshu

ShiClass = Literal[
    "中枢上破进行中",
    "中枢下破进行中",
    "中枢震荡未破",
    "上行背驰待确证",
    "下行背驰待确证",
    "上行背驰确立",
    "下行背驰确立",
]


@dataclass(frozen=True)
class ShiResult:
    class_: ShiClass
    evidence: list[str]
    momentum: float  # 最近主导方向段的力度（0..1 归一）
    risk: float  # 0..1，越高风险越大
    confidence: float  # 0..1
    last_segment_index: int | None = None
    last_zhongshu_index: int | None = None


# ---------------- helpers ----------------


def _hl_lists(df_eq: pd.DataFrame):
    highs = df_eq["High"].astype(float).tolist()
    lows = df_eq["Low"].astype(float).tolist()
    return highs, lows


def _segment_price_and_bars(
    seg: Segment, highs: list[float], lows: list[float]
) -> tuple[float, int]:
    """
    段的方向化 Δ价 与 跨越K数
      up  : Δp = High[end] - Low[start]
      down: Δp = High[start] - Low[end]
      bars = end - start（至少 1）
    """
    if seg.dir == "up":
        dprice = highs[seg.end] - lows[seg.start]
    else:
        dprice = highs[seg.start] - lows[seg.end]
    dbars = max(1, seg.end - seg.start)
    return dprice, dbars


def _segment_momentum(seg: Segment, highs: list[float], lows: list[float]) -> float:
    dprice, dbars = _segment_price_and_bars(seg, highs, lows)
    return max(0.0, dprice) / log(dbars + 1.0)


def _segment_extreme(seg: Segment, highs: list[float], lows: list[float]) -> float:
    """段方向上的“极值”：上段看 High[end]，下段看 Low[end]。"""
    return highs[seg.end] if seg.dir == "up" else lows[seg.end]


def _last_price_mid(df_eq: pd.DataFrame) -> float:
    """用最后一根等价K的 (High+Low)/2 作为当前位置近似。"""
    last = df_eq.iloc[-1]
    return (float(last["High"]) + float(last["Low"])) / 2.0


def _normalize_momentum(m: float) -> float:
    """力度做温和压缩，避免 UI 跨度过大。"""
    if m <= 0:
        return 0.0
    return m / (m + 5.0)


def _confidence_score(
    has_zs: bool,
    n_segs: int,
    in_band: bool,
    trend_agree: bool,
    has_divergence: bool,
    conflict: bool,
) -> float:
    """
    confidence = clamp((结构完整度 + 势一致性) - 冲突惩罚, 0, 1)
      结构完整度：有中枢 + 段数越多越高
      势一致性：突破方向与最近段一致更高；在中枢内适中
      冲突惩罚：背驰/方向冲突/位置冲突 时扣分（Precision 优先）
    """
    struct = 0.35
    if has_zs and n_segs >= 2:
        struct = 0.55
    if has_zs and n_segs >= 3:
        struct = 0.75

    if in_band:
        trend = 0.5
    else:
        trend = 0.65 if trend_agree else 0.35

    penalty = 0.0
    if has_divergence:
        penalty += 0.2
    if conflict:
        penalty += 0.15

    val = (struct + trend) - penalty
    return max(0.0, min(1.0, val))


def _prev_same_dir_index(segments: list[Segment], k: int) -> int | None:
    """找 k 之前最近一个同向段的索引。"""
    if k <= 0:
        return None
    d = segments[k].dir
    for j in range(k - 1, -1, -1):
        if segments[j].dir == d:
            return j
    return None


def _is_divergence_with_prev_same(
    seg_now: Segment, seg_prev: Segment, highs: list[float], lows: list[float]
) -> bool:
    """
    背驰判定：新高/新低 且 力度减弱（与“上一同向段”比较）
    """
    now_ext = _segment_extreme(seg_now, highs, lows)
    prev_ext = _segment_extreme(seg_prev, highs, lows)
    now_m = _segment_momentum(seg_now, highs, lows)
    prev_m = _segment_momentum(seg_prev, highs, lows)

    if seg_now.dir == "up":
        return (now_ext > prev_ext) and (now_m < prev_m)
    else:
        return (now_ext < prev_ext) and (now_m < prev_m)


# ---------------- main API ----------------


def classify_shi(  # noqa: C901
    df_eq: pd.DataFrame,
    segments: list[Segment],
    zhongshus: list[Zhongshu],
) -> ShiResult:
    """
    势分类（互斥单选）：
      - 中枢上破进行中 / 中枢下破进行中 / 中枢震荡未破
      - 上行背驰待确证 / 下行背驰待确证
      - 上行背驰确立 / 下行背驰确立

    判据：
      - 最近一个中枢的价格带位置（UpperZ/LowerZ）与“当前位置”比较
      - 最近两段“同向段”的极值与力度 M 比较
      - 背驰“确立”：背驰出现后，出现**反向段**确认
    """
    highs, lows = _hl_lists(df_eq)
    n_seg = len(segments)
    has_zs = len(zhongshus) > 0

    # 当前位置相对最近中枢带
    last_price = _last_price_mid(df_eq)
    in_band = False
    above = below = False
    last_zs_idx: int | None = None
    upper = lower = None
    if has_zs:
        zs = zhongshus[-1]
        lower, upper = zs.price_range
        last_zs_idx = len(zhongshus) - 1
        if lower < last_price < upper:
            in_band = True
        elif last_price >= upper:
            above = True
        elif last_price <= lower:
            below = True

    # 无段：仅靠位置给出势
    if n_seg == 0:
        if has_zs and above:
            return ShiResult(
                "中枢上破进行中", ["价位高于中枢上沿"], 0.0, 0.5, 0.6, None, last_zs_idx
            )
        if has_zs and below:
            return ShiResult(
                "中枢下破进行中", ["价位低于中枢下沿"], 0.0, 0.5, 0.6, None, last_zs_idx
            )
        return ShiResult(
            "中枢震荡未破",
            ["价位处于中枢带内或无有效线段"],
            0.0,
            0.5,
            0.5,
            None,
            last_zs_idx,
        )

    # 最近一段
    k = n_seg - 1
    last_seg = segments[k]
    last_m = _segment_momentum(last_seg, highs, lows)
    last_m_norm = _normalize_momentum(last_m)

    # 背驰：检测在“最后一段”上是否与其“上一同向段”构成背驰
    div_on_last = False
    prev_same_idx = _prev_same_dir_index(segments, k)
    if prev_same_idx is not None:
        div_on_last = _is_divergence_with_prev_same(last_seg, segments[prev_same_idx], highs, lows)

    # 背驰确立：如果“倒数第二段”已经发生背驰，且“最后一段”方向与其相反 → 确立
    established = False
    div_on_penultimate = False
    if n_seg >= 2:
        j = k - 1
        prev_same_j = _prev_same_dir_index(segments, j)
        if prev_same_j is not None:
            div_on_penultimate = _is_divergence_with_prev_same(
                segments[j], segments[prev_same_j], highs, lows
            )
            if div_on_penultimate and segments[k].dir != segments[j].dir:
                established = True

    evidence: list[str] = []
    conflict = False

    # 互斥分类优先级：
    # 1) 背驰确立
    # 2) 背驰待确证（发生在最后一段）
    # 3) 中枢突破进行中（位置 + 最近段方向一致 + 无背驰）
    # 4) 中枢震荡未破 / 边界冲突
    if established:
        cls: ShiClass = "上行背驰确立" if segments[k - 1].dir == "up" else "下行背驰确立"
        evidence.append("上一段已背驰且随后出现反向段（确立）")
        has_divergence = True
    elif div_on_last:
        cls = "上行背驰待确证" if last_seg.dir == "up" else "下行背驰待确证"
        evidence.append("最近一段创新高/新低但力度减弱（背驰待确证）")
        has_divergence = True
    else:
        has_divergence = False
        if has_zs and above and last_seg.dir == "up":
            cls = "中枢上破进行中"
            evidence.extend(["价位高于中枢上沿", "最近线段方向向上"])
        elif has_zs and below and last_seg.dir == "down":
            cls = "中枢下破进行中"
            evidence.extend(["价位低于中枢下沿", "最近线段方向向下"])
        else:
            cls = "中枢震荡未破"
            if has_zs and above and last_seg.dir != "up":
                evidence.append("价位高于上沿但线段方向非上行（冲突）")
                conflict = True
            elif has_zs and below and last_seg.dir != "down":
                evidence.append("价位低于下沿但线段方向非下行（冲突）")
                conflict = True
            else:
                evidence.append("结构不足或仍处中枢内")

    trend_agree = (cls == "中枢上破进行中" and last_seg.dir == "up") or (
        cls == "中枢下破进行中" and last_seg.dir == "down"
    )

    conf = _confidence_score(has_zs, n_seg, in_band, trend_agree, has_divergence, conflict)
    risk = max(0.0, min(1.0, 1.0 - conf))

    return ShiResult(
        class_=cls,
        evidence=evidence,
        momentum=last_m_norm,
        risk=risk,
        confidence=conf,
        last_segment_index=k,
        last_zhongshu_index=(len(zhongshus) - 1) if has_zs else None,
    )
