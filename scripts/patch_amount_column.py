#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_amount_column.py

一次性脚本：
1) 遍历 public/data 下的所有个股 CSV（排除 symbols.csv）
2) 若无 Amount 列：在 Volume 与 TurnoverRate 之间插入（若无 TurnoverRate，则紧跟 Volume）
3) 对每一行：
   - 若 Amount 为空/NaN：用 Volume * Close * 100 估算（单位：元）
   - 若 Volume 或 Close 为空/NaN：保持 NaN

使用示例：
  python scripts/patch_amount_column.py
  python scripts/patch_amount_column.py --data-dir /path/to/public/data --dry-run
  python scripts/patch_amount_column.py --backup

注意：
- 该脚本不会改动列名大小写（假定标准列名：Date,Open,High,Low,Close,Volume,Amount,TurnoverRate）
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from typing import List

import pandas as pd


def is_nan(x) -> bool:
    try:
        return pd.isna(x) or (isinstance(x, float) and math.isnan(x))
    except Exception:
        return False


def insert_amount_column(df: pd.DataFrame) -> pd.DataFrame:
    """
    确保存在 Amount 列，并将其放在 Volume 与 TurnoverRate 之间。
    若没有 TurnoverRate，则放在 Volume 之后。
    若 Volume 不存在（极少数脏数据），则放在 Close 之后；再不行就放到最后。
    """
    cols: List[str] = list(df.columns)

    if "Amount" not in cols:
        # 决定插入位置
        def idx_of(col: str) -> int | None:
            try:
                return cols.index(col)
            except ValueError:
                return None

        vol_i = idx_of("Volume")
        tr_i = idx_of("TurnoverRate")
        close_i = idx_of("Close")

        # 默认插最后
        insert_at = len(cols)

        if vol_i is not None and tr_i is not None:
            insert_at = tr_i  # 插在 TurnoverRate 之前
        elif vol_i is not None:
            insert_at = vol_i + 1  # Volume 后
        elif close_i is not None:
            insert_at = close_i + 1  # Close 后

        # 实际插入
        df.insert(insert_at, "Amount", pd.Series([float("nan")] * len(df), index=df.index))

    else:
        # 已存在则确保位置正确（可选：不强制移动，避免无谓改动）
        # 如需强制位置，可解除以下注释：
        # df = move_amount_between_volume_and_tr(df)
        pass

    return df


def fill_amount(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """
    用 Volume * Close * 100 填补 Amount（仅填空值）
    返回 (df, filled_count)
    """
    # 确保数字类型
    for col in ["Volume", "Close", "Amount"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "Amount" not in df.columns:
        df = insert_amount_column(df)

    filled = 0
    if "Volume" in df.columns and "Close" in df.columns:
        # 估算值
        est = df["Volume"] * df["Close"] * 100.0

        # 仅在 Amount 缺失时填补，且需要 Volume/Close 有效
        mask_need = df["Amount"].isna()
        mask_have = est.notna() & (est > 0)
        mask = mask_need & mask_have

        if mask.any():
            df.loc[mask, "Amount"] = est[mask]
            filled = int(mask.sum())

    return df, filled


def reorder_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    把列顺序整理成较为统一的风格：
    Date, Open, High, Low, Close, Volume, Amount, TurnoverRate, ...(其余原样追加)
    不会删除未知列。
    """
    preferred = ["Date", "Open", "High", "Low", "Close", "Volume", "Amount", "TurnoverRate"]
    exist_pref = [c for c in preferred if c in df.columns]
    others = [c for c in df.columns if c not in exist_pref]
    return df[exist_pref + others]


def process_file(path: Path, dry_run: bool = False, backup: bool = False) -> dict:
    """
    处理单个 CSV，返回统计信息。
    """
    try:
        df = pd.read_csv(path)
    except Exception as e:
        return {"file": str(path), "status": f"read_error: {e}"}

    orig_cols = list(df.columns)

    # 确保 Amount 列存在且位置合适
    df = insert_amount_column(df)

    # 填补 Amount
    df, filled_cnt = fill_amount(df)

    # 规范列顺序（不改变其他列）
    df = reorder_columns(df)

    changed_cols = list(df.columns) != orig_cols
    changed_rows = filled_cnt > 0

    if dry_run:
        return {
            "file": str(path),
            "status": "dry-run",
            "added_or_moved_amount_column": changed_cols,
            "filled_amount_rows": filled_cnt,
        }

    # 落盘前备份
    if backup:
        bak = path.with_suffix(path.suffix + ".bak")
        try:
            path.replace(bak)
            # 备份完成后写新文件
            df.to_csv(path, index=False)
            return {
                "file": str(path),
                "status": "ok (backup written)",
                "added_or_moved_amount_column": changed_cols,
                "filled_amount_rows": filled_cnt,
            }
        except Exception as e:
            # 发生异常尝试回滚
            try:
                if bak.exists():
                    bak.replace(path)
            except Exception:
                pass
            return {"file": str(path), "status": f"write_error_after_backup: {e}"}
    else:
        try:
            df.to_csv(path, index=False)
            return {
                "file": str(path),
                "status": "ok",
                "added_or_moved_amount_column": changed_cols,
                "filled_amount_rows": filled_cnt,
            }
        except Exception as e:
            return {"file": str(path), "status": f"write_error: {e}"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-dir",
        default="/Users/eloliu/Documents/Trading_App/public/data",
        help="个股 CSV 所在目录（默认：/Users/eloliu/Documents/Trading_App/public/data）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印变更，不写回文件",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="写回前为每个 CSV 生成 .bak 备份文件",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir).resolve()
    if not data_dir.exists():
        raise SystemExit(f"[ERR] data dir not found: {data_dir}")

    csvs = [p for p in sorted(data_dir.glob("*.csv")) if p.name.lower() != "symbols.csv"]

    print(f"[INFO] scanning {len(csvs)} csv files under {data_dir}")

    total_fill = 0
    changed_files = 0
    for i, p in enumerate(csvs, 1):
        res = process_file(p, dry_run=args.dry_run, backup=args.backup)
        status = res.get("status")
        filled = res.get("filled_amount_rows", 0)
        moved = res.get("added_or_moved_amount_column", False)

        if filled or moved or status.startswith("read_error") or status.startswith("write_error"):
            changed_files += 1

        total_fill += int(filled or 0)

        print(
            f"[{i:04d}/{len(csvs)}] {p.name:>16}  "
            f"status={status:<22}  "
            f"filled={filled:<6}  "
            f"moved_amount_col={str(moved):<5}"
        )

    print("\n=== Summary ===")
    print(f"Files scanned : {len(csvs)}")
    print(f"Files changed : {changed_files}")
    print(f"Rows filled   : {total_fill}")
    if args.dry_run:
        print("(dry-run: no files modified)")
    elif args.backup:
        print("(backup: *.csv.bak created for modified files)")


if __name__ == "__main__":
    main()
