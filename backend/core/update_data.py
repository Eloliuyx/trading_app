# backend/core/update_data.py
from __future__ import annotations
"""
多数据源日K更新（不复权），输出 CSV:
Date,Open,High,Low,Close,Volume[,Amount]

特性：
- Provider: akshare | tushare（自动降级：akshare 失败→tushare）
- 单票 / 全市场（SH|SZ|BJ|ALL）
- 幂等增量（last+1 ~ today）
- 限速 QPS + 抖动 + 指数退避重试
- 并发/分批（建议 workers=1 更稳）
- 断点续跑 (--resume) / 失败清单重跑 (--failures-only)
- 输出目录 --out-dir（默认 ../public/data）
- 不复权：AkShare adjust=""；TuShare 用 pro.daily 原始价
依赖：pandas, akshare(可选), tushare(可选)
"""
import argparse
import concurrent.futures
import os
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, List, Optional, Tuple

import pandas as pd

DATE_FMT = "%Y-%m-%d"
AK_DATE_FMT = "%Y%m%d"

# 路径与默认参数
DEF_OUT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "public", "data"))
DEF_QPS = 0.8
DEF_JITTER = 0.5
DEF_MAX_RETRIES = 3
DEF_TIMEOUT = 20.0
DEF_WORKERS = 1
DEF_BATCH_SIZE = 25
DEF_EXCHANGE = "ALL"
DEF_SINCE = "19900101"
RESUME_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "logs", "update_resume.txt"))
FAIL_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "logs", "update_failures.txt"))
os.makedirs(os.path.dirname(RESUME_FILE), exist_ok=True)

# ------------------ 工具 ------------------
def _today_ak() -> str:
    return datetime.now().strftime(AK_DATE_FMT)

def _sleep_with_qps(qps: float, jitter: float) -> None:
    base = 1.0 / max(1e-6, qps)
    extra = random.random() * max(0.0, jitter)
    time.sleep(base + extra)

def _normalize_symbol(sym: str) -> str:
    s = sym.strip().upper()
    if "." in s:
        return s
    if s.startswith(("60", "68")):
        return s + ".SH"
    if s.startswith(("00", "30")):
        return s + ".SZ"
    if s.startswith(("43", "83", "87")):
        return s + ".BJ"
    return s

def _read_existing(csv_path: str) -> pd.DataFrame:
    if not os.path.exists(csv_path):
        return pd.DataFrame()
    try:
        return pd.read_csv(csv_path)
    except Exception:
        return pd.DataFrame()

def _last_date(df: pd.DataFrame) -> Optional[str]:
    if len(df) == 0 or "Date" not in df.columns:
        return None
    return str(df["Date"].iloc[-1])

def _date_plus_one(datestr: str) -> str:
    d = datetime.strptime(datestr, DATE_FMT) + timedelta(days=1)
    return d.strftime(AK_DATE_FMT)

def _merge_incremental(existing: pd.DataFrame, newly: pd.DataFrame, drop_suspended: bool) -> pd.DataFrame:
    if len(newly) == 0:
        df = existing
    else:
        df = pd.concat([existing, newly], ignore_index=True)
    if drop_suspended and "Volume" in df.columns:
        df = df[df["Volume"].fillna(0) > 0]
    df = df.drop_duplicates(subset=["Date"]).sort_values("Date").reset_index(drop=True)
    return df

def _write_csv(df: pd.DataFrame, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_csv(path, index=False)

# ------------------ Provider 抽象 ------------------
class ProviderError(Exception):
    pass

@dataclass
class HistRequest:
    symbol: str      # 600519.SH
    start: str       # YYYYMMDD
    end: str         # YYYYMMDD
    timeout: float

class BaseProvider:
    name: str = "base"
    def list_a_symbols(self, exchange: str) -> List[str]:
        raise NotImplementedError
    def fetch_hist(self, req: HistRequest) -> pd.DataFrame:
        raise NotImplementedError

# ---- AkShare ----
class AkShareProvider(BaseProvider):
    name = "akshare"
    def __init__(self) -> None:
        try:
            import akshare as ak  # type: ignore
            self.ak = ak
        except Exception as e:
            raise ProviderError("未安装 akshare：pip install akshare") from e

    def list_a_symbols(self, exchange: str) -> List[str]:
        base = self.ak.stock_info_a_code_name()
        syms: List[str] = []
        for _, row in base.iterrows():
            code = str(row["code"])
            if code.startswith(("60", "68")):
                suf = ".SH"
            elif code.startswith(("00", "30")):
                suf = ".SZ"
            elif code.startswith(("43", "83", "87")):
                suf = ".BJ"
            else:
                continue
            s = code + suf
            if exchange == "ALL" or s.endswith("." + exchange):
                syms.append(s)
        return sorted(set(syms))

    def fetch_hist(self, req: HistRequest) -> pd.DataFrame:
        code, _ex = req.symbol.split(".")
        df = self.ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=req.start,
            end_date=req.end,
            adjust="",  # 不复权
        )
        if df is None or len(df) == 0:
            return pd.DataFrame(columns=["日期","开盘","收盘","最高","最低","成交量","成交额"])
        # 统一到规范列
        rename_map = {"日期":"Date","开盘":"Open","最高":"High","最低":"Low","收盘":"Close","成交量":"Volume","成交额":"Amount"}
        out = df.rename(columns=rename_map)
        keep = [c for c in ["Date","Open","High","Low","Close","Volume","Amount"] if c in out.columns]
        out = out.loc[:, keep].copy()
        out["Date"] = pd.to_datetime(out["Date"], errors="coerce").dt.strftime(DATE_FMT)
        for c in ["Open","High","Low","Close","Volume","Amount"]:
            if c in out.columns:
                out[c] = pd.to_numeric(out[c], errors="coerce")
        out = out.dropna(subset=["Date"]).drop_duplicates(subset=["Date"]).sort_values("Date").reset_index(drop=True)
        return out

# ---- TuShare ----
class TuShareProvider(BaseProvider):
    name = "tushare"
    def __init__(self, token: Optional[str]=None) -> None:
        try:
            import tushare as ts  # type: ignore
            self.ts = ts
        except Exception as e:
            raise ProviderError("未安装 tushare：pip install tushare") from e
        tok = token or os.environ.get("TUSHARE_TOKEN") or ""
        if not tok:
            raise ProviderError("TuShare 需要 TOKEN（环境变量 TUSHARE_TOKEN 或 --tushare-token）")
        self.pro = self.ts.pro_api(tok)

    def list_a_symbols(self, exchange: str) -> List[str]:
        # 统一使用 ts_code (xxxxxx.SH/SZ/BJ)
        df = self.pro.stock_basic(fields="ts_code,symbol,name,market,list_status,exchange")
        syms: List[str] = []
        for _, r in df.iterrows():
            ts_code = str(r["ts_code"])  # e.g. 600519.SH
            if exchange == "ALL" or ts_code.endswith("." + exchange):
                syms.append(ts_code)
        return sorted(set(syms))

    def fetch_hist(self, req: HistRequest) -> pd.DataFrame:
        # TuShare 的代码就是 600519.SH
        # pro.daily 返回列：trade_date, open, high, low, close, vol, amount
        df = self.pro.daily(ts_code=req.symbol, start_date=req.start, end_date=req.end)
        if df is None or len(df) == 0:
            return pd.DataFrame(columns=["Date","Open","High","Low","Close","Volume","Amount"])
        out = pd.DataFrame({
            "Date": pd.to_datetime(df["trade_date"], format="%Y%m%d", errors="coerce").dt.strftime(DATE_FMT),
            "Open": pd.to_numeric(df["open"], errors="coerce"),
            "High": pd.to_numeric(df["high"], errors="coerce"),
            "Low":  pd.to_numeric(df["low"], errors="coerce"),
            "Close":pd.to_numeric(df["close"], errors="coerce"),
            "Volume":pd.to_numeric(df["vol"], errors="coerce"),     # 手
            "Amount":pd.to_numeric(df["amount"], errors="coerce"),  # 元
        })
        out = out.dropna(subset=["Date"]).drop_duplicates(subset=["Date"]).sort_values("Date").reset_index(drop=True)
        return out

# ------------------ Provider 组合 ------------------
def _build_providers(primary: str, tushare_token: Optional[str]) -> List[BaseProvider]:
    chain: List[BaseProvider] = []
    primary = primary.lower()
    if primary == "tushare":
        # 先 tushare 后 akshare
        try:
            chain.append(TuShareProvider(tushare_token))
        except Exception as e:
            print(f"[WARN] TuShare 初始化失败：{e}")
        try:
            chain.append(AkShareProvider())
        except Exception as e:
            print(f"[WARN] AkShare 初始化失败：{e}")
    else:
        # 默认先 akshare 后 tushare
        try:
            chain.append(AkShareProvider())
        except Exception as e:
            print(f"[WARN] AkShare 初始化失败：{e}")
        try:
            chain.append(TuShareProvider(tushare_token))
        except Exception as e:
            print(f"[INFO] TuShare 备用不可用：{e}")
    if not chain:
        raise SystemExit("无可用 Provider，请安装/配置 akshare 或 tushare。")
    return chain

def _list_symbols(providers: List[BaseProvider], exchange: str) -> List[str]:
    last_err = None
    for pv in providers:
        try:
            print(f"[LIST] 使用 {pv.name} 列出标的 ...")
            syms = pv.list_a_symbols(exchange)
            if syms:
                print(f"[LIST] {pv.name} 共 {len(syms)} 支")
                return syms
        except Exception as e:
            last_err = e
            print(f"[WARN] {pv.name} 列表失败：{e}")
    if last_err:
        raise last_err  # type: ignore
    return []

# ------------------ 主任务 ------------------
def _task_fetch(symbol: str, out_dir: str, since: str, qps: float, jitter: float,
                max_retries: int, timeout: float, drop_suspended: bool,
                providers: List[BaseProvider]) -> Tuple[str, bool, str]:
    """
    (symbol, ok, msg)
    AkShare 失败 → 自动降级 TuShare（若可用）
    """
    csv_path = os.path.join(out_dir, f"{symbol}.csv")
    symbol = _normalize_symbol(symbol)
    existed = _read_existing(csv_path)
    last = _last_date(existed)

    start = _date_plus_one(last) if last else since
    end = _today_ak()

    if last and datetime.strptime(start, AK_DATE_FMT) > datetime.strptime(end, AK_DATE_FMT):
        return symbol, True, "无新增交易日"

    # provider 链路逐个尝试（每个 provider 内有重试）
    for pv in providers:
        tries = 0
        while True:
            try:
                _sleep_with_qps(qps, jitter)
                df_std = pv.fetch_hist(HistRequest(symbol, start, end, timeout))
                merged = _merge_incremental(existed, df_std, drop_suspended=drop_suspended)
                _write_csv(merged, csv_path)
                mode = "增量" if last else "全量"
                return symbol, True, f"{pv.name} {mode} {start}→{end}，写入 {os.path.relpath(csv_path)}"
            except Exception as e:
                tries += 1
                if tries > max_retries:
                    # 切下一个 provider
                    print(f"[FAIL] {pv.name} {symbol}: {e}")
                    break
                delay = (2 ** (tries - 1)) + random.random() * 0.5
                print(f"[RETRY] {pv.name} {symbol} 第{tries}次重试，等待 {delay:.1f}s：{e}")
                time.sleep(delay)

    return symbol, False, "所有 provider 均失败"

def _batches(items: List[str], batch_size: int) -> Iterable[List[str]]:
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]

# ------------------ CLI ------------------
def main() -> None:
    ap = argparse.ArgumentParser(description="Update A-share daily CSVs (multi-provider, no-adjust)")
    ap.add_argument("--provider", type=str, default="akshare", choices=["akshare","tushare"],
                    help="优先使用的数据源（失败将自动尝试另一个，如可用）")
    ap.add_argument("--tushare-token", type=str, default=None, help="TuShare TOKEN（也可用环境变量 TUSHARE_TOKEN）")

    ap.add_argument("--symbol", type=str, help="单一标的，如 600519.SH")
    ap.add_argument("--symbols-file", type=str, help="按行提供代码列表")
    ap.add_argument("--all", action="store_true", help="全市场（结合 --exchange）")
    ap.add_argument("--exchange", type=str, default=DEF_EXCHANGE, choices=["ALL","SH","SZ","BJ"],
                    help="交易所筛选")
    ap.add_argument("--since", type=str, default=DEF_SINCE, help="首次全量起点 YYYYMMDD")
    ap.add_argument("--out-dir", type=str, default=DEF_OUT_DIR, help="输出目录，默认 ../public/data")

    ap.add_argument("--workers", type=int, default=DEF_WORKERS, help="并发线程数（建议 1）")
    ap.add_argument("--batch-size", type=int, default=DEF_BATCH_SIZE, help="每批数量")
    ap.add_argument("--qps", type=float, default=DEF_QPS, help="每秒请求次数")
    ap.add_argument("--sleep-jitter", type=float, default=DEF_JITTER, help="随机抖动上限秒")
    ap.add_argument("--max-retries", type=int, default=DEF_MAX_RETRIES, help="单 provider 内最大重试")
    ap.add_argument("--timeout", type=float, default=DEF_TIMEOUT, help="单次请求超时秒（目前供扩展）")
    ap.add_argument("--drop-suspended", action="store_true", help="写入前丢弃 Volume==0 行")

    ap.add_argument("--resume", action="store_true", help=f"断点续跑 {os.path.relpath(RESUME_FILE)}")
    ap.add_argument("--failures-only", action="store_true", help=f"仅重跑失败清单 {os.path.relpath(FAIL_FILE)}")

    args = ap.parse_args()
    out_dir = os.path.abspath(args.out_dir)
    os.makedirs(out_dir, exist_ok=True)

    # provider 链
    providers = _build_providers(args.provider, args.tushare_token)

    # 符号列表
    symbols: List[str] = []
    if args.failures_only and os.path.exists(FAIL_FILE):
        with open(FAIL_FILE, "r", encoding="utf-8") as f:
            symbols = [ln.strip() for ln in f if ln.strip()]
        print(f"[RUN] 重跑失败清单：{len(symbols)} 支")
    elif args.symbol:
        symbols = [_normalize_symbol(args.symbol)]
    else:
        if args.symbols_file and os.path.exists(args.symbols_file):
            with open(args.symbols_file, "r", encoding="utf-8") as f:
                symbols = [ _normalize_symbol(ln.strip()) for ln in f if ln.strip() ]
        if args.all or not symbols:
            symbols = _list_symbols(providers, args.exchange)

    # 断点续跑过滤
    if args.resume and os.path.exists(RESUME_FILE):
        with open(RESUME_FILE, "r", encoding="utf-8") as f:
            done = {ln.strip() for ln in f if ln.strip()}
        before = len(symbols)
        symbols = [s for s in symbols if s not in done]
        print(f"[RESUME] 过滤已完成 {before - len(symbols)}，剩余 {len(symbols)}")

    if not symbols:
        print("[SKIP] 无待处理标的")
        return

    failures: List[str] = []

    for batch in _batches(symbols, args.batch_size):
        print(f"[Batch] {len(batch)} symbols ...")
        if args.workers and args.workers > 1:
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as ex:
                futs = {
                    ex.submit(_task_fetch, sym, out_dir, args.since, args.qps, args.sleep_jitter,
                              args.max_retries, args.timeout, args.drop_suspended, providers): sym
                    for sym in batch
                }
                for fut in concurrent.futures.as_completed(futs):
                    sym = futs[fut]
                    ok = True
                    msg = ""
                    try:
                        sym2, ok, msg = fut.result()
                    except Exception as e:
                        ok = False
                        msg = f"{type(e).__name__}: {e}"
                        sym2 = sym
                    status = "OK" if ok else "FAIL"
                    print(f"[{status}] {sym2}: {msg}")
                    if ok:
                        with open(RESUME_FILE, "a", encoding="utf-8") as rf:
                            rf.write(sym2 + "\n")
                    else:
                        failures.append(sym2)
        else:
            for sym in batch:
                sym2, ok, msg = _task_fetch(
                    sym, out_dir, args.since, args.qps, args.sleep_jitter,
                    args.max_retries, args.timeout, args.drop_suspended, providers
                )
                status = "OK" if ok else "FAIL"
                print(f"[{status}] {sym2}: {msg}")
                if ok:
                    with open(RESUME_FILE, "a", encoding="utf-8") as rf:
                        rf.write(sym2 + "\n")
                else:
                    failures.append(sym2)

    if failures:
        with open(FAIL_FILE, "w", encoding="utf-8") as ff:
            ff.write("\n".join(sorted(set(failures))) + "\n")
        print(f"[DONE] 完成，但有失败 {len(failures)} 支 → {os.path.relpath(FAIL_FILE)}")
    else:
        if os.path.exists(FAIL_FILE):
            os.remove(FAIL_FILE)
        print("[DONE] 全部完成，无失败")
    print(f"[OUT] CSV 输出目录：{out_dir}")
    print(f"[RESUME] 记录文件：{os.path.relpath(RESUME_FILE)}")

if __name__ == "__main__":
    main()
