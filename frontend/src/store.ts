import { create } from "zustand";
import type {
  Candle,
  MALine,
  Segment,
  Zone,
  SeriesCBundle,
  MarketIndex,
  OutputJson,
} from "./types";
import { toUTCTS } from "./utils/format";

/** —— 小工具 —— */
async function fetchJSON<T>(url: string): Promise<T> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} -> HTTP ${r.status}`);
  return r.json() as Promise<T>;
}
async function fetchText(url: string): Promise<string> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} -> HTTP ${r.status}`);
  return r.text();
}
function parseCsvCandles(csv: string): Candle[] {
  const lines = csv.trim().split(/\r?\n/);
  const header = lines.shift()!;
  const cols = header.split(",");
  const idxDate = cols.indexOf("Date");
  const idxOpen = cols.indexOf("Open");
  const idxHigh = cols.indexOf("High");
  const idxLow = cols.indexOf("Low");
  const idxClose = cols.indexOf("Close");
  if ([idxDate, idxOpen, idxHigh, idxLow, idxClose].some((i) => i < 0)) {
    throw new Error("CSV header 缺少必须列");
  }
  return lines.map((ln) => {
    const parts = ln.split(",");
    return {
      time: toUTCTS(parts[idxDate]),
      open: Number(parts[idxOpen]),
      high: Number(parts[idxHigh]),
      low: Number(parts[idxLow]),
      close: Number(parts[idxClose]),
    };
  });
}

type State = {
  symbol: string | null;
  candles: Candle[];
  ma: MALine[];
  segments: Segment[];
  zones: Zone[];
  loading: boolean;
  error: string | null;

  /** 结构输出（给 InsightPanel / Overlays 用） */
  outJson: OutputJson | null;

  /** 市场页数据 */
  market: MarketIndex | null;

  /** === Actions === */
  setSymbol: (s: string) => void;

  /** 从后端 bundle 拉 K线（不含 outJson） */
  loadFromBackend: (symbol: string, tf?: string) => Promise<void>;

  /** 推荐：一次性拉 bundle + analysis（优先 /api，失败回退到 public） */
  loadAllFor: (symbol: string, tf?: string) => Promise<void>;

  /** 本地示例（无后端也能跑）：读取 /data/600519.SH.csv + /out/600519.SH.json */
  loadSeriesCDemo: () => Promise<void>;

  /** 市场索引 */
  loadMarket: () => Promise<void>;

  /** 清空 */
  clear: () => void;
};

export const useDataStore = create<State>((set, get) => ({
  symbol: null,
  candles: [],
  ma: [],
  segments: [],
  zones: [],
  loading: false,
  error: null,

  outJson: null,
  market: null,

  setSymbol(s: string) {
    set({ symbol: s });
  },

  /** 仅从后端拿 series-c/bundle（不包含 outJson） */
  async loadFromBackend(symbol: string, tf: string = "1d") {
    set({ loading: true, error: null, symbol, outJson: null });
    try {
      const data = await fetchJSON<SeriesCBundle>(
        `/api/series-c/bundle?symbol=${encodeURIComponent(symbol)}&tf=${encodeURIComponent(tf)}`
      );
      set({
        symbol: data.symbol,
        candles: data.candles ?? [],
        ma: data.ma ?? [],
        segments: data.segments ?? [],
        zones: data.zones ?? [],
        loading: false,
      });
    } catch (e: any) {
      set({ loading: false, error: e?.message ?? String(e) });
    }
  },

  /** 一次性加载（优先 /api，失败回退到 public 的 /data + /out） */
  async loadAllFor(symbol: string, tf: string = "1d") {
    set({ loading: true, error: null, symbol, outJson: null });

    // 先尝试后端两个接口
    try {
      const [bundle, outJson] = await Promise.all([
        fetchJSON<SeriesCBundle>(
          `/api/series-c/bundle?symbol=${encodeURIComponent(symbol)}&tf=${encodeURIComponent(tf)}`
        ),
        fetchJSON<OutputJson>(`/api/analysis?symbol=${encodeURIComponent(symbol)}`),
      ]);
      set({
        symbol: bundle.symbol,
        candles: bundle.candles ?? [],
        ma: bundle.ma ?? [],
        segments: bundle.segments ?? [],
        zones: bundle.zones ?? [],
        outJson,
        loading: false,
      });
      return;
    } catch {
      // 忽略错误，改走 public 回退
    }

    // 回退：从 public 读 CSV + out json
    try {
      const [csv, outJson] = await Promise.all([
        fetchText(`/data/${symbol}.csv`),
        fetchJSON<OutputJson>(`/out/${symbol}.json`),
      ]);
      const candles = parseCsvCandles(csv);
      set({
        symbol,
        candles,
        ma: [],
        segments: [],
        zones: [],
        outJson,
        loading: false,
      });
    } catch (e: any) {
      set({ loading: false, error: e?.message ?? String(e) });
    }
  },

  /** 固定载入 600519.SH 的本地示例 */
  async loadSeriesCDemo() {
    set({ loading: true, error: null, symbol: "600519.SH", outJson: null });
    try {
      const [csv, outJson] = await Promise.all([
        fetchText(`/data/600519.SH.csv`),
        fetchJSON<OutputJson>(`/out/600519.SH.json`),
      ]);
      const candles = parseCsvCandles(csv);
      set({
        symbol: outJson.meta?.symbol ?? "600519.SH",
        candles,
        ma: [],
        segments: [],
        zones: [],
        outJson,
        loading: false,
      });
    } catch (e: any) {
      set({ loading: false, error: e?.message ?? String(e) });
    }
  },

  async loadMarket() {
    try {
      const data = await fetchJSON<MarketIndex>(`/out/market_index.json`);
      set({ market: data });
    } catch (e: any) {
      set({ error: e?.message ?? String(e) });
    }
  },

  clear() {
    set({
      symbol: null,
      candles: [],
      ma: [],
      segments: [],
      zones: [],
      outJson: null,
      error: null,
    });
  },
}));
