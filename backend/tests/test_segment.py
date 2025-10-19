# core/tests/test_segment.py
import pandas as pd

from core.bi import Bi
from core.segment import build_segments


def _mk_eq(vals):
    df = pd.DataFrame(vals)
    if "Date" not in df.columns:
        df["Date"] = [f"D{i}" for i in range(len(df))]
    return df[["Date", "High", "Low"]]


def test_basic_segment_without_divergence():
    # 交替的 5 笔，无背驰 → 合并成一段（到最后一笔）
    df = _mk_eq(
        [
            {"High": 10, "Low": 8},  # 0
            {"High": 11, "Low": 9},  # 1
            {"High": 12, "Low": 9.2},  # 2
            {"High": 11.2, "Low": 9.0},  # 3
            {"High": 12.5, "Low": 9.5},  # 4
            {"High": 11.5, "Low": 9.1},  # 5
            {"High": 12.8, "Low": 9.6},  # 6
        ]
    )
    bis = [
        Bi(0, 1, "up"),
        Bi(2, 3, "down"),
        Bi(4, 5, "up"),
        Bi(5, 6, "down"),
        Bi(6, 6, "up"),
    ]
    segs = build_segments(df, bis)
    assert len(segs) == 1
    s = segs[0]
    assert s.dir == "up"
    assert s.start == bis[0].start and s.end == bis[-1].end  # 0..6


def test_divergence_cuts_segment():
    """
    构造：第二个“同向上笔”较弱（但先不检查），
    再下一根同向上笔继续创新高且更弱 → 在这根处判背驰。
    按保守口径（从第4笔开始检查），背驰应在最后一根 up 判定。
    """
    df = _mk_eq(
        [
            {"High": 10, "Low": 8},  # 0
            {"High": 11.5, "Low": 9.0},  # 1  up  M1 = 3.5/ln2
            {"High": 11.0, "Low": 9.2},  # 2  down
            {"High": 12.0, "Low": 9.4},  # 3  up  M2 = 2.6/ln2 (弱于 M1)，但此时不检查
            {"High": 11.6, "Low": 9.5},  # 4  down
            {
                "High": 12.1,
                "Low": 9.6,
            },  # 5  up  新高但仍较弱（与上一同向 i2 比较将更弱）
            {"High": 11.7, "Low": 9.7},  # 6  down
            {"High": 12.2, "Low": 9.7},  # 7  up  再创新高，Δ=2.5<2.6 → 背驰在这里成立
        ]
    )
    bis = [
        Bi(0, 1, "up"),
        Bi(2, 3, "down"),
        Bi(4, 5, "up"),
        Bi(5, 6, "down"),
        Bi(6, 7, "up"),
    ]
    segs = build_segments(df, bis)
    assert len(segs) >= 1
    s0 = segs[0]
    assert s0.dir == "up"
    # 段应包含造成背驰的最后这笔 up（end == 7）
    assert s0.start == 0 and s0.end == 7


def test_less_than_three_bis_returns_empty():
    df = _mk_eq(
        [
            {"High": 10, "Low": 8},
            {"High": 11, "Low": 9},
            {"High": 12, "Low": 10},
        ]
    )
    bis = [Bi(0, 1, "up"), Bi(1, 2, "down")]
    assert build_segments(df, bis) == []


def test_direction_break_stops_extension():
    # 中途人为插入两笔同向 → 方向破坏 → 截段（不包含破坏笔）
    df = _mk_eq(
        [
            {"High": 10, "Low": 8},  # 0
            {"High": 11.3, "Low": 9.0},  # 1
            {"High": 11.0, "Low": 9.1},  # 2
            {"High": 12.2, "Low": 9.4},  # 3
            {"High": 11.5, "Low": 9.2},  # 4
            {"High": 12.4, "Low": 9.6},  # 5
            {"High": 12.8, "Low": 9.8},  # 6
        ]
    )
    # up, down, up 可以起段；随后再来一个 up（不交替） → 方向破坏
    bis = [
        Bi(0, 1, "up"),
        Bi(2, 3, "down"),
        Bi(4, 5, "up"),
        Bi(5, 6, "up"),  # 破坏：连续同向
    ]
    segs = build_segments(df, bis)
    assert len(segs) >= 1
    s0 = segs[0]
    assert s0.dir == "up"
    # 段应结束在第三笔（index=2）的 end=5，不包含破坏笔
    assert s0.start == 0 and s0.end == 5


def test_no_divergence_when_no_new_extreme():
    # 同向上笔未创出新高，即使 M 变弱也不应判背驰；直到后面真正新高才进入比较
    df = _mk_eq(
        [
            {"High": 10, "Low": 8},  # 0
            {"High": 11.0, "Low": 9.0},  # 1  up基准：ext=11.0, M1
            {"High": 10.5, "Low": 9.2},  # 2  down
            {"High": 10.9, "Low": 9.1},  # 3  up（未超过 11.0）M 更小，但不应背驰
            {"High": 10.7, "Low": 9.0},  # 4  down
            {"High": 11.2, "Low": 9.3},  # 5  up（此处新高才生效比较；若弱则此处才截）
        ]
    )
    bis = [
        Bi(0, 1, "up"),
        Bi(2, 3, "down"),
        Bi(3, 3, "up"),
        Bi(4, 4, "down"),
        Bi(5, 5, "up"),
    ]
    segs = build_segments(df, bis)
    # 不应在 i=3 就被截断；至少包含到 i=5
    assert segs[0].end == 5


def test_divergence_compares_with_previous_same_dir_only():
    """
    第一上笔强（M1），第二上笔更强（M2 > M1，且预更新为“上一同向离开笔”），
    第三上笔再创新高但力度 M3 < M2 → 仅与“上一同向”（第二）比较而判背驰，end == 5。
    """
    df = _mk_eq(
        [
            {"High": 10, "Low": 8},  # 0
            {"High": 11.5, "Low": 9.0},  # 1  up  M1 = 3.5/ln2
            {"High": 11.0, "Low": 9.2},  # 2  down
            {"High": 13.1, "Low": 9.4},  # 3  up  M2 = 3.7/ln2 (>M1) → 预更新“上一同向”
            {"High": 11.6, "Low": 9.5},  # 4  down
            {"High": 13.2, "Low": 9.7},  # 5  up  新高但 M3 = 3.5/ln2 < M2 → 背驰
        ]
    )
    bis = [
        Bi(0, 1, "up"),
        Bi(2, 3, "down"),
        Bi(3, 3, "up"),
        Bi(4, 4, "down"),
        Bi(5, 5, "up"),
    ]
    segs = build_segments(df, bis)
    assert segs[0].end == 5
