# core/bi.py
# rules_version: v1.2.0
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from core.fractals import (
    Fractal,
    compress_fractals_for_bi,
    detect_fractal_candidates,
)

BiDir = Literal["up", "down"]


@dataclass(frozen=True)
class Bi:
    start: int  # 起点（等价K序列索引 = 底/顶分型的中心 idx）
    end: int  # 终点（等价K序列索引）
    dir: BiDir  # 'up' or 'down'


# ---------------- helpers ----------------


def _tolist_float(series: pd.Series) -> list[float]:
    return series.astype(float).tolist()


def _more_extreme_same_type(  # noqa: C901
    highs: list[float], lows: list[float], a: Fractal, b: Fractal
) -> Fractal:
    """同类分型之间，返回更“极端”的那个；完全平价取更左（a）。"""
    if a.type != b.type:
        return a  # 防御，不应出现
    if a.type == "top":
        if highs[a.idx] > highs[b.idx]:
            return a
        if highs[b.idx] > highs[a.idx]:
            return b
        # 高点相等 → 低点更高者更“抬升”
        if lows[a.idx] > lows[b.idx]:
            return a
        if lows[b.idx] > lows[a.idx]:
            return b
        return a  # 完全平价 → 取更左
    else:  # bottom
        if lows[a.idx] < lows[b.idx]:
            return a
        if lows[b.idx] < lows[a.idx]:
            return b
        # 低点相等 → 高点更低者更“下压”
        if highs[a.idx] < highs[b.idx]:
            return a
        if highs[b.idx] < highs[a.idx]:
            return b
        return a


def _enforce_min_span_and_alternation(
    highs: list[float], lows: list[float], cands: list[Fractal]
) -> list[Fractal]:
    """
    在“候选分型”基础上为构笔进行规范化：
      1) 先用 compress_fractals_for_bi 去除“相邻(idx差1)抖动”
      2) 再保证类型交替：若出现同类连发（即使 idx差≥2），保留更极端/更左的一个
      3) 最终确保构笔所需的最小跨度：相邻保留分型的中心 idx 差 ≥ 2
    """
    if not cands:
        return []

    # 第一步：先去掉 idx 差 1 的抖动（相邻冲突）
    out = compress_fractals_for_bi(highs, lows, cands)

    # 第二步：保证交替（同类连发时收敛为一个极端点）
    alt: list[Fractal] = []
    for f in out:
        if not alt:
            alt.append(f)
            continue
        g = alt[-1]
        if f.type == g.type:
            # 同类：保留更极端（平价取左）
            alt[-1] = _more_extreme_same_type(highs, lows, g, f)
        else:
            alt.append(f)

    # 第三步：确保最小跨度（idx 差 ≥ 2）；若差 < 2，做同类/异类裁决：
    norm: list[Fractal] = []
    for f in alt:
        if not norm:
            norm.append(f)
            continue
        g = norm[-1]
        if f.idx - g.idx >= 2:
            norm.append(f)
            continue
        # 只有差==1会来到这里；但 compress 已经去掉了“相邻抖动”，此处是兜底：
        if f.type == g.type:
            norm[-1] = _more_extreme_same_type(highs, lows, g, f)
        else:
            # 异类仍贴邻：为确定性与简洁，取更左（g）
            pass

    return norm


# ---------------- main APIs ----------------


def select_fractals_for_bi(df_eq: pd.DataFrame, cands: list[Fractal]) -> list[Fractal]:
    """
    输入：等价K DataFrame + 分型候选（通常来自 detect_fractal_candidates）
    输出：已满足“构笔”需求的分型序列（交替、间距≥2、去抖动）
    """
    highs = _tolist_float(df_eq["High"])
    lows = _tolist_float(df_eq["Low"])
    return _enforce_min_span_and_alternation(highs, lows, cands)


def build_bis(df_eq: pd.DataFrame, fractals_for_bi: list[Fractal]) -> list[Bi]:
    """
    用“已为构笔准备好的分型序列”生成笔：
      - 以“相邻两个分型”作为一笔的两端（必须是异类，且 idx 差 ≥ 2）
      - bottom→top 为 up；top→bottom 为 down
      - “延伸/替换”在上游分型选择阶段已实现（同类连发保留更极端）
    返回：List[Bi]，按时间升序。
    """
    if len(fractals_for_bi) < 2:
        return []

    bis: list[Bi] = []
    prev = fractals_for_bi[0]

    for cur in fractals_for_bi[1:]:
        if cur.idx - prev.idx < 2:
            # 规范化阶段理论上不会发生；这里防御性跳过
            continue
        if prev.type == "bottom" and cur.type == "top":
            bis.append(Bi(start=prev.idx, end=cur.idx, dir="up"))
            prev = cur  # 下一笔从当前顶开始
        elif prev.type == "top" and cur.type == "bottom":
            bis.append(Bi(start=prev.idx, end=cur.idx, dir="down"))
            prev = cur
        else:
            # 同类（应已在规范化阶段解决）；兜底：选择更极端者作为 prev
            highs = _tolist_float(df_eq["High"])
            lows = _tolist_float(df_eq["Low"])
            prev = _more_extreme_same_type(highs, lows, prev, cur)

    return bis


def detect_and_build_bis(df_eq: pd.DataFrame) -> list[Bi]:
    """
    便捷函数：从等价K直接得到“笔”。
      - detect_fractal_candidates → select_fractals_for_bi → build_bis
    """
    cands = detect_fractal_candidates(df_eq)
    frs = select_fractals_for_bi(df_eq, cands)
    return build_bis(df_eq, frs)


__all__ = ["Bi", "BiDir", "select_fractals_for_bi", "build_bis", "detect_and_build_bis"]
