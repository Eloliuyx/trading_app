# backend/core/reco_io.py
from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pandas as pd

PROJ_DIR = Path(__file__).resolve().parents[2]  # Trading_App/
PUBLIC_DIR = PROJ_DIR / "public"
DATA_DIR = PUBLIC_DIR / "data"
META_DIR = DATA_DIR / "metadata"
OUT_DIR = PUBLIC_DIR / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def list_price_files() -> Iterator[Path]:
    """遍历 public/data 下所有个股 csv（忽略 metadata 子目录）"""
    for p in sorted(DATA_DIR.glob("*.csv")):
        yield p


def symbol_from_filename(p: Path) -> str:
    name = p.name
    return name[:-4] if name.endswith(".csv") else name


def read_prices(path: Path) -> pd.DataFrame:
    """读取个股日线，保证列名与类型，按日期升序"""
    df = pd.read_csv(path)
    need = ["Date", "Open", "High", "Low", "Close", "Volume"]
    missing = [c for c in need if c not in df.columns]
    if missing:
        raise ValueError(f"{path}: missing columns {missing}")
    df = df[need].copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    return df


def read_symbols_meta() -> pd.DataFrame:
    """读取 symbols.csv（symbol,name,industry,market,is_st,exchange,code）"""
    meta_path = META_DIR / "symbols.csv"
    df = pd.read_csv(meta_path, dtype={"code": str})
    # 兜底字段
    for col, default in [
        ("symbol", ""),
        ("name", ""),
        ("industry", "未知行业"),
        ("market", "主板"),
        ("is_st", False),
    ]:
        if col not in df.columns:
            df[col] = default
    return df[["symbol", "name", "industry", "market", "is_st"]].drop_duplicates("symbol")


def get_public_out_path() -> Path:
    return OUT_DIR / "market_reco.json"
