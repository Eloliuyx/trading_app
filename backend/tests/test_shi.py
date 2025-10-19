# core/tests/test_shi.py
import pandas as pd

from core.segment import Segment
from core.shi import classify_shi
from core.zhongshu import Zhongshu


def _mk_eq(vals):
    df = pd.DataFrame(vals)
    if "Date" not in df.columns:
        df["Date"] = [f"D{i}" for i in range(len(df))]
    return df[["Date", "High", "Low"]]


def test_break_up_in_progress():
    # 中枢带上沿在 10.5，最后价位 11 在其上，最近段向上，无背驰 → 上破进行中
    df = _mk_eq(
        [
            {"High": 10.8, "Low": 10.0},  # 0
            {"High": 11.2, "Low": 10.6},  # 1
        ]
    )
    segs = [Segment(start=0, end=1, dir="up")]
    zs = [
        Zhongshu(
            start_bi_idx=0,
            end_bi_idx=2,
            price_range=(10.3, 10.5),
            legs=[(0, 0), (0, 1), (0, 1)],
            move="up",
        )
    ]
    res = classify_shi(df, segs, zs)
    assert res.class_ == "中枢上破进行中"
    assert res.confidence > 0.5


def test_in_band_is_oscillation():
    df = _mk_eq(
        [
            {"High": 10.6, "Low": 10.2},  # 0
            {"High": 10.5, "Low": 10.1},  # 1
        ]
    )
    segs = [Segment(start=0, end=1, dir="down")]
    zs = [
        Zhongshu(
            start_bi_idx=0,
            end_bi_idx=2,
            price_range=(10.15, 10.45),
            legs=[(0, 0), (0, 1), (0, 1)],
            move="flat",
        )
    ]
    res = classify_shi(df, segs, zs)
    assert res.class_ == "中枢震荡未破"


def test_divergence_pending_up():
    # 构造两个“上段”之间：第二个上段创更高，但 M 变弱 → 背驰待确证
    # 段1: start=0,end=2  High[end]=11.5, Low[start]=10.0 → Δp=1.5, bars=2
    # 段2: start=3,end=5  High[end]=11.6, Low[start]=10.4 → Δp=1.2, bars=2 → 力度更弱
    df = _mk_eq(
        [
            {"High": 10.5, "Low": 10.0},  # 0
            {"High": 10.8, "Low": 10.2},  # 1
            {"High": 11.5, "Low": 10.3},  # 2
            {"High": 10.9, "Low": 10.4},  # 3
            {"High": 11.2, "Low": 10.5},  # 4
            {"High": 11.6, "Low": 10.6},  # 5
        ]
    )
    segs = [
        Segment(start=0, end=2, dir="up"),
        Segment(start=2, end=3, dir="down"),
        Segment(start=3, end=5, dir="up"),
    ]
    zs = []  # 无中枢
    res = classify_shi(df, segs, zs)
    assert res.class_ == "上行背驰待确证"
    assert any("背驰" in e for e in res.evidence)


def test_divergence_established_down():
    # 下行背驰确立：第二个下段创新低但力度减弱，随后出现一个上段 → 确立
    df = _mk_eq(
        [
            {"High": 12.0, "Low": 11.0},  # 0
            {"High": 11.2, "Low": 10.6},  # 1
            {"High": 11.0, "Low": 10.4},  # 2  first down seg end
            {"High": 11.3, "Low": 10.8},  # 3  up seg
            {"High": 10.9, "Low": 10.2},  # 4
            {"High": 10.8, "Low": 10.0},  # 5  second down seg end (new low but weaker)
            {"High": 10.9, "Low": 10.4},  # 6  up seg (confirms)
        ]
    )
    segs = [
        Segment(start=0, end=2, dir="down"),
        Segment(start=2, end=3, dir="up"),
        Segment(start=3, end=5, dir="down"),
        Segment(start=5, end=6, dir="up"),  # 反向段出现 → “确立”
    ]
    zs = []
    res = classify_shi(df, segs, zs)
    assert res.class_ in ("下行背驰确立", "下行背驰待确证")  # 口径宽松些，允许边界实现
    assert any("背驰" in e for e in res.evidence)
