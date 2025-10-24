# backend/server.py
from __future__ import annotations

import json
import os
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

# ====== 项目路径与静态目录优先级 ======
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))

DATA_DIRS = [
    os.path.join(PROJECT_ROOT, "public", "data"),  # 你的实际位置
    os.path.join(PROJECT_ROOT, "data"),
    os.path.join(PROJECT_ROOT, "backend", "data"),
]
OUT_DIRS = [
    os.path.join(PROJECT_ROOT, "public", "out"),  # 你的实际位置
    os.path.join(PROJECT_ROOT, "out"),
    os.path.join(PROJECT_ROOT, "backend", "out"),
]

# ====== 导入你现有的核心模块 ======
from .core.bi import build_bis, select_fractals_for_bi
from .core.fractals import detect_fractal_candidates
from .core.io import read_csv_checked  # 严格读
from .core.prelude import resolve_inclusions
from .core.recommend import RULES_VERSION, advise_for_today
from .core.segment import build_segments
from .core.shi import classify_shi
from .core.zhongshu import build_zhongshus

app = FastAPI(title="Trading_App API", version="1.0.0", debug=True)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发期放开
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ====== 工具：查找文件 ======
def _find_csv(symbol: str) -> str:
    fname = f"{symbol}.csv"
    for d in DATA_DIRS:
        p = os.path.join(d, fname)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(f"未找到 CSV：{fname}；搜索路径：{DATA_DIRS}")


def _find_market_index() -> str:
    for d in OUT_DIRS:
        p = os.path.join(d, "market_index.json")
        if os.path.exists(p):
            return p
    raise FileNotFoundError(f"未找到 market_index.json；搜索路径：{OUT_DIRS}")


# ====== CSV 读取（严格→回退）======
REQUIRED_COLS = ["Date", "Open", "High", "Low", "Close", "Volume"]


def _read_csv_loose(csv_path: str) -> pd.DataFrame:
    """当 read_csv_checked 因为严格校验失败时，回退到最小规范化读法（开发期友好）。"""
    df = pd.read_csv(csv_path)
    # 宽松列名映射
    rename_map = {
        "日期": "Date",
        "开盘": "Open",
        "最高": "High",
        "最低": "Low",
        "收盘": "Close",
        "成交量": "Volume",
        "date": "Date",
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    }
    df = df.rename(columns=rename_map)
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"CSV 缺少必要列 {missing}; 实际列={list(df.columns)}; 文件={csv_path}")

    df = df[REQUIRED_COLS].copy()
    # 统一日期为 YYYY-MM-DD 字符串
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.strftime("%Y-%m-%d")
    df = (
        df.dropna(subset=["Date"])
        .drop_duplicates(subset=["Date"])
        .sort_values("Date")
        .reset_index(drop=True)
    )
    # 价格列转数值
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    return df


def _read_ohlcv(csv_path: str) -> pd.DataFrame:
    """优先严格校验；失败打印原因并回退到宽松读取。"""
    try:
        return read_csv_checked(csv_path)
    except Exception:
        print("[read_csv_checked 异常，启用回退] path=", csv_path)
        traceback.print_exc()
        return _read_csv_loose(csv_path)


# ====== 烛形序列序列化（UTC 秒）======
def _csv_to_candles(df: pd.DataFrame) -> List[Dict[str, Any]]:
    candles: List[Dict[str, Any]] = []
    for _, r in df.iterrows():
        ds = str(r["Date"])
        dt = datetime.strptime(ds, "%Y-%m-%d")
        ts = int(datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc).timestamp())
        candles.append(
            {
                "time": ts,
                "open": float(r["Open"]),
                "high": float(r["High"]),
                "low": float(r["Low"]),
                "close": float(r["Close"]),
            }
        )
    return candles


# ====== Zhongshu: 输出为等价K索引范围（便于前端画矩形）======
def _zs_start_end_by_k(legs: List[tuple[int, int]]) -> tuple[int, int]:
    """legs 是 [(bi.start, bi.end), ...]，都已是等价K索引。"""
    if not legs:
        return (0, 0)
    starts = [a for a, _ in legs]
    ends = [b for _, b in legs]
    return (int(min(starts)), int(max(ends)))


# ====== 主分析流水线 ======
def _analyze(symbol: str, cutoff: Optional[str]) -> Dict[str, Any]:
    csv_path = _find_csv(symbol)
    df = _read_ohlcv(csv_path)

    # 截止日期（回放），与 cli 一样按 "YYYY-MM-DD" 字符串比较
    if cutoff:
        df = df[df["Date"] <= cutoff].reset_index(drop=True)
        if len(df) == 0:
            # 最小空结构（与 cli 的空态一致口径）
            return {
                "meta": {
                    "symbol": symbol,
                    "asof": datetime.now().astimezone().isoformat(),
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

    last_bar_date = str(df.iloc[-1]["Date"]) if len(df) else None

    # === 等价K仅需 Date/High/Low ===
    df_eq = resolve_inclusions(df[["Date", "High", "Low"]].reset_index(drop=True))

    # Fractals → Bi → Segment → Zhongshu → Shi → Recommend
    frs = detect_fractal_candidates(df_eq)
    bis = build_bis(df_eq, select_fractals_for_bi(df_eq, frs))
    segs = build_segments(df_eq, bis)
    zss = build_zhongshus(df_eq, bis, confirm_leave=True, reuse_tail_bi=True)
    shi = classify_shi(df_eq, segs, zss)
    rec = advise_for_today(df_eq, segs, zss, shi)

    # —— 序列化（严格用属性）——
    out_frs = [{"idx": int(f.idx), "type": f.type} for f in frs]
    out_bis = [{"start": int(b.start), "end": int(b.end), "dir": b.dir} for b in bis]
    out_segs = [{"start": int(s.start), "end": int(s.end), "dir": s.dir} for s in segs]
    out_zss: List[Dict[str, Any]] = []
    for z in zss:
        ks, ke = _zs_start_end_by_k(z.legs)  # ➜ 用等价K索引范围
        low, up = z.price_range
        out_zss.append(
            {
                "start": ks,
                "end": ke,
                "price_range": [float(low), float(up)],
                "move": z.move,
                "legs": [[int(a), int(b)] for (a, b) in z.legs],
            }
        )

    out = {
        "meta": {
            "symbol": symbol,
            "asof": datetime.now().astimezone().isoformat(timespec="seconds"),
            "last_bar_date": last_bar_date,
            "tz": "Asia/Shanghai",
        },
        "rules_version": RULES_VERSION,
        "fractals": out_frs,
        "bis": out_bis,
        "segments": out_segs,
        "zhongshus": out_zss,
        "shi": {
            "class": shi.class_,
            "confidence": float(round(shi.confidence, 4)),
            "momentum": float(round(shi.momentum, 4)),
            "risk": float(round(shi.risk, 4)),
            "evidence": list(shi.evidence),
        },
        "recommendation_for_today": {
            "at_close_of": last_bar_date,
            "action": rec.action,
            "buy_strength": float(round(rec.buy_strength, 4)),
            "rationale": rec.rationale,
            "invalidate_if": rec.invalidate_if,
            "components": rec.components,
        },
    }
    return out


# ====== 路由 ======
@app.get("/api/series-c/bundle")
def api_series_c_bundle(
    symbol: str = Query(..., description="带交易所后缀，如 600519.SH"),
    tf: str = Query("1d", description="预留时间粒度"),
) -> Dict[str, Any]:
    try:
        csv_path = _find_csv(symbol)
        df = _read_ohlcv(csv_path)
        candles = _csv_to_candles(df)
        return {
            "symbol": symbol,
            "timeframe": tf,
            "candles": candles,
            "ma": [],
            "segments": [],
            "zones": [],
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print("[bundle error]", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"bundle error: {e}")


@app.get("/api/analysis")
def api_analysis(
    symbol: str = Query(..., description="带交易所后缀，如 600519.SH"),
    t: Optional[str] = Query(None, description="可选回放：截止 YYYY-MM-DD"),
) -> Dict[str, Any]:
    try:
        return _analyze(symbol, cutoff=t)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print("[analysis error]", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"analysis error: {e}")


@app.get("/api/market-index")
def api_market_index() -> Dict[str, Any]:
    try:
        p = _find_market_index()
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        print("[market-index error]", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"market-index error: {e}")
