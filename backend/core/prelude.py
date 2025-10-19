# core/prelude.py 包含
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class MergeSpan:
    """原始索引区间（闭区间），用于溯源/可视化对齐。"""

    start: int
    end: int


def resolve_inclusions(df: pd.DataFrame) -> pd.DataFrame:
    """
    等价K合并（包含/吞没），只使用 High/Low。
    规则（v1.2）：
      - 若 High[i] ≤ High[i-1] 且 Low[i] ≥ Low[i-1] → 当前K被包含 → 合并；
      - 若 High[i] ≥ High[i-1] 且 Low[i] ≤ Low[i-1] → 当前K包含前一K → 合并；
    合并后：
      - High = max(prev.High, cur.High)
      - Low  = min(prev.Low,  cur.Low)
      - 索引（以及代表日期）取最左（保持确定性）
    单向线性扫描一次（O(N)）。

    输入列至少需要：["Date","High","Low"]；其余列忽略。
    返回列：["Date","High","Low","src_start","src_end"]
      - Date：取区间起点行的 Date（最左）
      - src_start/src_end：原始 df 的位置索引闭区间，用于后续映射
    """
    if len(df) == 0:
        return df.loc[:, ["Date", "High", "Low"]].assign(src_start=[], src_end=[]).copy()

    # 仅取必要列，并确保索引从 0 开始连续（src 索引基于此）
    base = df.reset_index(drop=True).loc[:, ["Date", "High", "Low"]].copy()

    # 工作栈存放已合并等价K
    # 每个元素：dict(Date, High, Low, src_start, src_end)
    merged: list[dict] = []

    for i, row in base.iterrows():
        cur_high = float(row["High"])
        cur_low = float(row["Low"])
        cur_date = row["Date"]

        if not merged:
            merged.append(
                {
                    "Date": cur_date,
                    "High": cur_high,
                    "Low": cur_low,
                    "src_start": i,
                    "src_end": i,
                }
            )
            continue

        last = merged[-1]
        last_high = float(last["High"])
        last_low = float(last["Low"])

        # 包含 / 吞没 判定（等价价位会同时满足两条，合并结果一致）
        cur_inside_prev = (cur_high <= last_high) and (cur_low >= last_low)
        cur_engulfs_prev = (cur_high >= last_high) and (cur_low <= last_low)

        if cur_inside_prev or cur_engulfs_prev:
            # 合并：索引/日期取最左（保持不变）
            last["High"] = max(last_high, cur_high)
            last["Low"] = min(last_low, cur_low)
            last["src_end"] = i  # 向右扩展区间
        else:
            # 不包含：作为新的等价K
            merged.append(
                {
                    "Date": cur_date,
                    "High": cur_high,
                    "Low": cur_low,
                    "src_start": i,
                    "src_end": i,
                }
            )

    out = pd.DataFrame(merged, columns=["Date", "High", "Low", "src_start", "src_end"])
    return out.reset_index(drop=True)
