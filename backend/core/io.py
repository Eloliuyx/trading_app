# core/io.py
from __future__ import annotations

import os
from typing import Any, SupportsFloat, SupportsIndex, SupportsInt, cast

import pandas as pd

REQUIRED_COLS = ["Date", "Open", "High", "Low", "Close", "Volume"]
OPTIONAL_COLS = ["Amount"]

# 允许的中英文列名映射（宽松处理，避免数据源差异）
CN2EN: dict[str, str] = {
    "日期": "Date",
    "开盘": "Open",
    "最高": "High",
    "最低": "Low",
    "收盘": "Close",
    "成交量": "Volume",
    "成交额": "Amount",
}


class IOValidationError(ValueError):
    """输入数据不合规时抛出。"""


def _to_float(x: Any) -> float:
    """把常见数值/字符串/索引安全转成 float，失败时抛 IOValidationError。"""
    try:
        # cast 只是喂给 mypy 的类型提示，实际还是交给 float() 做兜底
        y = cast("SupportsFloat | SupportsInt | SupportsIndex | str", x)
        return float(y)  # type: ignore[arg-type]
    except Exception as e:  # noqa: BLE001
        raise IOValidationError(f"无法转换为浮点数: {x!r}") from e


def _rename_columns_if_needed(df: pd.DataFrame) -> pd.DataFrame:
    rename_map: dict[str, str] = {}
    for col in df.columns:
        if col in CN2EN:
            rename_map[col] = CN2EN[col]
    if rename_map:
        df = df.rename(columns=rename_map)
    return df


def _assert_required_columns(df: pd.DataFrame) -> None:
    cols = set(df.columns)
    missing = [c for c in REQUIRED_COLS if c not in cols]
    if missing:
        raise IOValidationError(f"缺少必需列: {missing}. 需要列: {REQUIRED_COLS}")


def _coerce_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    # Date 转为 pandas datetime（不带时区），保持“日期严格升序”的口径
    try:
        df["Date"] = pd.to_datetime(df["Date"], utc=False).dt.date
    except Exception as e:
        raise IOValidationError(f"Date 列解析失败: {e}") from e

    # 价格列转 float，Volume/Amount 尝试转为数值
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "Amount" in df.columns:
        df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")

    # 去除任何关键列为 NaN 的行
    df = df.dropna(subset=["Date", "Open", "High", "Low", "Close", "Volume"]).copy()

    # 统一列顺序（若 Amount 不存在则忽略）
    final_cols = [*REQUIRED_COLS, *([c for c in OPTIONAL_COLS if c in df.columns])]
    return df.loc[:, final_cols]


def _ensure_strictly_increasing_dates(df: pd.DataFrame) -> None:
    # 先按 Date 排序，再检查是否严格单调递增 & 无重复
    sorted_df = df.sort_values("Date", kind="mergesort").reset_index(drop=True)
    if not (sorted_df["Date"] == df["Date"]).all():
        # 只要入参不是严格升序，就报错（保持“输入数据严格升序”的契约）
        raise IOValidationError("日期必须严格升序（发现乱序）。")

    # 检查重复
    if sorted_df["Date"].duplicated().any():
        dups = sorted_df.loc[sorted_df["Date"].duplicated(), "Date"].tolist()
        raise IOValidationError(f"发现重复日期: {dups}")


def _filter_suspended_days(df: pd.DataFrame) -> pd.DataFrame:
    """
    停牌日处理：跳过。口径：
    - Volume == 0 或者 NaN 视为无成交 → 过滤
    """
    _before = len(df)
    df = df[df["Volume"].fillna(0) > 0].reset_index(drop=True)
    _after = len(df)
    # 不在这里报错；只是过滤。必要时可在日志中记录 before-after。
    return df


def _validate_price_consistency(df: pd.DataFrame) -> None:
    """基本数值合理性：High ≥ max(Open, Close) 且 Low ≤ min(Open, Close) 且 High ≥ Low"""
    bad_rows: list[int] = []
    # 使用命名元组属性访问，避免 dict 下标错误；pos 是 0-based 行号
    for pos, row in enumerate(df.itertuples(index=False, name="Row"), start=0):
        high = _to_float(row.High)
        low = _to_float(row.Low)
        open_ = _to_float(row.Open)
        close = _to_float(row.Close)

        high_ok = high >= max(open_, close)
        low_ok = low <= min(open_, close)
        range_ok = high >= low

        if not (high_ok and low_ok and range_ok):
            bad_rows.append(pos)

    if bad_rows:
        # 抛出统一异常；调用方捕获为 IOValidationError 即可
        raise IOValidationError(f"价格不一致，问题行号(0-based): {bad_rows}")


# === public API ===


def read_csv_checked(path: str) -> pd.DataFrame:
    """
    读取 CSV → 列名规范化 → 基础校验 → 过滤停牌/无量 → 返回 DataFrame
    要求：包含列 Date, High, Low；日期升序、去重。
    """
    try:
        df = pd.read_csv(path)
    except Exception as e:  # noqa: BLE001
        # 保留异常链，便于定位
        raise IOValidationError(f"CSV 读取失败: {e}") from e

    df = _rename_columns_if_needed(df)  # 你已有的列名映射函数
    _validate_price_consistency(df)  # 你已有的校验与类型规范函数
    df = _filter_suspended_days(df)  # 你已有的过滤函数（若命名不同用你的实际函数）
    return read_ohlcv_csv(path)


def read_ohlcv_csv(path: str) -> pd.DataFrame:
    """
    读取 A 股日K CSV，并进行严格校验与规范化，返回 DataFrame。
    口径：
      - 前复权价格
      - Asia/Shanghai 时区（日期不带时区，按自然日）
      - 日期严格升序、无重复
      - 停牌（Volume==0）跳过
      - 必要列：Date, Open, High, Low, Close, Volume；Amount 可选

    返回列顺序：Date, Open, High, Low, Close, Volume, [Amount?]
    """
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    try:
        df = pd.read_csv(path)
    except Exception as e:
        raise IOValidationError(f"CSV 读取失败: {e}") from e

    df = _rename_columns_if_needed(df)
    _assert_required_columns(df)
    df = _coerce_dtypes(df)

    # 日期必须严格升序（不自动更正，避免非确定性）
    _ensure_strictly_increasing_dates(df)

    # 过滤停牌
    df = _filter_suspended_days(df)

    # 数值一致性检查
    _validate_price_consistency(df)

    # 最终再保证索引连续
    df = df.reset_index(drop=True)
    _validate_price_consistency(df)
    return df


def summarize_df(df: pd.DataFrame) -> tuple[int, tuple[float, float]]:
    """
    简要统计：返回 (记录数, (全局最低价, 全局最高价))
    方便测试/日志。
    """
    n = len(df)
    low = float(df["Low"].min()) if n > 0 else float("nan")
    high = float(df["High"].max()) if n > 0 else float("nan")
    return n, (low, high)


__all__ = ["read_ohlcv_csv", "read_csv_checked"]
