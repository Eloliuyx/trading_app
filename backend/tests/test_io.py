# core/tests/test_io.py
from pathlib import Path

import pytest

from core.io import IOValidationError, read_ohlcv_csv, summarize_df


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def test_read_ok_and_filter_suspended(tmp_path: Path):
    csv = """Date,Open,High,Low,Close,Volume,Amount
2025-10-10,10,10.5,9.8,10.2,1000,100000
2025-10-11,10.2,10.6,10.0,10.4,0,110000
2025-10-12,10.4,10.8,10.3,10.7,1200,120000
"""
    p = _write(tmp_path, "ok.csv", csv)
    df = read_ohlcv_csv(str(p))
    # 第二天 Volume==0 被过滤 → 只剩两行
    assert len(df) == 2
    assert list(df.columns)[:6] == ["Date", "Open", "High", "Low", "Close", "Volume"]
    n, (lo, hi) = summarize_df(df)
    assert n == 2
    assert lo == pytest.approx(9.8, rel=1e-6) or lo == pytest.approx(10.3, rel=1e-6)
    assert hi == pytest.approx(10.8, rel=1e-6)


def test_read_chinese_headers(tmp_path: Path):
    csv = """日期,开盘,最高,最低,收盘,成交量,成交额
2025-10-10,10,10.5,9.8,10.2,1000,100000
2025-10-11,10.2,10.6,10.0,10.4,900,110000
"""
    p = _write(tmp_path, "cn.csv", csv)
    df = read_ohlcv_csv(str(p))
    assert list(df.columns)[:6] == ["Date", "Open", "High", "Low", "Close", "Volume"]
    assert len(df) == 2


def test_not_strictly_increasing_dates_should_fail(tmp_path: Path):
    csv = """Date,Open,High,Low,Close,Volume
2025-10-11,10,10.5,9.8,10.2,1000
2025-10-10,10.2,10.6,10.0,10.4,900
"""
    p = _write(tmp_path, "bad_order.csv", csv)
    with pytest.raises(IOValidationError):
        _ = read_ohlcv_csv(str(p))


def test_duplicate_dates_should_fail(tmp_path: Path):
    csv = """Date,Open,High,Low,Close,Volume
2025-10-10,10,10.5,9.8,10.2,1000
2025-10-10,10.2,10.6,10.0,10.4,900
"""
    p = _write(tmp_path, "dup.csv", csv)
    with pytest.raises(IOValidationError):
        _ = read_ohlcv_csv(str(p))


def test_missing_required_col_should_fail(tmp_path: Path):
    csv = """Date,Open,High,Low,Close
2025-10-10,10,10.5,9.8,10.2
"""
    p = _write(tmp_path, "miss.csv", csv)
    with pytest.raises(IOValidationError):
        _ = read_ohlcv_csv(str(p))


def test_price_consistency_should_fail(tmp_path: Path):
    # High 低于 Close → 不合理，应报错
    csv = """Date,Open,High,Low,Close,Volume
2025-10-10,10,9.0,8.0,9.5,1000
"""
    p = _write(tmp_path, "bad_price.csv", csv)
    with pytest.raises(IOValidationError):
        _ = read_ohlcv_csv(str(p))
