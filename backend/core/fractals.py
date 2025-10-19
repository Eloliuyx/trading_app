# core/fractals.py
# rules_version: v1.2.0
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

FractalType = Literal["top", "bottom"]
RULES_VERSION = "v1.2.0"


@dataclass(frozen=True)
class Fractal:
    idx: int  # 在等价K序列中的索引（df_eq.reset_index(drop=True) 后的下标）
    type: FractalType  # 'top' | 'bottom'


# ---------- helpers ----------


def _ensure_columns(df: pd.DataFrame, cols=("High", "Low")) -> None:
    for c in cols:
        if c not in df.columns:
            raise ValueError(f"df_eq 缺少列: {c}")


def _tolist_float(series: pd.Series) -> list[float]:
    return series.astype(float).tolist()


def _is_top_candidate(highs: list[float], lows: list[float], j: int) -> bool:
    tri_h = [highs[j - 1], highs[j], highs[j + 1]]
    tri_l = [lows[j - 1], lows[j], lows[j + 1]]
    return (_leftmost_index_of_max(tri_h) == 1) and (_leftmost_index_of_max(tri_l) == 1)


def _is_bottom_candidate(highs: list[float], lows: list[float], j: int) -> bool:
    tri_h = [highs[j - 1], highs[j], highs[j + 1]]
    tri_l = [lows[j - 1], lows[j], lows[j + 1]]
    return (_leftmost_index_of_min(tri_l) == 1) and (_leftmost_index_of_min(tri_h) == 1)


# 严格“平价取最左”的工具
def _leftmost_index_of_max(values: list[float]) -> int:
    m = max(values)
    for i, v in enumerate(values):
        if v == m:
            return i
    raise RuntimeError("unreachable")


def _leftmost_index_of_min(values: list[float]) -> int:
    m = min(values)
    for i, v in enumerate(values):
        if v == m:
            return i
    raise RuntimeError("unreachable")


def _more_extreme_same_type(
    highs: list[float], lows: list[float], a: Fractal, b: Fractal
) -> Fractal:
    """与 bi.py 等价的本地实现，避免循环依赖；平价取左（a）。"""
    if a.type != b.type:
        return a
    if a.type == "top":
        if highs[a.idx] > highs[b.idx]:
            return a
        if highs[b.idx] > highs[a.idx]:
            return b
        if lows[a.idx] > lows[b.idx]:
            return a
        if lows[b.idx] > lows[a.idx]:
            return b
        return a
    else:  # bottom
        if lows[a.idx] < lows[b.idx]:
            return a
        if lows[b.idx] < lows[a.idx]:
            return b
        if highs[a.idx] < highs[b.idx]:
            return a
        if highs[b.idx] < highs[a.idx]:
            return b
        return a


# ============= 供 Bi 阶段调用的压缩工具（不在分型阶段默认启用） =============


def compress_fractals_for_bi(
    highs: list[float], lows: list[float], cands: list[Fractal]
) -> list[Fractal]:
    """
    为“笔（Bi）”构建提供的候选压缩工具：
    - 解决相邻（idx 差 1）的同类/异类抖动（同类取更极端，异类取更左）
    - 可多轮压缩直到不再相邻
    - 不强制“中心间距 >= 2”的最终约束（由 Bi 内部统一把关）
    """
    if not cands:
        return []

    cands = sorted(cands, key=lambda f: f.idx)

    changed = True
    out = cands
    while changed:
        changed = False
        tmp: list[Fractal] = []
        i = 0
        while i < len(out):
            a = out[i]
            if i + 1 < len(out) and out[i + 1].idx == a.idx + 1:
                b = out[i + 1]
                if a.type == b.type:
                    chosen = _more_extreme_same_type(highs, lows, a, b)
                    tmp.append(chosen)
                else:
                    # 异类相邻：为确定性取更左（a）
                    tmp.append(a)
                i += 2
                changed = True
            else:
                tmp.append(a)
                i += 1
        out = tmp

    return out


# ============= 主 API：候选分型 & 便捷入口 =============


def detect_fractal_candidates(df_eq: pd.DataFrame) -> list[Fractal]:
    """
    只按三连K定义识别“候选分型”，不做最小跨度/相邻冲突消解。
    规则（v1.2）：
      顶分型（允许等号）：
        High[i] == max(High[i-1], High[i], High[i+1]) 且
        Low[i]  == max(Low[i-1],  Low[i],  Low[i+1])
      底分型（允许等号）：
        Low[i]  == min(Low[i-1],  Low[i],  Low[i+1]) 且
        High[i] == min(High[i-1], High[i], High[i+1])
      平台（顶/底同时为真）→ 跳过（无信息增益）
    """
    _ensure_columns(df_eq, ("High", "Low"))
    n = len(df_eq)
    if n < 3:
        return []

    highs = _tolist_float(df_eq["High"])
    lows = _tolist_float(df_eq["Low"])

    cands: list[Fractal] = []
    for i in range(1, n - 1):
        top_cand = _is_top_candidate(highs, lows, i)
        bot_cand = _is_bottom_candidate(highs, lows, i)
        if top_cand and bot_cand:
            continue
        if top_cand:
            cands.append(Fractal(idx=i, type="top"))
        elif bot_cand:
            cands.append(Fractal(idx=i, type="bottom"))

    return sorted(cands, key=lambda f: f.idx)


def detect_fractals(df_eq: pd.DataFrame, *, precompress: bool = False) -> list[Fractal]:
    """
    便捷入口：
      - 默认（precompress=False）：返回纯“候选分型”（供 Bi 阶段使用），严格符合 v1.2。
      - 调试（precompress=True）：对候选做一次相邻压缩，便于肉眼观测。
    """
    cands = detect_fractal_candidates(df_eq)
    if not precompress:
        return cands

    highs = _tolist_float(df_eq["High"])
    lows = _tolist_float(df_eq["Low"])
    return compress_fractals_for_bi(highs, lows, cands)


__all__ = [
    "Fractal",
    "FractalType",
    "RULES_VERSION",
    "detect_fractal_candidates",
    "compress_fractals_for_bi",
    "detect_fractals",
]
