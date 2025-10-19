# core/tests/test_prelude.py
import pandas as pd

from core.prelude import resolve_inclusions


def _mk(df_list):
    """快速构建仅含 Date/High/Low 的 DataFrame。"""
    return pd.DataFrame(df_list)


def test_no_inclusion_keeps_length():
    df = _mk(
        [
            {"Date": "2025-10-10", "High": 11.0, "Low": 10.0},
            {"Date": "2025-10-11", "High": 12.5, "Low": 10.2},  # 不包含前一条
            {"Date": "2025-10-12", "High": 13.0, "Low": 10.8},  # 不包含前一条
        ]
    )
    out = resolve_inclusions(df)
    assert len(out) == 3
    # src 索引一一对应
    assert out.loc[0, "src_start"] == 0 and out.loc[0, "src_end"] == 0
    assert out.loc[1, "src_start"] == 1 and out.loc[1, "src_end"] == 1
    assert out.loc[2, "src_start"] == 2 and out.loc[2, "src_end"] == 2


def test_current_inside_previous_merges():
    # 第二根完全被第一根包含 → 合为一根
    # 第三根又吞没合并后的第一根 → 继续合并 → 最终只剩一根
    df = _mk(
        [
            {"Date": "D1", "High": 12.0, "Low": 10.0},
            {"Date": "D2", "High": 11.0, "Low": 10.5},  # inside D1
            {"Date": "D3", "High": 12.5, "Low": 9.8},  # engulfs merged(D1+D2)
        ]
    )
    out = resolve_inclusions(df)
    assert len(out) == 1
    # 日期/索引取最左，区间扩展到 [0,2]，极值为区间内 max/min
    assert out.loc[0, "Date"] == "D1"
    assert (out.loc[0, "src_start"], out.loc[0, "src_end"]) == (0, 2)
    assert out.loc[0, "High"] == 12.5
    assert out.loc[0, "Low"] == 9.8


def test_current_engulfs_previous_merges():
    # 第二根吞没第一根 → 合为一根，日期取最左（第一根的日期）
    df = _mk(
        [
            {"Date": "D1", "High": 11.0, "Low": 10.2},
            {"Date": "D2", "High": 12.2, "Low": 9.8},  # engulfs D1
            {
                "Date": "D3",
                "High": 12.0,
                "Low": 10.0,
            },  # inside 合并后 → inside → 继续合并
        ]
    )
    out = resolve_inclusions(df)
    assert len(out) == 1
    assert out.loc[0, "Date"] == "D1"  # 最左索引保留
    assert (out.loc[0, "src_start"], out.loc[0, "src_end"]) == (0, 2)
    # 合并后的极值：
    assert out.loc[0, "High"] == 12.2
    assert out.loc[0, "Low"] == 9.8


def test_equal_bars_should_merge_and_keep_left_index():
    # 前两根完全等价 → 合并；第三根吞没前两根 → 继续合并 → 最终只剩一根
    df = _mk(
        [
            {"Date": "D1", "High": 10.0, "Low": 9.0},
            {
                "Date": "D2",
                "High": 10.0,
                "Low": 9.0,
            },  # equal（inside & engulfs 同时成立）
            {"Date": "D3", "High": 10.5, "Low": 8.8},  # engulfs merged(D1+D2)
        ]
    )
    out = resolve_inclusions(df)
    assert len(out) == 1
    assert out.loc[0, "Date"] == "D1"  # 取最左
    assert (out.loc[0, "src_start"], out.loc[0, "src_end"]) == (0, 2)
    assert out.loc[0, "High"] == 10.5
    assert out.loc[0, "Low"] == 8.8
