# core/zhongshu.py
# rules_version: v1.2.0
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from core.bi import Bi

MoveDir = Literal["up", "down", "flat"]


@dataclass(frozen=True)
class Zhongshu:
    """
    v1.2 中枢定义：
      - 至少三笔的价格区间交叠：UpperZ > LowerZ → 成立
      - 后续笔若与当前区间仍有交叠 → 延伸（区间取交集、可能上/下移并收敛）
      - 若出现不交叠：
          · confirm_leave=False：首次不交叠立即离开（中枢于前一笔结束）
          · confirm_leave=True ：需“连续两笔不交叠”才确认离开；若中间重新交叠则视作假离开继续延伸
    索引均为等价K（resolve_inclusions 后）空间。
    """

    start_bi_idx: int  # 在 bis 列表中的起始笔索引（含）
    end_bi_idx: int  # 在 bis 列表中的结束笔索引（含）
    price_range: tuple[float, float]  # (LowerZ, UpperZ) —— 最终收敛后的有效带
    legs: list[tuple[int, int]]  # 组成该中枢的笔端点 [(bi.start, bi.end), ...]
    move: MoveDir  # 相对“初始三笔交集”整体上移/下移/基本不变


# ---------------- helpers ----------------


def _hl_lists(df_eq: pd.DataFrame):
    highs = df_eq["High"].astype(float).tolist()
    lows = df_eq["Low"].astype(float).tolist()
    return highs, lows


def _bi_band(bi: Bi, highs: list[float], lows: list[float]) -> tuple[float, float]:
    # 用端点极值近似“一笔的覆盖带”
    lo = min(lows[bi.start], lows[bi.end])
    hi = max(highs[bi.start], highs[bi.end])
    return (lo, hi)


def _triple_overlap_band(
    b1: Bi, b2: Bi, b3: Bi, highs: list[float], lows: list[float]
) -> tuple[float, float]:
    """
    三笔交叠后的中枢带：
      UpperZ = min(highs_of_three)
      LowerZ = max(lows_of_three)
    成立条件：UpperZ > LowerZ（严格）
    """
    l1, h1 = _bi_band(b1, highs, lows)
    l2, h2 = _bi_band(b2, highs, lows)
    l3, h3 = _bi_band(b3, highs, lows)
    upper = min(h1, h2, h3)
    lower = max(l1, l2, l3)
    return (lower, upper)


def _overlap_with_band(
    bi: Bi, band: tuple[float, float], highs: list[float], lows: list[float]
) -> tuple[bool, tuple[float, float]]:
    """检查单笔与当前中枢带是否有交叠；若有，返回交集后的新带。"""
    lo, hi = _bi_band(bi, highs, lows)
    cur_low, cur_high = band
    new_low = max(cur_low, lo)
    new_high = min(cur_high, hi)
    if new_high > new_low:  # 必须严格相交
        return True, (new_low, new_high)
    return False, band


def _band_move_dir(
    initial: tuple[float, float], final: tuple[float, float], eps: float = 1e-9
) -> MoveDir:
    li, ui = initial
    lf, uf = final
    # 上下界都同向明显移动才认定 up/down；否则 flat
    if (lf - li) > eps and (uf - ui) > eps:
        return "up"
    if (li - lf) > eps and (ui - uf) > eps:
        return "down"
    return "flat"


# ---------------- main API ----------------


def build_zhongshus(
    df_eq: pd.DataFrame,
    bis: list[Bi],
    *,
    confirm_leave: bool = True,  # True：连续两笔不交叠确认离开（抗假离开）
    reuse_tail_bi: bool = True,  # True：下一轮扫描复用上一中枢的“尾笔”（相接中枢）
) -> list[Zhongshu]:
    """
    输入：等价K序列 + 笔（升序）
    输出：中枢列表（含 price_range/move/legs）
    """
    if len(bis) < 3:
        return []

    highs, lows = _hl_lists(df_eq)
    out: list[Zhongshu] = []

    i = 0
    n = len(bis)

    while i <= n - 3:
        b1, b2, b3 = bis[i], bis[i + 1], bis[i + 2]
        lower, upper = _triple_overlap_band(b1, b2, b3, highs, lows)
        if not (upper > lower):
            i += 1
            continue

        # —— 成立：初始化当前中枢 —— #
        init_band = (lower, upper)
        cur_low, cur_high = lower, upper
        start_idx = i
        end_idx = i + 2
        legs: list[tuple[int, int]] = [
            (b1.start, b1.end),
            (b2.start, b2.end),
            (b3.start, b3.end),
        ]

        # —— 延伸/离开确认 —— #
        k = i + 3
        pending_leave = False  # 首次不交叠的“待确认离开”标记
        while k < n:
            ok, new_band = _overlap_with_band(bis[k], (cur_low, cur_high), highs, lows)
            if ok:
                # 曾出现一次不交叠但又回到区间 → 取消待确认，继续延伸
                pending_leave = False
                cur_low, cur_high = new_band
                end_idx = k
                legs.append((bis[k].start, bis[k].end))
                k += 1
            else:
                if not confirm_leave:
                    break  # 首次不交叠即离开
                if not pending_leave:
                    # 第一次不交叠：标记并观察下一笔
                    pending_leave = True
                    k += 1
                    continue
                else:
                    # 连续第二笔仍不交叠 → 离开确认
                    break

        # —— move：用整段 legs 的包络相对初始交集判断 —— #
        lo_final = min(lows[p] for p, _ in legs)
        hi_final = max(highs[q] for _, q in legs)
        move = _band_move_dir(init_band, (lo_final, hi_final))

        out.append(
            Zhongshu(
                start_bi_idx=start_idx,
                end_bi_idx=end_idx,
                price_range=(cur_low, cur_high),  # 最终收敛后的有效带
                legs=legs,
                move=move,
            )
        )

        # —— 下一窗口步进策略 —— #
        # True：i=end_idx（复用尾笔，允许中枢相接）
        # False：i=end_idx+1（不复用，窗口从下一笔开始）
        i = end_idx if reuse_tail_bi else (end_idx + 1)

    return out


__all__ = ["Zhongshu", "MoveDir", "build_zhongshus"]
