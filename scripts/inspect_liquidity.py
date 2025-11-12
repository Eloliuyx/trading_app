#!/usr/bin/env python
"""
inspect_liquidity.py

从 universe.json 中找出：
  近60日平均日成交额 ≥ 5000万元
的标的，并打印出来，方便检查 F2 为什么为 0 个。

使用方式：
  python inspect_liquidity.py path/to/universe.json

如不传参数，默认尝试 ./public/data/universe.json
"""

import json
import sys
from pathlib import Path

# ===== 配置 =====
# 如果你的 amt60_avg 单位是「元」，阈值用 50_000_000
# 如果你的 amt60_avg 单位是「万元」，阈值用 5_000
THRESHOLD = 50_000_000  # 按“元”算，如需按“万元”改成 5_000

DEFAULT_PATHS = [
    Path("public/data/universe.json"),
    Path("public/universe.json"),
    Path("universe.json"),
]

def load_universe(path_arg: str | None):
    if path_arg:
        p = Path(path_arg)
        if not p.is_file():
            raise SystemExit(f"[ERR] File not found: {p}")
        return json.loads(p.read_text(encoding="utf-8")), p

    for p in DEFAULT_PATHS:
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8")), p

    raise SystemExit("[ERR] universe.json not found in default paths.")

def get_amt60(item: dict) -> float:
    """
    尽量从多处取 amt60_avg，兼容不同结构：
    - 顶层 item['amt60_avg']
    - features 里面的 item['features']['amt60_avg']
    """
    f = item.get("features") or {}
    v = item.get("amt60_avg", None)
    if v is None or v == 0:
        v = f.get("amt60_avg", 0.0)
    # 确保是数字
    try:
        return float(v or 0.0)
    except Exception:
        return 0.0

def main():
    path_arg = sys.argv[1] if len(sys.argv) > 1 else None
    data, path = load_universe(path_arg)

    items = data.get("list", [])
    print(f"[INFO] Loaded {len(items)} symbols from {path}")
    print(f"[INFO] Using threshold: {THRESHOLD} (same unit as amt60_avg)\n")

    passed = []
    zero_or_missing = 0

    for item in items:
        amt60 = get_amt60(item)
        if amt60 <= 0:
            zero_or_missing += 1
        if amt60 >= THRESHOLD:
            passed.append(
                {
                    "symbol": item.get("symbol"),
                    "name": item.get("name"),
                    "amt60_avg": amt60,
                }
            )

    # 按成交额从大到小排序
    passed.sort(key=lambda x: x["amt60_avg"], reverse=True)

    print(f"=== Stocks with amt60_avg >= {THRESHOLD} ===")
    if not passed:
        print("(none)")
    else:
        for x in passed:
            print(
                f"{x['symbol']:>10}  {x['name']:<12}  amt60_avg={x['amt60_avg']:.2f}"
            )

    print("\n=== Summary ===")
    print(f"Total symbols: {len(items)}")
    print(f"amt60_avg >= threshold: {len(passed)}")
    print(f"amt60_avg <= 0 (possible data issue): {zero_or_missing}")

if __name__ == "__main__":
    main()
