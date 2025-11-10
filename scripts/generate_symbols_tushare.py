#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
根据 TuShare 数据生成 symbols.csv

输出字段：
symbol,name,industry,market,is_st,exchange,code

约定：
- 仅保留 A 股上市公司（上交所 / 深交所 / 北交所，list_status='L'）
- symbol 使用 ts_code（如 000001.SZ）
- industry 使用 TuShare stock_basic.industry（为空则填 '未知行业'）
- market 使用 TuShare 的 market 字段（主板 / 创业板 / 科创板 / 北交所 等）
- is_st 通过名称包含 'ST' / '*ST' 判断
- exchange 使用 ts_code 后缀（SH / SZ / BJ）
- code 为纯 6 位代码（000001）
"""

import os
import sys
import pathlib
import tushare as ts
import pandas as pd


def get_pro():
    token = os.getenv("TUSHARE_TOKEN") or os.getenv("TUSHARE_PRO_TOKEN")
    if not token:
        raise SystemExit(
            "ERROR: 请先在环境变量中设置 TUSHARE_TOKEN（或 TUSHARE_PRO_TOKEN）。"
        )
    ts.set_token(token)
    return ts.pro_api()


def fetch_a_share_symbols(pro):
    """
    使用 TuShare pro.stock_basic 获取 A 股基础信息
    """
    # exchange='' + list_status='L' = 所有在市 A 股
    df = pro.stock_basic(
        exchange="",
        list_status="L",
        fields=(
            "ts_code,symbol,name,area,industry,market,exchange,list_date"
        ),
    )

    # 仅保留上交所/深交所/北交所股票
    df = df[df["exchange"].isin(["SSE", "SZSE", "BSE"])].copy()

    # 统一字段
    df["symbol"] = df["ts_code"]  # 000001.SZ
    df["code"] = df["symbol"].str.split(".").str[0]

    # exchange: 简写 SH / SZ / BJ
    def map_exchange(ts_code: str) -> str:
        if not isinstance(ts_code, str) or "." not in ts_code:
            return ""
        suf = ts_code.split(".")[1]
        if suf.upper() == "SH":
            return "SH"
        if suf.upper() == "SZ":
            return "SZ"
        if suf.upper() == "BJ":
            return "BJ"
        return suf.upper()

    df["exchange_short"] = df["symbol"].apply(map_exchange)

    # industry: 使用 tushare 的行业字段，缺失填 '未知行业'
    df["industry"] = df["industry"].fillna("未知行业")

    # market: tushare 的 market 字段已是中文（主板 / 创业板 / 科创板 / 北交所 等）
    df["market"] = df["market"].fillna("")

    # is_st: 名称中包含 ST / *ST 视为 True
    df["is_st"] = df["name"].str.contains("ST", case=False, na=False)

    # 选取 & 重命名列
    out = df[
        [
            "symbol",
            "name",
            "industry",
            "market",
            "is_st",
            "exchange_short",
            "code",
        ]
    ].rename(columns={"exchange_short": "exchange"})

    # 按 symbol 排序
    out = out.sort_values("symbol").reset_index(drop=True)

    return out


def main():
    pro = get_pro()
    df = fetch_a_share_symbols(pro)

    # 输出路径：项目根目录下 /public/data/metadata/symbols.csv
    # 你也可以改成 backend 使用的位置
    root = pathlib.Path(__file__).resolve().parents[1]  # 项目根目录
    out_dir = root / "public" / "data" / "metadata"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "symbols.csv"

    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"写入 {out_path}，共 {len(df)} 条 A 股记录。")


if __name__ == "__main__":
    main()
