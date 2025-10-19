# core/tests/test_fractals.py
import pandas as pd

from core.fractals import detect_fractals


def _mk(vals):
    """传入 [{'High':..,'Low':..}, ...]，自动补 Date。"""
    df = pd.DataFrame(vals)
    if "Date" not in df.columns:
        df["Date"] = [f"D{i}" for i in range(len(df))]
    return df[["Date", "High", "Low"]]


def test_simple_top_and_bottom():
    #     i : 0     1     2     3     4
    df = _mk(
        [
            {"High": 10, "Low": 8},
            {
                "High": 12,
                "Low": 9,
            },  # 顶：此处 High=12 为三者最大且最左；Low=9 为三者最大且最左
            {"High": 11, "Low": 8.5},
            {
                "High": 10.5,
                "Low": 7.8,
            },  # 底：此处 Low=7.8 为最小且最左；High=10.5 为最小且最左
            {"High": 11, "Low": 8.0},
        ]
    )
    frs = detect_fractals(df)
    assert [(f.idx, f.type) for f in frs] == [(1, "top"), (3, "bottom")]


def test_tie_leftmost_for_top():
    # 顶分型平价取最左：
    # tri @ i=1: High = [12, 12, 11] → 最大 12 的最左索引是 0（→不是 i）
    #            Low  = [ 9,  9,  8] → 最大  9 的最左索引是 0（→不是 i）
    # 所以 i=1 不是顶；i=2 再看：High=[12,11,11], 最大最左=0（索引不是 1），也不是顶。
    df = _mk(
        [
            {"High": 12, "Low": 9},
            {"High": 12, "Low": 9},
            {"High": 11, "Low": 8},
            {"High": 10, "Low": 7},
        ]
    )
    frs = detect_fractals(df)
    # 不应误判为顶
    assert all(f.type != "top" for f in frs)


def test_tie_leftmost_for_bottom():
    # 底分型平价取最左：
    # tri @ i=1: Low=[8,8,9] → 最小 8 的最左索引=0（→不是 i），High=[10,10,11] → 最小最左=0
    # 所以 i=1 不是底。整体不应产生底分型。
    df = _mk(
        [
            {"High": 10, "Low": 8},
            {"High": 10, "Low": 8},
            {"High": 11, "Low": 9},
            {"High": 12, "Low": 10},
        ]
    )
    frs = detect_fractals(df)
    assert all(f.type != "bottom" for f in frs)


def test_length_less_than_3_returns_empty():
    df = _mk([{"High": 10, "Low": 9}, {"High": 11, "Low": 8.5}])
    assert detect_fractals(df) == []
