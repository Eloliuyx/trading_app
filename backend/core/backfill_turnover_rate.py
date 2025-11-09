# backend/core/backfill_turnover_rate.py
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

# 默认数据目录：项目根/public/data
PROJ = Path(__file__).resolve().parents[2]
PUBLIC = PROJ / "public"
DATA = PUBLIC / "data"


def _tushare_client(token: Optional[str]):
    import tushare as ts

    if token:
        return ts.pro_api(token)
    return ts.pro_api()


def iter_symbol_files(data_dir: Path):
    for p in sorted(data_dir.glob("*.csv")):
        name = p.name.lower()
        if name == "symbols.csv":
            continue
        yield p


def backfill_one(
    pro,
    csv_path: Path,
    since_days: Optional[int] = None,
) -> None:
    sym = csv_path.stem  # 600519.SH

    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"[skip] {sym}: read_csv error: {e}")
        return

    if "Date" not in df.columns:
        print(f"[skip] {sym}: no Date column")
        return

    # 规范 Date
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)

    if df.empty:
        print(f"[skip] {sym}: empty csv")
        return

    # 若不存在 TurnoverRate 列，则创建
    if "TurnoverRate" not in df.columns:
        df["TurnoverRate"] = pd.NA

    # 找出需要补的日期区间
    if since_days is not None:
        # 只处理最近 N 天（含）
        end_date = df["Date"].max().date()
        start_date = (end_date - timedelta(days=since_days)).isoformat()
        end_date_s = end_date.isoformat()
        mask = (df["Date"] >= start_date) & (df["Date"] <= end_date_s)
        target_dates = df.loc[mask, "Date"]
    else:
        # 所有 TurnoverRate 为空的行
        missing = df["TurnoverRate"].isna()
        if not missing.any():
            print(f"[ok] {sym}: no missing TurnoverRate, skip")
            return
        target_dates = df.loc[missing, "Date"]

    if target_dates.empty:
        print(f"[skip] {sym}: no target dates")
        return

    start_ymd = target_dates.min().strftime("%Y%m%d")
    end_ymd = target_dates.max().strftime("%Y%m%d")

    # 向 tushare 请求 daily_basic.turnover_rate
    try:
        basic = pro.daily_basic(
            ts_code=sym,
            start_date=start_ymd,
            end_date=end_ymd,
            fields="ts_code,trade_date,turnover_rate",
        )
    except Exception as e:
        print(f"[error] {sym}: tushare.daily_basic failed: {e}")
        return

    if basic is None or basic.empty:
        print(f"[warn] {sym}: no daily_basic data for {start_ymd}-{end_ymd}")
        return

    # 规范日期 & 换手率（转为小数）
    basic["Date"] = pd.to_datetime(basic["trade_date"])
    basic["TurnoverRate_new"] = (
        pd.to_numeric(basic["turnover_rate"], errors="coerce") / 100.0
    )

    basic = basic[["Date", "TurnoverRate_new"]].dropna(subset=["TurnoverRate_new"])

    if basic.empty:
        print(f"[warn] {sym}: all turnover_rate invalid")
        return

    # 按 Date 左连接补数据：已有的不覆盖，只填 NaN
    merged = df.merge(basic, on="Date", how="left")

    # 优先保留原有 TurnoverRate；若为空则用新值
    if "TurnoverRate" in merged.columns:
        merged["TurnoverRate"] = merged["TurnoverRate"].combine_first(
            merged["TurnoverRate_new"]
        )
    else:
        merged["TurnoverRate"] = merged["TurnoverRate_new"]

    merged = merged.drop(columns=["TurnoverRate_new"])

    # 保存
    merged.to_csv(csv_path, index=False)
    filled = merged["TurnoverRate"].notna().sum()
    print(
        f"[ok] {sym}: backfilled TurnoverRate for {filled} rows "
        f"(range {start_ymd}-{end_ymd})"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--token",
        help="Tushare token（可不填，默认读环境变量 TUSHARE_TOKEN）",
        default=None,
    )
    ap.add_argument(
        "--data-dir",
        default=str(DATA),
        help="CSV 目录，默认 public/data",
    )
    ap.add_argument(
        "--symbol",
        help="仅处理单只，如 600519.SH；不填则遍历全部 *.csv",
        default=None,
    )
    ap.add_argument(
        "--since-days",
        type=int,
        default=None,
        help="仅回填最近 N 天（可选，用于省积分）",
    )
    args = ap.parse_args()

    data_dir = Path(args.data_dir).resolve()
    if not data_dir.exists():
        raise SystemExit(f"data dir not found: {data_dir}")

    pro = _tushare_client(args.token)

    if args.symbol:
        csv_path = data_dir / f"{args.symbol}.csv"
        if not csv_path.exists():
            raise SystemExit(f"csv not found: {csv_path}")
        backfill_one(pro, csv_path, since_days=args.since_days)
    else:
        for csv_path in iter_symbol_files(data_dir):
            backfill_one(pro, csv_path, since_days=args.since_days)


if __name__ == "__main__":
    main()
