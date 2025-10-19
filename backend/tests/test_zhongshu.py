# core/tests/test_zhongshu.py
import pandas as pd

from core.bi import Bi
from core.zhongshu import build_zhongshus


def _mk_eq(vals):
    df = pd.DataFrame(vals)
    if "Date" not in df.columns:
        df["Date"] = [f"D{i}" for i in range(len(df))]
    return df[["Date", "High", "Low"]]


def test_triple_overlap_establish_and_extend_with_confirm_leave():
    """
    场景：
      - 前三笔严格交叠 → 中枢成立
      - 第四笔不交叠（假离开）
      - 第五笔重新回到交叠 → 应继续延伸（confirm_leave=True）
    期望：
      - 只有一个中枢
      - end_bi_idx 至少延伸到第 5 笔
    """
    df = _mk_eq(
        [
            {"High": 12.0, "Low": 8.0},  # 0
            {"High": 11.3, "Low": 9.0},  # 1
            {"High": 11.1, "Low": 9.2},  # 2  初始交集 ~ [9.2, 11.1]
            {"High": 12.0, "Low": 11.3},  # 3  不交叠（向上探出）
            {"High": 11.0, "Low": 9.4},  # 4  重新交叠 → 延伸
            {"High": 11.0, "Low": 9.5},  # 5  继续延伸
        ]
    )
    # 为简洁，笔用 start=end 的“等价K端点笔”
    bis = [Bi(i, i, "up" if i % 2 == 0 else "down") for i in range(len(df))]
    zs = build_zhongshus(df, bis, confirm_leave=True, reuse_tail_bi=False)
    assert len(zs) == 1
    z = zs[0]
    assert z.start_bi_idx == 0 and z.end_bi_idx >= 4
    lo, hi = z.price_range
    assert hi > lo
    assert z.move in ("flat", "up", "down")  # 交集口径下一般为 flat


def test_leave_confirmed_only_after_two_consecutive_non_overlaps():
    """
    场景：
      - 前三笔交叠成立
      - 第四笔不交叠
      - 第五笔仍不交叠 → 连续两笔不交叠，确认离开
    期望：
      - 中枢在第三笔（idx=2）结束（即 end_bi_idx == 2）
    """
    df = _mk_eq(
        [
            {"High": 12.0, "Low": 8.0},  # 0
            {"High": 11.3, "Low": 9.0},  # 1
            {"High": 11.1, "Low": 9.2},  # 2  初始交集 ~ [9.2, 11.1]
            {"High": 12.0, "Low": 11.3},  # 3  不交叠 #1
            {"High": 12.2, "Low": 11.4},  # 4  不交叠 #2 → 确认离开
            {"High": 11.0, "Low": 9.5},  # 5  后续与第一中枢无关
        ]
    )
    bis = [Bi(i, i, "up" if i % 2 == 0 else "down") for i in range(len(df))]
    zs = build_zhongshus(df, bis, confirm_leave=True, reuse_tail_bi=False)
    assert len(zs) >= 1
    z0 = zs[0]
    assert z0.end_bi_idx == 2
    lo, hi = z0.price_range
    assert hi > lo


def test_immediate_leave_when_confirm_leave_is_false():
    """
    confirm_leave=False 时，首次不交叠即离开。
    """
    df = _mk_eq(
        [
            {"High": 12.0, "Low": 8.0},  # 0
            {"High": 11.3, "Low": 9.0},  # 1
            {"High": 11.1, "Low": 9.2},  # 2  初始交集 ~ [9.2, 11.1]
            {"High": 12.0, "Low": 11.3},  # 3  首次不交叠 → 立即离开
            {"High": 11.0, "Low": 9.4},  # 4  回到交叠也不应再计入该中枢
        ]
    )
    bis = [Bi(i, i, "up" if i % 2 == 0 else "down") for i in range(len(df))]
    zs = build_zhongshus(df, bis, confirm_leave=False, reuse_tail_bi=False)
    assert len(zs) == 1
    assert zs[0].end_bi_idx == 2


def test_reuse_tail_bi_can_yield_same_or_more_zhongshu_than_non_reuse():
    """
    验证 reuse_tail_bi=True（相接中枢可重用上一中枢的尾笔）时，
    中枢数量不会少于 reuse_tail_bi=False（更保守推进）的结果。
    """
    df = _mk_eq(
        [
            {"High": 12.0, "Low": 8.0},  # 0
            {"High": 11.3, "Low": 9.0},  # 1
            {"High": 11.1, "Low": 9.2},  # 2  → 中枢 #1 成立
            {"High": 12.0, "Low": 11.3},  # 3  非交叠
            {"High": 11.0, "Low": 9.4},  # 4  回到交叠（可延伸或作为新起点）
            {"High": 10.9, "Low": 9.5},  # 5
            {"High": 10.8, "Low": 9.6},  # 6
            {"High": 10.7, "Low": 9.7},  # 7  → 形成第二个三笔交叠的机会
        ]
    )
    bis = [Bi(i, i, "up" if i % 2 == 0 else "down") for i in range(len(df))]

    zs_nonreuse = build_zhongshus(df, bis, confirm_leave=True, reuse_tail_bi=False)
    zs_reuse = build_zhongshus(df, bis, confirm_leave=True, reuse_tail_bi=True)

    assert len(zs_reuse) >= len(zs_nonreuse)  # 开启重用不应更少
    # 两种策略都应产出至少一个有效中枢
    assert len(zs_nonreuse) >= 1 and len(zs_reuse) >= 1


def test_price_range_is_intersection_band_and_move_is_defined():
    """
    最终 price_range 为交集带（严格上界>下界），
    move 字段存在且在允许取值内。
    注：在“交集带口径”下，延伸只会让上界不增、下界不降，常见为 flat。
    """
    df = _mk_eq(
        [
            {"High": 12.0, "Low": 8.0},  # 0
            {"High": 11.4, "Low": 9.1},  # 1
            {"High": 11.2, "Low": 9.2},  # 2  交集成立
            {"High": 11.1, "Low": 9.3},  # 3  延伸收敛
            {"High": 11.05, "Low": 9.35},  # 4  继续收敛
        ]
    )
    bis = [Bi(i, i, "up" if i % 2 == 0 else "down") for i in range(len(df))]
    zs = build_zhongshus(df, bis, confirm_leave=True, reuse_tail_bi=False)
    assert len(zs) == 1
    lo, hi = zs[0].price_range
    assert hi > lo
    assert zs[0].move in ("flat", "up", "down")
