# core/segment.py
# rules_version: v1.2.0
from __future__ import annotations

from dataclasses import dataclass
from math import log
from typing import Literal

import pandas as pd

from core.bi import Bi

SegDir = Literal["up", "down"]


@dataclass(frozen=True)
class Segment:
    start: int  # 等价K索引（取起始笔的 start）
    end: int  # 等价K索引（取结束笔的 end）
    dir: SegDir  # 'up' | 'down'


# ---------------- helpers ----------------


def _hl_lists(df_eq: pd.DataFrame) -> tuple[list[float], list[float]]:
    highs = df_eq["High"].astype(float).tolist()
    lows = df_eq["Low"].astype(float).tolist()
    return highs, lows


def _bi_price_delta_and_bars(bi: Bi, highs: list[float], lows: list[float]) -> tuple[float, int]:
    """
    计算一笔的价格跨度（与方向一致）和 K 数跨度。
    上笔：Δprice = High[end] - Low[start]
    下笔：Δprice = High[start] - Low[end]
    Δbars = end - start
    """
    if bi.dir == "up":
        dprice = highs[bi.end] - lows[bi.start]
    else:  # down
        dprice = highs[bi.start] - lows[bi.end]
    dbars = max(1, bi.end - bi.start)  # 保底避免 0，理论上 >=1
    return dprice, dbars


def _bi_momentum(bi: Bi, highs: list[float], lows: list[float]) -> float:
    """力度定义：M = Δprice / ln(Δbars + 1)"""
    dprice, dbars = _bi_price_delta_and_bars(bi, highs, lows)
    return dprice / log(dbars + 1.0)


def _bi_extreme_value(bi: Bi, highs: list[float], lows: list[float]) -> float:
    """
    该笔方向上的“极值”：
      - 上笔：取 High[end]（段上沿用以判断“创新高”）
      - 下笔：取 Low[end]  （段下沿用以判断“创新低”）
    """
    return highs[bi.end] if bi.dir == "up" else lows[bi.end]


def _dir_breaks_expected(prev_dir: SegDir, cur_dir: SegDir) -> bool:
    """
    方向破坏判定（保守口径）：
      - 线段扩展过程中，笔方向应交替；只要能形成合法线段，首尾方向一致。
      - 如果遇到任何不交替的笔（连续同向），认为方向破坏，及时截段。
    """
    return prev_dir == cur_dir


# ---------------- main API ----------------


def build_segments(df_eq: pd.DataFrame, bis: list[Bi]) -> list[Segment]:  # noqa: C901
    """
    输入：等价K序列 + 笔（时间升序）
    输出：线段 Segment 列表（start/end 为等价K索引；dir ∈ {'up','down'}）

    规则（v1.2）：
      - 至少 3 笔成段，方向取两端笔方向（在交替笔序中，首尾同向）。
      - 扩展策略：从最小 3 笔起段，向右逐笔尝试扩展；
        若出现：
          1) 背驰：价格创新高/新低，但力度 M 低于“上一同向离开笔” → 立刻截段（含当前笔）。
             * “上一同向离开笔”= 本段内**上一次**与段方向相同且**创出新极值**的那一笔。
          2) 方向破坏：遇到连续同向笔（不交替） → 截段（不含破坏笔）。
    """
    if len(bis) < 3:
        return []

    highs, lows = _hl_lists(df_eq)
    segs: list[Segment] = []

    i = 0
    n = len(bis)

    while i <= n - 3:
        i0, i1, i2 = i, i + 1, i + 2

        # 三笔必须交替（否则无法起段）
        if not (bis[i0].dir != bis[i1].dir and bis[i1].dir != bis[i2].dir):
            i += 1
            continue

        seg_dir: SegDir = bis[i0].dir  # 交替序列中 i0 与 i2 同向，即段方向

        # 初始化“上一同向离开笔”基准为 i0
        last_same_dir_extreme = _bi_extreme_value(bis[i0], highs, lows)
        last_same_dir_M = _bi_momentum(bis[i0], highs, lows)

        # 若 i2 与段方向同向，且“创出新极值”，则预更新基准到 i2
        if bis[i2].dir == seg_dir:
            i2_ext = _bi_extreme_value(bis[i2], highs, lows)
            if (seg_dir == "up" and i2_ext > last_same_dir_extreme) or (
                seg_dir == "down" and i2_ext < last_same_dir_extreme
            ):
                last_same_dir_extreme = i2_ext
                last_same_dir_M = _bi_momentum(bis[i2], highs, lows)
                # 注意：按保守口径，不在 i2 判背驰；只更新上一同向基准

        # 当前段的最右端（在 bis 下标）
        j = i2

        # 尝试向右扩展（保守口径：从第4笔开始检查背驰）
        k = i + 3
        while k < n:
            # 若不交替 → 方向破坏，截到 j，不含破坏笔 k
            if _dir_breaks_expected(bis[k - 1].dir, bis[k].dir):
                break

            # 仅在“新同向笔”上检查背驰
            if bis[k].dir == seg_dir:
                cur_extreme = _bi_extreme_value(bis[k], highs, lows)
                cur_M = _bi_momentum(bis[k], highs, lows)

                # 是否创出新高/新低（严格大/小于）
                is_new_extreme = (seg_dir == "up" and cur_extreme > last_same_dir_extreme) or (
                    seg_dir == "down" and cur_extreme < last_same_dir_extreme
                )

                if is_new_extreme:
                    # 与“上一同向离开笔”比较
                    if cur_M < last_same_dir_M:
                        # 背驰成立：将造成背驰的这笔也计入，再截段
                        j = k
                        break

                    # 未背驰：更新“上一同向离开笔”基准为当前这笔
                    last_same_dir_extreme = cur_extreme
                    last_same_dir_M = cur_M

            # 无背驰继续扩展
            j = k
            k += 1

        # 形成段（start/end 用等价K索引）
        segs.append(
            Segment(
                start=bis[i0].start,
                end=bis[j].end,
                dir=seg_dir,
            )
        )

        # 下一段从 j 开始重新寻找最小三笔（段与段首尾相接，不重叠）
        i = j

        # 防护推进（极端情况下 j 可能没推进到能组成新三笔的位置）
        if i == j and j < n - 1:
            i += 1

    return segs
