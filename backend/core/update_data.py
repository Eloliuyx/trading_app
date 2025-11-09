# backend/core/update_data.py
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

# === 路径约定：默认写入项目根 /public/data ===
PROJ = Path(__file__).resolve().parents[2]
PUBLIC = PROJ / "public"
DEFAULT_OUT = PUBLIC / "data"
DEFAULT_MANIFEST = PUBLIC / "data_index.json"

TZ_SH = timezone(timedelta(hours=8))


# ----------------- 工具函数 -----------------
def _to_ts_date(d: datetime) -> str:
    return d.strftime("%Y%m%d")  # yyyymmdd


def _date_str_yyyymmdd(s: str) -> str:
    return s.replace("-", "")


def _today_cn() -> datetime:
    return datetime.now(TZ_SH)


def _ymd_to_int(s: str) -> int:
    return int(s.replace("-", ""))


# ----------------- 读写 CSV -----------------
def read_existing(csv_path: Path) -> Optional[pd.DataFrame]:
    if not csv_path.exists():
        return None
    df = pd.read_csv(csv_path)
    need = ["Date", "Open", "High", "Low", "Close", "Volume"]
    miss = [c for c in need if c not in df.columns]
    if miss:
        return None
    df["Date"] = pd.to_datetime(df["Date"])
    return df.sort_values("Date").reset_index(drop=True)


def save_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


# ----------------- Manifest（不逐个读 CSV，挑落后者） -----------------
def load_manifest(path: Path) -> Dict[str, str]:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_manifest(path: Path, data: Dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)


def tail_last_date_from_csv(csv_path: Path) -> Optional[str]:
    if not csv_path.exists():
        return None
    try:
        with open(csv_path, "rb") as f:
            try:
                f.seek(-1024, os.SEEK_END)
            except OSError:
                f.seek(0)
            tail = f.read().decode("utf-8", errors="ignore").strip().splitlines()
    except Exception:
        return None
    for line in reversed(tail):
        if not line or line.lower().startswith("date"):
            continue
        parts = line.split(",")
        if parts:
            dt_str = parts[0].strip()
            if len(dt_str) == 10 and dt_str[4] == "-" and dt_str[7] == "-":
                return dt_str
    return None


def build_manifest_from_dir(out_dir: Path) -> Dict[str, str]:
    m: Dict[str, str] = {}
    for p in sorted(out_dir.glob("*.csv")):
        name = p.name
        if name.lower() == "symbols.csv":
            continue
        sym = name[:-4]
        last = tail_last_date_from_csv(p)
        if last:
            m[sym] = last  # YYYY-MM-DD
    return m


def update_manifest_entry(manifest_path: Path, sym: str, new_last_day: str) -> None:
    m = load_manifest(manifest_path)
    if _ymd_to_int(new_last_day) > _ymd_to_int(m.get(sym, "1900-01-01")):
        m[sym] = new_last_day
        save_manifest(manifest_path, m)


# ----------------- Tushare 实现 -----------------
def _tushare_client(token: Optional[str]):
    import tushare as ts

    if token:
        return ts.pro_api(token)
    return ts.pro_api()


def _latest_trading_day_by_benchmark(pro, bench_symbol: str) -> str:
    """
    不用 trade_cal，改用基准股票在最近 10 天的日线数据，取最大 trade_date。
    返回 YYYY-MM-DD。
    """
    today = _today_cn().date()
    end_i = int(today.strftime("%Y%m%d"))
    start_dt = today - timedelta(days=10)
    start_i = int(start_dt.strftime("%Y%m%d"))
    df = pro.daily(ts_code=bench_symbol, start_date=str(start_i), end_date=str(end_i))
    if df is None or df.empty:
        # 兜底：用“今天”，即使非交易日，下游增量拉取也会安全（返回空）
        return today.isoformat()
    last = str(df["trade_date"].max())  # e.g. 20251103
    return f"{last[:4]}-{last[4:6]}-{last[6:8]}"


def _fetch_daily_with_basic_tushare(
    pro,
    ts_code: str,
    start_date: Optional[str],
    end_date: Optional[str],
) -> pd.DataFrame:
    """
    从 tushare 抓取日线 + daily_basic(turnover_rate)，合并为一张表：
    - Date, Open, High, Low, Close, Volume
    - TurnoverRate: 换手率（小数，0.01 = 1%）
    """
    params = {"ts_code": ts_code}
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date

    # 日线
    df_daily = pro.daily(**params)
    if df_daily is None or df_daily.empty:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume", "TurnoverRate"])

    # daily_basic: 只拿 turnover_rate，减少积分
    df_basic = pro.daily_basic(
        ts_code=ts_code,
        start_date=params.get("start_date"),
        end_date=params.get("end_date"),
        fields="ts_code,trade_date,turnover_rate",
    )
    if df_basic is None or df_basic.empty:
        df_basic = pd.DataFrame(columns=["ts_code", "trade_date", "turnover_rate"])

    # 合并
    df = df_daily.merge(
        df_basic,
        on=["ts_code", "trade_date"],
        how="left",
        suffixes=("", "_basic"),
    )

    df = df.sort_values("trade_date").reset_index(drop=True)

    # 构造输出
    out = pd.DataFrame(
        {
            "Date": pd.to_datetime(df["trade_date"]),
            "Open": df["open"].astype(float),
            "High": df["high"].astype(float),
            "Low": df["low"].astype(float),
            "Close": df["close"].astype(float),
            "Volume": df["vol"].astype(float),  # 单位：手
        }
    )

    # TurnoverRate：转为小数（0.xx），缺失保持 NaN
    if "turnover_rate" in df.columns:
        tr = pd.to_numeric(df["turnover_rate"], errors="coerce") / 100.0
    else:
        tr = pd.Series([float("nan")] * len(out))
    out["TurnoverRate"] = tr

    return out


def _merge_incremental(existing: Optional[pd.DataFrame], new_df: pd.DataFrame) -> pd.DataFrame:
    if existing is None or existing.empty:
        return new_df
    if new_df is None or new_df.empty:
        return existing

    # 兼容老 CSV 没有 TurnoverRate 的情况：补列为 NaN 再 concat
    for col in ["TurnoverRate"]:
        if col not in existing.columns:
            existing[col] = float("nan")
        if col not in new_df.columns:
            new_df[col] = float("nan")

    merged = pd.concat([existing, new_df], ignore_index=True)
    merged = merged.drop_duplicates(subset=["Date"]).sort_values("Date").reset_index(drop=True)
    return merged


def update_one_tushare(
    pro,
    ts_code: str,
    out_dir: Path,
    latest_open_day: str,  # YYYY-MM-DD（用基准股票推断）
    last_date_hint: Optional[str] = None,  # 来自 manifest 的提示，减少一次读盘
) -> None:
    """
    增量逻辑：
    - 若无文件：全量从 1990-01-01 拉到 latest_open_day
    - 若有文件：从 (最后一行日期 + 1日) 拉到 latest_open_day，append 去重
    """
    csv_path = out_dir / f"{ts_code}.csv"
    end_yyyymmdd = _date_str_yyyymmdd(latest_open_day)

    existing: Optional[pd.DataFrame] = None
    last_dt = None
    if csv_path.exists() and last_date_hint:
        try:
            last_dt = datetime.fromisoformat(last_date_hint).date()
        except Exception:
            existing = read_existing(csv_path)
            if existing is not None and not existing.empty:
                last_dt = existing["Date"].iloc[-1].date()
    else:
        existing = read_existing(csv_path)
        if existing is not None and not existing.empty:
            last_dt = existing["Date"].iloc[-1].date()

    if last_dt is None:
        start_yyyymmdd = "19900101"
    else:
        start_dt = last_dt + timedelta(days=1)
        if start_dt > datetime.fromisoformat(latest_open_day).date():
            print(f"[skip] {ts_code} up-to-date ({last_dt})")
            return
        start_yyyymmdd = _to_ts_date(
            datetime(start_dt.year, start_dt.month, start_dt.day, tzinfo=TZ_SH)
        )

    new_df = _fetch_daily_with_basic_tushare(
        pro,
        ts_code=ts_code,
        start_date=start_yyyymmdd,
        end_date=end_yyyymmdd,
    )

    if existing is None and csv_path.exists():
        existing = read_existing(csv_path)

    merged = _merge_incremental(existing, new_df)
    if merged is None or merged.empty:
        print(f"[warn] {ts_code} no data returned")
        return

    save_csv(merged, csv_path)
    last = merged["Date"].iloc[-1].date()
    print(
        f"[ok] {ts_code}: {len(existing) if existing is not None else 0} -> {len(merged)} rows (last={last})"
    )


# ----------------- 任务选择 -----------------
def iter_symbols_from_public_data(out_dir: Path) -> List[str]:
    syms = []
    for p in sorted(out_dir.glob("*.csv")):
        name = p.name
        if name.lower() == "symbols.csv":
            continue
        sym = name[:-4]  # 去 .csv
        if "." in sym:
            syms.append(sym)
    return syms


def select_stale_symbols(
    latest_open_day: str, symbols: List[str], manifest_path: Path
) -> List[str]:
    """
    使用 manifest 与 latest_open_day 对比，仅挑“落后”的 symbol。
    不逐个读 CSV。
    """
    m = load_manifest(manifest_path)
    if not m:
        return symbols  # 没有 manifest 时退化为全量，后续会在 update_one 内部自跳过
    latest_i = _ymd_to_int(latest_open_day)
    stale: List[str] = []
    for sym in symbols:
        last = m.get(sym, "1900-01-01")
        if _ymd_to_int(last) < latest_i:
            stale.append(sym)
    return stale


# ----------------- CLI -----------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=["tushare"], default="tushare")
    parser.add_argument("--token", help="Tushare token（可不填，默认读环境变量 TUSHARE_TOKEN）")
    parser.add_argument(
        "--all",
        action="store_true",
        help="更新 out_dir 下已存在的全部 symbol（或 symbols.csv 列表）",
    )
    parser.add_argument("--symbol", help="仅更新单只，如 600519.SH")
    parser.add_argument(
        "--out-dir", default=str(DEFAULT_OUT), help="输出目录，默认项目根/public/data"
    )

    # manifest / 只更新落后 / 窗口限制 / 基准股票
    parser.add_argument(
        "--build-manifest", action="store_true", help="仅从现有 CSV 构建 manifest 索引后退出"
    )
    parser.add_argument(
        "--only-stale",
        action="store_true",
        help="仅处理 manifest 判定为落后的 symbol（不逐个读 CSV）",
    )
    parser.add_argument(
        "--manifest",
        default=str(DEFAULT_MANIFEST),
        help="manifest 文件路径，默认 public/data_index.json",
    )
    parser.add_argument(
        "--since-days", type=int, default=None, help="最多回补最近 N 天（可选；用于限制抓取窗口）"
    )
    parser.add_argument(
        "--bench-symbol", default="000001.SZ", help="用此基准股票推断最近开市日（默认 000001.SZ）"
    )

    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(args.manifest).resolve()

    if args.provider != "tushare":
        raise SystemExit("当前只实现 tushare")

    pro = _tushare_client(args.token)

    # ---- 构建 manifest 并退出 ----
    if args.build_manifest:
        syms = iter_symbols_from_public_data(out_dir)
        if not syms:
            print(f"[hint] {out_dir} 下没有现成 csv；先放入历史数据再构建 manifest。")
            return
        m = build_manifest_from_dir(out_dir)
        save_manifest(manifest_path, m)
        print(f"[manifest] 写入 {manifest_path}，共 {len(m)} 条。")
        return

    # 用基准股票推断最近开市日（兼容只有日线权限的账号）
    latest_open_day = _latest_trading_day_by_benchmark(pro, args.bench_symbol)  # YYYY-MM-DD

    # ---- 选择待更新 symbol ----
    if args.symbol:
        todo = [args.symbol]
    elif args.all:
        base = iter_symbols_from_public_data(out_dir)
        if args.only_stale:
            todo = select_stale_symbols(latest_open_day, base, manifest_path)
            print(
                f"[plan] only-stale: {len(todo)} / {len(base)} 需要更新（最新开市日 {latest_open_day}）"
            )
        else:
            todo = base
    else:
        print("用法示例：")
        print("  # 扫描一次现有 CSV，建立索引")
        print(
            "  python -m backend.core.update_data --provider tushare --build-manifest --manifest public/data_index.json"
        )
        print("  # 之后每天只更新确实落后的（不逐个读 CSV）")
        print(
            "  python -m backend.core.update_data --provider tushare --all --only-stale --manifest public/data_index.json"
        )
        print("  # 只用日线推断最新开市日，指定基准股票")
        print(
            "  python -m backend.core.update_data --provider tushare --all --only-stale --bench-symbol 000001.SZ"
        )
        print("  # 单只更新")
        print("  python -m backend.core.update_data --provider tushare --symbol 600519.SH")
        return

    if not todo:
        print("[done] 所有 symbol 均已最新，无需更新。")
        return

    # 预计算 end_yyyymmdd
    end_yyyymmdd = _date_str_yyyymmdd(latest_open_day)

    # 限制窗口（只影响 start 的下限，真正截取在 update_one 里靠 end 控制）
    cutoff_i: Optional[int] = None
    if args.since_days:
        cutoff_dt = datetime.fromisoformat(latest_open_day).date() - timedelta(days=args.since_days)
        cutoff_i = int(cutoff_dt.strftime("%Y%m%d"))

    manifest_cache = load_manifest(manifest_path)

    for ts_code in todo:
        try:
            hint = manifest_cache.get(ts_code)

            # 如果限制窗口且存在 hint，提前检查是否无需更新
            if hint and cutoff_i is not None:
                try:
                    last_dt = datetime.fromisoformat(hint).date()
                    start_dt = last_dt + timedelta(days=1)
                    start_i = int(start_dt.strftime("%Y%m%d"))
                    if start_i > int(end_yyyymmdd):
                        print(f"[skip] {ts_code} up-to-date ({hint})")
                        continue
                except Exception:
                    pass

            update_one_tushare(
                pro=pro,
                ts_code=ts_code,
                out_dir=out_dir,
                latest_open_day=latest_open_day,
                last_date_hint=hint,
            )

            # 成功后把 manifest 更新到 latest_open_day
            update_manifest_entry(manifest_path, ts_code, latest_open_day)

            time.sleep(1.3)  # 降速，省积分
        except Exception as e:
            print(f"[error] {ts_code}: {e}")


if __name__ == "__main__":
    main()
