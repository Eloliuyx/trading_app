// src/store.ts
import { create } from "zustand";

/** ========= 基础类型 ========= */

export type PriceLine = { id: string; price: number; title?: string };

export type Note = { id: string; ts: string; text: string };

export type MarketSnapshot = {
  asof?: string;
  last_bar_date?: string;
  rules_version?: string;
  status?: "OK" | "NO_DATA" | "ERROR";
  error?: string;
  [k: string]: any;
};

export type StockItem = {
  symbol: string;
  name: string;
  industry?: string;
  market?: string;
  last_date?: string;
  is_st?: boolean;
  score?: number;
  bucket?: string;
  reasons?: string[];
  [k: string]: any;
};

export type KLineBar = {
  time: string | number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
};

/** ========= F1-F9 ========= */

export type FKey = "F1" | "F2" | "F3" | "F4" | "F5" | "F6" | "F7" | "F8" | "F9";

export type FilterState = {
  q: string;
} & { [K in FKey]: boolean };

const defaultFilter: FilterState = {
  q: "",
  F1: false,
  F2: false,
  F3: false,
  F4: false,
  F5: false,
  F6: false,
  F7: false,
  F8: false,
  F9: false,
};

type FactorConfig = {
  key: FKey;
  label: string;
  test: (s: StockItem) => boolean;
};

export const FACTOR_CONFIG: FactorConfig[] = [
  {
    key: "F1",
    label: "F1 剔除ST/风险股",
    test: (s) => {
      if (s.f_exclude_st !== undefined) return !!s.f_exclude_st;
      if (s.is_st !== undefined) return !s.is_st;
      return true;
    },
  },
  {
    key: "F2",
    label: "F2 强流动性",
    test: (s) => {
      if (s.f_liquid_strong !== undefined) return !!s.f_liquid_strong;
      const v = s.amt60_avg;
      if (v == null) return true;
      return v >= 50_000_000;
    },
  },
  {
    key: "F3",
    label: "F3 合理价格区间",
    test: (s) => {
      if (s.f_price_floor !== undefined) return !!s.f_price_floor;
      const c = s.close;
      if (c == null) return true;
      return c >= 3 && c <= 80;
    },
  },
  {
    key: "F4",
    label: "F4 高成交额",
    test: (s) => {
      const a = s.amount_t ?? s.amount;
      if (a == null) return true;
      return a >= 20_000_000;
    },
  },
  {
    key: "F5",
    label: "F5 放量确认",
    test: (s) => {
      const vr = s.vr ?? s.vol_ratio20 ?? s.vol_ratio10;
      if (vr == null) return true;
      return vr >= 1.2;
    },
  },
  {
    key: "F6",
    label: "F6 行业相对强",
    test: (s) => {
      const r = s.industry_rs20 ?? s.industry_rs ?? s.industry_rank;
      if (r == null) return true;
      return (r > 0 && r <= 0.3) || r <= 30;
    },
  },
  {
    key: "F7",
    label: "F7 强势行业/主题",
    test: () => true,
  },
  {
    key: "F8",
    label: "F8 多头均线",
    test: (s) => {
      const f = s.f_bull_ma ?? s.trend_bull ?? s.bull_ma;
      if (f == null) return true;
      return !!f;
    },
  },
  {
    key: "F9",
    label: "F9 突破/趋势强化",
    test: (s) => {
      const f = s.f_breakout ?? s.trend_breakout;
      if (f == null) return true;
      return !!f;
    },
  },
];

/** ========= 工具 ========= */

async function fetchJSON(url: string) {
  const res = await fetch(url, { cache: "no-cache" });
  if (!res.ok) throw new Error(`HTTP ${res.status} ${url}`);
  return res.json();
}

async function fetchText(url: string) {
  const res = await fetch(url, { cache: "no-cache" });
  if (!res.ok) throw new Error(`HTTP ${res.status} ${url}`);
  return res.text();
}

/** JSON -> K线 */
function normalizeKlineFromJson(raw: any): KLineBar[] {
  const arr: any[] =
    Array.isArray(raw) ? raw :
    Array.isArray(raw.list) ? raw.list :
    Array.isArray(raw.bars) ? raw.bars :
    [];
  return arr
    .map((b) => {
      const time = b.time ?? b.date ?? b.Date ?? b.trade_date;
      const open = b.open ?? b.Open;
      const high = b.high ?? b.High;
      const low = b.low ?? b.Low;
      const close = b.close ?? b.Close;
      const vol = b.volume ?? b.Volume ?? b.vol;
      if (
        time === undefined ||
        open === undefined ||
        high === undefined ||
        low === undefined ||
        close === undefined
      )
        return null;
      return {
        time,
        open: Number(open),
        high: Number(high),
        low: Number(low),
        close: Number(close),
        volume: vol != null ? Number(vol) : undefined,
      } as KLineBar;
    })
    .filter(Boolean) as KLineBar[];
}

/** CSV(Date,Open,High,Low,Close,Volume) -> K线 */
function normalizeKlineFromCsv(text: string): KLineBar[] {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length <= 1) return [];
  const headers = lines[0].split(",").map((s) => s.trim());
  const idx = (name: string) =>
    headers.findIndex((h) => h.toLowerCase() === name.toLowerCase());
  const iDate = idx("Date");
  const iOpen = idx("Open");
  const iHigh = idx("High");
  const iLow = idx("Low");
  const iClose = idx("Close");
  const iVol = idx("Volume");
  if (iDate < 0 || iOpen < 0 || iHigh < 0 || iLow < 0 || iClose < 0) {
    return [];
  }
  const out: KLineBar[] = [];
  for (let i = 1; i < lines.length; i++) {
    if (!lines[i]) continue;
    const cols = lines[i].split(",");
    const time = cols[iDate];
    const open = Number(cols[iOpen]);
    const high = Number(cols[iHigh]);
    const low = Number(cols[iLow]);
    const close = Number(cols[iClose]);
    const vol = iVol >= 0 ? Number(cols[iVol]) : undefined;
    if ([open, high, low, close].some((v) => Number.isNaN(v))) continue;
    out.push({ time, open, high, low, close, volume: vol });
  }
  return out;
}

/** notes 持久化 */

const NOTES_KEY = "ta_notes_v1";

function loadInitialNotesMap(): Record<string, Note[]> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(NOTES_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function saveNotesMap(map: Record<string, Note[]>) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(NOTES_KEY, JSON.stringify(map));
  } catch {
    // ignore
  }
}

/** ========= Store ========= */

type DataStore = {
  market: MarketSnapshot | null;
  stocks: StockItem[];
  selectedSymbol: string | null;
  filter: FilterState;

  klineMap: Record<string, KLineBar[]>;
  lineMap: Record<string, PriceLine[]>;
  notesMap: Record<string, Note[]>;

  loadMarket: () => Promise<void>;
  setFilter: (patch: Partial<FilterState>) => void;
  toggleFlag: (key: FKey) => void;
  setSelectedSymbol: (symbol: string | null) => void;

  loadKline: (symbol: string) => Promise<void>;
  getLines: (symbol: string) => PriceLine[];
  addLine: (symbol: string, line: PriceLine) => void;
  removeLine: (symbol: string, id: string) => void;

  getNotes: (symbol: string) => Note[];
  addNote: (symbol: string, text: string) => void;
  deleteNote: (symbol: string, id: string) => void;
};

export const useDataStore = create<DataStore>((set, get) => ({
  market: null,
  stocks: [],
  selectedSymbol: null,
  filter: defaultFilter,
  klineMap: {},
  lineMap: {},
  notesMap: loadInitialNotesMap(),

  async loadMarket() {
    try {
      let raw: any;
      try {
        raw = await fetchJSON("/out/universe.json");
      } catch {
        raw = await fetchJSON("/universe.json");
      }

      let listRaw: any[] = [];
      let asof: string | undefined;
      let lastBarDate: string | undefined;
      let rulesVersion: string | undefined;

      if (Array.isArray(raw)) {
        listRaw = raw;
      } else if (Array.isArray(raw.list)) {
        listRaw = raw.list;
        asof = raw.asof;
        lastBarDate = raw.last_bar_date;
        rulesVersion = raw.rules_version;
      } else {
        throw new Error("universe.json format invalid");
      }

      const list: StockItem[] = listRaw.map((it) => {
        const { features, ...rest } = it;
        return { ...rest, ...(features || {}) } as StockItem;
      });

      const market: MarketSnapshot = {
        asof,
        last_bar_date: lastBarDate,
        rules_version: rulesVersion,
        status: list.length ? "OK" : "NO_DATA",
      };

      set({ market, stocks: list });
    } catch (e: any) {
      console.error("[loadMarket] failed:", e);
      set({
        market: {
          status: "ERROR",
          error: e?.message || String(e),
        },
        stocks: [],
      });
    }
  },

  setFilter(patch) {
    set((state) => ({
      filter: { ...state.filter, ...patch },
    }));
  },

  toggleFlag(key) {
    set((state) => ({
      filter: { ...state.filter, [key]: !state.filter[key] },
    }));
  },

  setSelectedSymbol(symbol) {
    set({ selectedSymbol: symbol });
  },

  async loadKline(symbol) {
    if (!symbol) return;
    const cached = get().klineMap[symbol];
    if (cached && cached.length) return;

    const jsonUrls = [
      `/out/${symbol}.json`,
      `/out/kline/${symbol}.json`,
      `/kline/${symbol}.json`,
    ];
    for (const url of jsonUrls) {
      try {
        const raw = await fetchJSON(url);
        const bars = normalizeKlineFromJson(raw);
        if (bars.length) {
          set((state) => ({
            klineMap: { ...state.klineMap, [symbol]: bars },
          }));
          return;
        }
      } catch {
        // try next
      }
    }

    const csvUrls = [`/data/${symbol}.csv`];
    for (const url of csvUrls) {
      try {
        const text = await fetchText(url);
        const bars = normalizeKlineFromCsv(text);
        if (bars.length) {
          set((state) => ({
            klineMap: { ...state.klineMap, [symbol]: bars },
          }));
          return;
        }
      } catch {
        // try next
      }
    }

    console.warn(`[loadKline] no kline for ${symbol}`);
    set((state) => ({
      klineMap: { ...state.klineMap, [symbol]: [] },
    }));
  },

  getLines(symbol) {
    return get().lineMap[symbol] || [];
  },

  addLine(symbol, line) {
    if (!symbol) return;
    set((state) => {
      const prev = state.lineMap[symbol] || [];
      const next = { ...state.lineMap, [symbol]: [...prev, line] };
      return { lineMap: next };
    });
  },

  removeLine(symbol, id) {
    if (!symbol) return;
    set((state) => {
      const prev = state.lineMap[symbol] || [];
      const next = {
        ...state.lineMap,
        [symbol]: prev.filter((l) => l.id !== id),
      };
      return { lineMap: next };
    });
  },

  getNotes(symbol) {
    if (!symbol) return [];
    return get().notesMap[symbol] || [];
  },

  addNote(symbol, text) {
    if (!symbol || !text.trim()) return;
    const note: Note = {
      id: `n_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      ts: new Date().toISOString(),
      text: text.trim(),
    };
    set((state) => {
      const prev = state.notesMap[symbol] || [];
      const nextMap = {
        ...state.notesMap,
        [symbol]: [note, ...prev],
      };
      saveNotesMap(nextMap);
      return { notesMap: nextMap };
    });
  },

  deleteNote(symbol, id) {
    if (!symbol) return;
    set((state) => {
      const prev = state.notesMap[symbol] || [];
      const nextMap = {
        ...state.notesMap,
        [symbol]: prev.filter((n) => n.id !== id),
      };
      saveNotesMap(nextMap);
      return { notesMap: nextMap };
    });
  },
}));
