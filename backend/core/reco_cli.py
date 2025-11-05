# backend/core/reco_cli.py
from __future__ import annotations
import argparse, json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, List

import pandas as pd

from .reco_io import list_price_files, read_prices, symbol_from_filename, read_symbols_meta, get_public_out_path
from .reco import analyze_symbol, MetaRow, RULES_VERSION

TZ_SH = timezone(timedelta(hours=8))

def run_all() -> Dict[str, Any]:
    meta_df = read_symbols_meta()
    items: List[Dict[str, Any]] = []
    last_bar_date = None

    for path in list_price_files():
        symbol = symbol_from_filename(path)
        try:
            df = read_prices(path)
        except Exception:
            continue

        if last_bar_date is None and len(df) > 0:
            last_bar_date = df["Date"].iloc[-1].strftime("%Y-%m-%d")
        row = meta_df.loc[meta_df["symbol"] == symbol]
        if row.empty:
            # 元数据缺失时提供兜底
            meta = MetaRow(symbol=symbol, name=symbol, industry="未知行业", market="主板", is_st=False)
        else:
            r = row.iloc[0]
            meta = MetaRow(
                symbol=symbol,
                name=str(r["name"]),
                industry=str(r["industry"]),
                market=str(r["market"]),
                is_st=bool(r["is_st"])
            )

        item = analyze_symbol(df, meta)
        if item:
            items.append(item)

    # 按 score 排序
    items = sorted(items, key=lambda x: x["score"], reverse=True)

    payload: Dict[str, Any] = {
        "asof": datetime.now(TZ_SH).isoformat(),
        "last_bar_date": last_bar_date,
        "rules_version": RULES_VERSION,
        "count": len(items),
        "list": items,
    }
    return payload

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="写入 public/out/market_reco.json")
    args = parser.parse_args()

    payload = run_all()
    if args.write:
        out_path = get_public_out_path()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ wrote {out_path} ({payload['count']} items)")
    else:
        print(json.dumps(payload, ensure_ascii=False)[:2000] + " ...")

if __name__ == "__main__":
    main()
