# core/tests/test_recommend.py
import pandas as pd

from core.recommend import advise_for_today, compute_buy_strength
from core.segment import Segment
from core.shi import ShiResult
from core.zhongshu import Zhongshu


def _mk_eq(vals):
    df = pd.DataFrame(vals)
    if "Date" not in df.columns:
        df["Date"] = [f"D{i}" for i in range(len(df))]
    return df[["Date", "High", "Low"]]


def test_score_components_and_reason_texts():
    df = _mk_eq(
        [
            {"High": 10.8, "Low": 10.0},  # 0
            {"High": 11.2, "Low": 10.6},  # 1
            {"High": 11.1, "Low": 10.7},  # 2
        ]
    )
    segs = [Segment(0, 1, "up"), Segment(1, 2, "down"), Segment(1, 2, "up")]
    zs = [Zhongshu(0, 2, (10.6, 10.9), [(0, 1), (1, 1), (1, 2)], "up")]
    shi = ShiResult(
        class_="中枢上破进行中",
        evidence=[],
        momentum=0.5,
        risk=0.3,
        confidence=0.7,
        last_segment_index=2,
        last_zhongshu_index=0,
    )

    score, comps, reasons, inv = compute_buy_strength(df, segs, zs, shi)
    assert 0.0 <= score <= 1.0
    assert set(comps.keys()) == set("ABCDE")
    assert isinstance(reasons, list) and len(reasons) >= 1
    assert "上沿" in inv


def test_advice_mapping():
    df = _mk_eq(
        [
            {"High": 10.8, "Low": 10.0},  # 0
            {"High": 11.2, "Low": 10.6},  # 1
            {"High": 11.3, "Low": 10.8},  # 2
        ]
    )
    segs = [Segment(0, 1, "up"), Segment(1, 2, "down"), Segment(1, 2, "up")]
    zs = [Zhongshu(0, 2, (10.6, 10.9), [(0, 1), (1, 1), (1, 2)], "up")]
    shi = ShiResult(
        class_="中枢上破进行中",
        evidence=[],
        momentum=0.7,
        risk=0.2,
        confidence=0.8,
        last_segment_index=2,
        last_zhongshu_index=0,
    )

    rec = advise_for_today(df, segs, zs, shi)
    assert rec.action in ("买", "观察买点", "回避", "止盈", "持有")
    assert 0.0 <= rec.buy_strength <= 1.0
    assert len(rec.rationale) > 0
