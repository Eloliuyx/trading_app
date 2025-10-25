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

# ===== 路径配置 =====
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))

DATA_DIRS = [
    os.path.join(PROJECT_ROOT, "public", "data"),
    os.path.join(PROJECT_ROOT, "data"),
    os.path.join(PROJECT_ROOT, "backend", "data"),
]
OUT_DIRS = [
    os.path.join(PROJECT_ROOT, "public", "out"),
    os.path.join(PROJECT_ROOT, "out"),
    os.path.join(PROJECT_ROOT, "backend", "out"),
]

# ===== 导入核心模块 =====
from .core.io import read_csv_checked
from .core.prelude import resolve_inclusions
from .core.fractals import detect_fractal_candidates
from .core.bi import select_fractals_for_bi, build_bis
from .core.segment import build_segments
from .core.zhongshu import build_zhongshus
from .core.shi import classify_shi
from .core.recommend import advise_for_today, RULES_VERSION

app = FastAPI(title="Trading_App API", version="1.2.0", debug=True)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== 文件定位工具 =====
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

def _list_symbols() -> List[str]:
    syms = []
    for d in DATA_DIRS:
        if not os.path.exists(d):
            continue
        for f in os.listdir(d):
            if f.endswith(".csv"):
                syms.append(f[:-4])
    return sorted(list(set(syms)))

# ===== 宽松读取（仅开发启用） =====
REQUIRED_COLS = ["Date", "Open", "High", "Low", "Close", "Volume"]

def _read_csv_loose(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
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
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
    df = df.dropna(subset=["Date"]).drop_duplicates(subset=["Date"]).sort_values("Date").reset_index(drop=True)
    for c in ["Open", "High", "Low", "Close", "Volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["Open", "High", "Low", "Close"])
    return df

def _read_ohlcv(csv_path: str) -> pd.DataFrame:
    """
    优先严格校验；失败时默认回退到宽松读取（与旧版行为一致）。
    若需要严格失败，请设置环境变量 STRICT_READ=1。
    """
    try:
        return read_csv_checked(csv_path)
    except Exception as e:
        strict = os.getenv("STRICT_READ") == "1"
        if strict:
            # 严格模式下直接抛，让上层返回 4xx/5xx
            raise
        print("[WARN] read_csv_checked 失败，自动回退到宽松读取: ", csv_path, " -> ", repr(e))
        traceback.print_exc()
        return _read_csv_loose(csv_path)

# ===== 转蜡烛序列（UTC 秒） =====
def _csv_to_candles(df: pd.DataFrame) -> List[Dict[str, Any]]:
    candles = []
    for _, r in df.iterrows():
        dt = r["Date"]
        if not isinstance(dt, datetime):
            dt = datetime.combine(dt, datetime.min.time())
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

# ===== 工具：中枢索引范围（等价K） =====
def _zs_start_end_by_k(legs: List[tuple[int, int]]) -> tuple[int, int]:
    """legs 是 [(bi.start, bi.end), ...]，都已是等价K索引。"""
    if not legs:
        return (0, 0)
    starts = [a for a, _ in legs]
    ends = [b for _, b in legs]
    return (int(min(starts)), int(max(ends)))

# ===== 主分析流水线 =====
def _analyze(symbol: str, cutoff: Optional[str], mode: str = "precision",
             confirm_leave: Optional[bool] = None, reuse_tail_bi: Optional[bool] = None) -> Dict[str, Any]:
    csv_path = _find_csv(symbol)
    df = _read_ohlcv(csv_path)

    # 回放（与 CLI 一致）
    if cutoff:
        df = df[df["Date"] <= cutoff].reset_index(drop=True)
        if len(df) == 0:
            return {
                "meta": {"symbol": symbol, "asof": datetime.now().astimezone().isoformat(),
                         "last_bar_date": None, "tz": "Asia/Shanghai"},
                "rules_version": RULES_VERSION,
                "fractals": [], "bis": [], "segments": [], "zhongshus": [],
                "shi": {"class": "中枢震荡未破", "confidence": 0.5, "momentum": 0.0, "risk": 0.5,
                        "evidence": ["数据不足，默认中性"]},
                "recommendation_for_today": {
                    "at_close_of": None, "action": "回避", "buy_strength": 0.0,
                    "rationale": "数据不足", "invalidate_if": "无",
                    "components": {"A": 0.0, "B": 0.0, "C": 0.0, "D": 0.0, "E": 0.0},
                },
            }

    last_bar_date = str(df.iloc[-1]["Date"]) if len(df) else None

    # 等价K（含 src_start/src_end，可用于回映射）
    df_eq = resolve_inclusions(df[["Date", "High", "Low"]].reset_index(drop=True))

    # === 管道 ===
    frs = detect_fractal_candidates(df_eq)
    bis = build_bis(df_eq, select_fractals_for_bi(df_eq, frs))
    segs = build_segments(df_eq, bis)
    zss = build_zhongshus(df_eq, bis, confirm_leave=True, reuse_tail_bi=True)
    shi = classify_shi(df_eq, segs, zss)
    rec = advise_for_today(df_eq, segs, zss, shi)

    # === 等价K索引 -> 原始K索引 映射 ===
    # 这里选择用 src_end 作为该等价K在原始序列上的锚点（稳定、单调递增）
    idx_map = df_eq["src_end"].astype(int).tolist()
    n_map = len(idx_map)

    def eq_to_raw(i: int) -> int:
        if i < 0:
            return 0
        if i >= n_map:
            return len(df) - 1
        return idx_map[i]

    # 分型（可选：如果前端不用分型，仍照旧返回）
    out_frs = [{"idx": eq_to_raw(f.idx), "type": f.type} for f in frs]

    # 笔 / 段：把 start/end 映射到原始K索引
    out_bis = [{"start": eq_to_raw(b.start), "end": eq_to_raw(b.end), "dir": b.dir} for b in bis]
    out_segs = [{"start": eq_to_raw(s.start), "end": eq_to_raw(s.end), "dir": s.dir} for s in segs]

    # 中枢：legs、start/end 也全部映射到原始K索引
    out_zss: List[Dict[str, Any]] = []
    for z in zss:
        # 先在等价K空间求最小/最大，再映射到原始
        ks_eq = min(a for a, _ in z.legs)
        ke_eq = max(b for _, b in z.legs)
        ks_raw = eq_to_raw(ks_eq)
        ke_raw = eq_to_raw(ke_eq)
        low, up = z.price_range
        out_zss.append(
            {
                "start": int(ks_raw),
                "end": int(ke_raw),
                "price_range": [float(low), float(up)],
                "move": z.move,
                "legs": [[eq_to_raw(a), eq_to_raw(b)] for (a, b) in z.legs],
            }
        )

    return {
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

# ===== 路由 =====
# ====== 可选元数据文件（若存在则补充名称/行业等）======
META_FILES = [
    os.path.join(PROJECT_ROOT, "public", "meta", "symbols.json"),  # 建议：由 update_data 生成
    os.path.join(PROJECT_ROOT, "meta", "symbols.json"),
]
def _load_symbol_meta() -> dict[str, dict]:
    for p in META_FILES:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # 允许是 list[ {symbol,...} ] 或 {symbol: {...}}
                if isinstance(data, list):
                    return {d.get("symbol"): d for d in data if d.get("symbol")}
                if isinstance(data, dict):
                    return data
            except Exception:
                traceback.print_exc()
    return {}

def _list_csv_symbols() -> list[str]:
    syms: set[str] = set()
    for d in DATA_DIRS:
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if name.lower().endswith(".csv"):
                syms.add(os.path.splitext(name)[0])
    return sorted(syms)

@app.get("/api/symbols")
def api_symbols(q: Optional[str] = Query(None, description="按代码或名称模糊搜索（可选）"),
                limit: int = Query(2000, ge=1, le=10000)) -> Dict[str, Any]:
    """
    返回当前可用（本地已有 CSV）的股票清单。
    若存在 meta/symbols.json，会补充 name/market/industry/area 等字段。
    """
    try:
        all_syms = _list_csv_symbols()
        meta_map = _load_symbol_meta()

        records = []
        for s in all_syms:
            m = meta_map.get(s, {})
            records.append({
                "symbol": s,
                "name": m.get("name"),
                "market": m.get("market"),
                "industry": m.get("industry"),
                "area": m.get("area"),
            })

        if q:
            key = q.lower()
            def hit(rec: dict) -> bool:
                return (key in (rec["symbol"] or "").lower()) or (key in (rec.get("name") or "").lower())
            records = [r for r in records if hit(r)]

        return {"count": min(len(records), limit), "items": records[:limit]}
    except Exception as e:
        print("[symbols error]", e)
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"symbols error: {e}")


@app.get("/api/symbols")
def api_symbols() -> Dict[str, Any]:
    return {"symbols": _list_symbols()}

@app.get("/api/series-c/bundle")
def api_series_c_bundle(
    symbol: str = Query(..., description="带交易所后缀，如 600519.SH"),
    tf: str = Query("1d", description="时间粒度"),
) -> Dict[str, Any]:
    try:
        csv_path = _find_csv(symbol)
        df = _read_ohlcv(csv_path)
        return {
            "symbol": symbol,
            "timeframe": tf,
            "candles": _csv_to_candles(df),
            "ma": [],
            "segments": [],
            "zones": [],
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"bundle error: {e}")

@app.get("/api/analysis")
def api_analysis(
    symbol: str = Query(..., description="带交易所后缀，如 600519.SH"),
    t: Optional[str] = Query(None, description="可选截止日 YYYY-MM-DD"),
    mode: str = Query("precision", description="模式 precision|recall"),
    confirm_leave: bool = Query(True, description="是否要求离开确认"),
    reuse_tail_bi: bool = Query(True, description="是否重用尾笔"),
) -> Dict[str, Any]:
    try:
        return _analyze(symbol, cutoff=t, mode=mode, confirm_leave=confirm_leave, reuse_tail_bi=reuse_tail_bi)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
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
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"market-index error: {e}")
