# core/cli.py
# rules_version: v1.2.0
from __future__ import annotations

import argparse
import glob
import json
import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from core.bi import build_bis, select_fractals_for_bi
from core.fractals import detect_fractal_candidates
from core.io import read_csv_checked
from core.prelude import resolve_inclusions
from core.recommend import RULES_VERSION, advise_for_today
from core.segment import build_segments
from core.shi import classify_shi
from core.zhongshu import build_zhongshus

TZ_SH = ZoneInfo("Asia/Shanghai")


# --------------- helpers ---------------


def _parse_cutoff(cutoff: str | None) -> str | None:
    if not cutoff:
        return None
    # 严格 YYYY-MM-DD
    try:
        dt = datetime.strptime(cutoff, "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except Exception as e:
        # ruff B904：保留异常链，便于定位
        raise ValueError(f"invalid cutoff date: {cutoff} (expected YYYY-MM-DD)") from e


def _now_iso_cn() -> str:
    return datetime.now(tz=TZ_SH).isoformat(timespec="seconds")


def _load_eq_df(path: str, cutoff: str | None) -> pd.DataFrame:
    df = read_csv_checked(path)  # Date,Open,High,Low,Close,Volume,...
    # 保障升序 & 去重（规范里要求升序，这里兜底）
    df = df.sort_values("Date").drop_duplicates(subset=["Date"]).reset_index(drop=True)
    if cutoff:
        # 日期列标准是 YYYY-MM-DD 字符串，直接比较即可（已升序）
        df = df[df["Date"] <= cutoff]
    # 仅取用于核心的列
    df_eq = resolve_inclusions(df[["Date", "High", "Low"]].reset_index(drop=True))
    return df_eq


def _empty_analysis(symbol: str) -> dict[str, Any]:
    """当数据不足（三根等价K都没有）时输出最小结构，保证稳定。"""
    asof = _now_iso_cn()
    return {
        "meta": {
            "symbol": symbol,
            "asof": asof,
            "last_bar_date": None,
            "tz": "Asia/Shanghai",
        },
        "rules_version": RULES_VERSION,
        "fractals": [],
        "bis": [],
        "segments": [],
        "zhongshus": [],
        "shi": {
            "class": "中枢震荡未破",
            "confidence": 0.5,
            "momentum": 0.0,
            "risk": 0.5,
            "evidence": ["数据不足，默认中性"],
        },
        "recommendation_for_today": {
            "at_close_of": None,
            "action": "回避",
            "buy_strength": 0.0,
            "rationale": "数据不足",
            "invalidate_if": "无",
            "components": {"A": 0.0, "B": 0.0, "C": 0.0, "D": 0.0, "E": 0.0},
        },
    }


def _mode_to_params(mode: str) -> tuple[bool, bool]:
    """
    返回 (confirm_leave, reuse_tail_bi)
    precision：抗假离开、减少过度切分
    recall   ：首次不交叠离开、允许相接重用尾笔
    """
    mode = (mode or "precision").lower()
    if mode == "recall":
        return (False, True)
    # default: precision
    return (True, False)


# --------------- pipeline ---------------


def _analyze_df(
    symbol: str,
    df_eq: pd.DataFrame,
    *,
    confirm_leave: bool = True,
    reuse_tail_bi: bool = False,
) -> dict[str, Any]:
    if len(df_eq) == 0:
        return _empty_analysis(symbol)

    # Fractals → Bis → Segments → Zhongshu → Shi → Recommend
    frs = detect_fractal_candidates(df_eq)
    bis = build_bis(df_eq, select_fractals_for_bi(df_eq, frs))
    segs = build_segments(df_eq, bis)
    zss = build_zhongshus(df_eq, bis, confirm_leave=confirm_leave, reuse_tail_bi=reuse_tail_bi)
    shi = classify_shi(df_eq, segs, zss)
    rec = advise_for_today(df_eq, segs, zss, shi)

    last_bar_date = str(df_eq.iloc[-1]["Date"])
    meta = {
        "symbol": symbol,
        "asof": _now_iso_cn(),
        "last_bar_date": last_bar_date,
        "tz": "Asia/Shanghai",
    }

    out = {
        "meta": meta,
        "rules_version": RULES_VERSION,
        "fractals": [{"idx": f.idx, "type": f.type} for f in frs],
        "bis": [{"start": b.start, "end": b.end, "dir": b.dir} for b in bis],
        "segments": [{"start": s.start, "end": s.end, "dir": s.dir} for s in segs],
        "zhongshus": [
            {
                "start": z.start_bi_idx,
                "end": z.end_bi_idx,
                "price_range": [float(z.price_range[0]), float(z.price_range[1])],
                "move": z.move,
                "legs": z.legs,  # 便于前端 hover 可解释（小体积）
            }
            for z in zss
        ],
        "shi": {
            "class": shi.class_,
            "confidence": round(shi.confidence, 4),
            "momentum": round(shi.momentum, 4),
            "risk": round(shi.risk, 4),
            "evidence": shi.evidence,
        },
        "recommendation_for_today": {
            "at_close_of": last_bar_date,
            "action": rec.action,
            "buy_strength": round(rec.buy_strength, 4),
            "rationale": rec.rationale,
            "invalidate_if": rec.invalidate_if,
            "components": rec.components,  # ✅ 输出 A/B/C/D/E 明细，便于可解释
        },
    }
    return out


def analyze(
    symbol: str,
    data_dir: str = "./data",
    out_dir: str = "./out",
    cutoff: str | None = None,
    *,
    mode: str = "precision",
    confirm_leave: bool | None = None,
    reuse_tail_bi: bool | None = None,
) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(data_dir, f"{symbol}.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    cutoff = _parse_cutoff(cutoff)
    df_eq = _load_eq_df(path, cutoff)

    # mode → 默认参数，再由显式开关覆盖
    default_confirm, default_reuse = _mode_to_params(mode)
    confirm_leave = default_confirm if confirm_leave is None else confirm_leave
    reuse_tail_bi = default_reuse if reuse_tail_bi is None else reuse_tail_bi

    out = _analyze_df(symbol, df_eq, confirm_leave=confirm_leave, reuse_tail_bi=reuse_tail_bi)
    out_path = os.path.join(out_dir, f"{symbol}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    return out_path


def analyze_all(
    data_dir: str = "./data",
    out_dir: str = "./out",
    cutoff: str | None = None,
    *,
    mode: str = "precision",
    confirm_leave: bool | None = None,
    reuse_tail_bi: bool | None = None,
) -> str:
    os.makedirs(out_dir, exist_ok=True)
    files = sorted(glob.glob(os.path.join(data_dir, "*.csv")))
    buckets: dict[str, list[tuple[str, float]]] = {
        "买": [],
        "观察买点": [],
        "持有": [],
        "止盈": [],
        "回避": [],
    }
    buy_strength_map: dict[str, float] = {}

    last_out_path = ""
    cutoff = _parse_cutoff(cutoff)
    default_confirm, default_reuse = _mode_to_params(mode)
    confirm_leave = default_confirm if confirm_leave is None else confirm_leave
    reuse_tail_bi = default_reuse if reuse_tail_bi is None else reuse_tail_bi

    for path in files:
        symbol = os.path.splitext(os.path.basename(path))[0]
        try:
            df_eq = _load_eq_df(path, cutoff)
            out = _analyze_df(
                symbol, df_eq, confirm_leave=confirm_leave, reuse_tail_bi=reuse_tail_bi
            )
        except Exception as e:
            # 失败 fallback：写空结构，避免整批中断
            out = _empty_analysis(symbol)
            out["meta"]["error"] = str(e)

        # 写单标的 json
        out_path = os.path.join(out_dir, f"{symbol}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        last_out_path = out_path

        rec = out["recommendation_for_today"]
        action = rec["action"]
        bs = float(rec["buy_strength"])
        buy_strength_map[symbol] = bs
        if action in buckets:
            buckets[action].append((symbol, bs))
        else:
            buckets.setdefault(action, []).append((symbol, bs))

    # 各 bucket 内按 buy_strength 降序
    sort_desc = {
        k: [sym for sym, _ in sorted(v, key=lambda x: x[1], reverse=True)]
        for k, v in buckets.items()
    }

    market_index = {
        "asof": _now_iso_cn(),
        "rules_version": RULES_VERSION,
        "mode": mode,
        "params": {
            "confirm_leave": confirm_leave,
            "reuse_tail_bi": reuse_tail_bi,
        },
        "buckets": {
            "买": sort_desc["买"],
            "观察买点": sort_desc["观察买点"],
            "持有": sort_desc["持有"],
            "止盈": sort_desc["止盈"],
            "回避": sort_desc["回避"],
        },
        "buy_strength": buy_strength_map,
    }
    idx_path = os.path.join(out_dir, "market_index.json")
    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(market_index, f, ensure_ascii=False, indent=2)
    return last_out_path


# --------------- CLI ---------------


def main():
    p = argparse.ArgumentParser(description="Trading_App v1.2 CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    # analyze
    pa = sub.add_parser("analyze", help="分析单个标的")
    pa.add_argument("symbol", type=str)
    pa.add_argument("--data", type=str, default="./data")
    pa.add_argument("--out", type=str, default="./out")
    pa.add_argument("--t", type=str, default=None, help="截止日期 YYYY-MM-DD（回放）")
    pa.add_argument("--mode", type=str, choices=["precision", "recall"], default="precision")
    pa.add_argument(
        "--confirm-leave",
        dest="confirm_leave",
        action="store_true",
        help="连续不交叠确认离开",
    )
    pa.add_argument("--no-confirm-leave", dest="confirm_leave", action="store_false")
    pa.add_argument(
        "--reuse-tail-bi",
        dest="reuse_tail_bi",
        action="store_true",
        help="相接中枢重用尾笔",
    )
    pa.add_argument("--no-reuse-tail-bi", dest="reuse_tail_bi", action="store_false")
    pa.set_defaults(confirm_leave=None, reuse_tail_bi=None)

    # analyze-all
    paa = sub.add_parser("analyze-all", help="批量分析 data 目录全部 CSV")
    paa.add_argument("--data", type=str, default="./data")
    paa.add_argument("--out", type=str, default="./out")
    paa.add_argument("--t", type=str, default=None, help="截止日期 YYYY-MM-DD（回放）")
    paa.add_argument("--mode", type=str, choices=["precision", "recall"], default="precision")
    paa.add_argument("--confirm-leave", dest="confirm_leave", action="store_true")
    paa.add_argument("--no-confirm-leave", dest="confirm_leave", action="store_false")
    paa.add_argument("--reuse-tail-bi", dest="reuse_tail_bi", action="store_true")
    paa.add_argument("--no-reuse-tail-bi", dest="reuse_tail_bi", action="store_false")
    paa.set_defaults(confirm_leave=None, reuse_tail_bi=None)

    args = p.parse_args()

    if args.cmd == "analyze":
        path = analyze(
            args.symbol,
            args.data,
            args.out,
            args.t,
            mode=args.mode,
            confirm_leave=args.confirm_leave,
            reuse_tail_bi=args.reuse_tail_bi,
        )
        print(path)
    elif args.cmd == "analyze-all":
        path = analyze_all(
            args.data,
            args.out,
            args.t,
            mode=args.mode,
            confirm_leave=args.confirm_leave,
            reuse_tail_bi=args.reuse_tail_bi,
        )
        print(path)


if __name__ == "__main__":
    main()
