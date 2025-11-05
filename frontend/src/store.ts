import { create } from "zustand";

/** —— 类型 —— */
export type PriceLine = { id: string; price: number; title?: string };
export type Note = { id: string; date: string; text: string };

export type FilterState = { [k: string]: any };

export type MarketPoint = {
  ts?: string;
  date?: string;
  name?: string;
  value?: number;
  [k: string]: any;
};

export type MarketSnapshot = {
  asof?: string;
  indices?: MarketPoint[];
  breadth?: MarketPoint[];
  [k: string]: any;
};

export type StockItem = {
  symbol: string;
  name: string;
  industry?: string;
  market?: string;
  reco?: string;
  score?: number;
  bucket?: string;
  features?: Record<string, any>;
};

export type StockLite = StockItem;

export type UniverseRaw = {
  asof?: string;
  list: any[];
};

export type DataStore = {
  asof: string | null;
  stocks: StockItem[];
  symbols: StockItem[];
  filter: FilterState;

  selectedSymbol: string | null;
  setSelectedSymbol: (s: string | null) => void;

  symbol: string | null;
  setSymbol: (s: string | null) => void;

  setFilter: (p: Partial<FilterState>) => void;
  setStocks: (items: StockItem[]) => void;

  outJson: UniverseRaw | null;
  loadSymbols: () => Promise<void>;
  loadAllFor: (symbol: string) => Promise<void>;

  kline: Record<string, any>;
  analysis: Record<string, any>;

  getLines: (symbol: string) => PriceLine[];
  addLine: (symbol: string, price: number, title?: string) => void;
  removeLine: (symbol: string, id: string) => void;
  replaceLines: (symbol: string, lines: PriceLine[]) => void;

  getNotes: (symbol: string) => Note[];
  addNote: (symbol: string, text: string) => void;
  deleteNote: (symbol: string, id: string) => void;

  loadMarket: () => Promise<void>;
  market: MarketSnapshot | null;
};

/** —— 本地存取工具 —— */
const keyLines = (sym: string) => `lines_${sym}`;
const keyNotes = (sym: string) => `notes_${sym}`;

function readJSON<T>(key: string, fallback: T): T {
  try {
    const s = localStorage.getItem(key);
    return s ? (JSON.parse(s) as T) : fallback;
  } catch {
    return fallback;
  }
}
function writeJSON<T>(key: string, v: T) {
  try {
    localStorage.setItem(key, JSON.stringify(v));
  } catch {}
}

function toNum(v: any): number | null {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}
function isNum(v: any): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

/** —— 将 /out/universe.json 的一项归一成 StockItem —— */
function normalizeItem(it: any): StockItem {
  const f0 = (it?.features ?? {}) as Record<string, any>;

  // 兼容 amt60_avg 在顶层或 features 中
  const amt60 =
    (typeof f0.amt60_avg === "number" ? f0.amt60_avg : undefined) ??
    (typeof it.amt60_avg === "number" ? it.amt60_avg : undefined) ??
    0;

  // 抽出常用原始数值
  const close = toNum(f0.close ?? it.close);
  const amount_t = toNum(f0.amount_t ?? it.amount_t);        // 今日成交额
  const vr = toNum(f0.vr ?? it.vr);                           // 相对均量
  const ma5 = toNum(f0.ma5 ?? it.ma5);
  const ma13 = toNum(f0.ma13 ?? it.ma13);
  const ma39 = toNum(f0.ma39 ?? it.ma39);
  const indRS = toNum(f0.industry_rs20 ?? it.industry_rs20);  // 板块强弱 0~1

  const features: Record<string, any> = {
    ...f0,
    amt60_avg: Number.isFinite(amt60) ? amt60 : 0,
  };

  // 把顶层可能存在的 f_* 也纳入 features（不覆盖已有）
  for (const k of Object.keys(it ?? {})) {
    if (k.startsWith("f_") && features[k] === undefined) {
      features[k] = it[k];
    }
  }

  // ===== 前端兜底：若缺失则依据数值派生（偏宽松，避免全空） =====
  const AMT_RATIO = 1.05;  // 今日成交额 ≥ 1.05 × 60日均额
  const VR_MIN = 1.10;     // VR ≥ 1.10
  const IND_TOP5 = 0.70;   // 行业Top5 近似
  const IND_STRONG = 0.60; // 强势板块近似
  const BULL_TOL = 0.97;   // 收盘 ≥ 0.97 × MA5 且 MA5≥MA13≥MA39

  if (features.f_high_amt === undefined) {
    features.f_high_amt =
      isNum(amount_t) && isNum(amt60) && amt60 > 0 && amount_t >= AMT_RATIO * amt60;
  }

  if (features.f_high_vr === undefined) {
    features.f_high_vr = isNum(vr) && vr >= VR_MIN;
  }

  if (features.f_ind_rank_top5 === undefined) {
    features.f_ind_rank_top5 = isNum(indRS) && indRS >= IND_TOP5;
  }

  if (features.f_strong_industry === undefined) {
    features.f_strong_industry = isNum(indRS) && indRS >= IND_STRONG;
  }

  if (features.f_bull_ma === undefined) {
    features.f_bull_ma =
      isNum(ma5) &&
      isNum(ma13) &&
      isNum(ma39) &&
      ma5 >= ma13 &&
      ma13 >= ma39 &&
      isNum(close) &&
      close >= BULL_TOL * ma5;
  }
  // ============================================================

  return {
    symbol: it.symbol,
    name: it.name,
    industry: it.industry,
    market: it.market,
    reco: it.reco,
    score: it.score,
    features,
  };
}

/** —— Zustand Store —— */
export const useDataStore = create<DataStore>((set, get) => ({
  asof: null,
  stocks: [],
  symbols: [],
  market: null,
  filter: {},

  selectedSymbol: null,
  setSelectedSymbol: (s) => set({ selectedSymbol: s, symbol: s }),

  // ➕ 别名：保持与 selectedSymbol 同步
  symbol: null,
  setSymbol: (s) => set({ selectedSymbol: s, symbol: s }),

  setFilter: (p) => set((s) => ({ filter: { ...s.filter, ...p } })),

  // ⭐ 关键修复：任何入口来的 items，都统一 normalize 一遍
  setStocks: (items) => {
    const normalized = (items ?? []).map(normalizeItem);
    // 默认按流动性降序
    normalized.sort((a, b) => {
      const av = Number(a.features?.amt60_avg ?? 0);
      const bv = Number(b.features?.amt60_avg ?? 0);
      return bv - av;
    });
    set({
      stocks: normalized,
      symbols: normalized,
    });
  },

  // —— 载入 universe —— //
  outJson: null,
  kline: {},
  analysis: {},

  loadSymbols: async () => {
    if (get().stocks.length > 0) return;

    const res = await fetch("/out/universe.json", { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const raw = (await res.json()) as UniverseRaw;

    const list = Array.isArray(raw.list) ? raw.list.map(normalizeItem) : [];

    // 按流动性降序
    list.sort((a, b) => {
      const av = Number(a.features?.amt60_avg ?? 0);
      const bv = Number(b.features?.amt60_avg ?? 0);
      return bv - av;
    });

    set({
      asof: raw.asof ?? null,
      outJson: raw,
      stocks: list,
      symbols: list,
    });
  },

  loadMarket: async () => {
    try {
      const r = await fetch("/out/market.json", { cache: "no-cache" });
      if (r.ok) {
        const payload = (await r.json()) as MarketSnapshot;
        set({ market: payload });
        return;
      }
    } catch {}
    try {
      const r2 = await fetch("/api/market/snapshot", { cache: "no-cache" });
      if (r2.ok) {
        const payload = (await r2.json()) as MarketSnapshot;
        set({ market: payload });
      }
    } catch {}
  },

  // —— 拉取某只股票的 K 线 & 分析（有啥拿啥，失败忽略） —— //
  loadAllFor: async (symbol: string) => {
    try {
      const qs = new URLSearchParams({ symbol, tf: "1d" });
      const r = await fetch(`/api/series-c/bundle?${qs.toString()}`, { cache: "no-cache" });
      if (r.ok) {
        const payload = await r.json();
        set((s) => ({ kline: { ...s.kline, [symbol]: payload } }));
      }
    } catch {}

    try {
      const qs = new URLSearchParams({ symbol });
      const r = await fetch(`/api/analysis?${qs.toString()}`, { cache: "no-cache" });
      if (r.ok) {
        const payload = await r.json();
        set((s) => ({ analysis: { ...s.analysis, [symbol]: payload } }));
      }
    } catch {}
  },

  // —— 价位线 —— //
  getLines: (symbol) => readJSON<PriceLine[]>(keyLines(symbol), []),
  addLine: (symbol, price, title) => {
    const cur = readJSON<PriceLine[]>(keyLines(symbol), []);
    const id = `${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
    const next = [...cur, { id, price, title }];
    writeJSON(keyLines(symbol), next);
    if (get().selectedSymbol === symbol) set((s) => ({ ...s }));
  },
  removeLine: (symbol, id) => {
    const cur = readJSON<PriceLine[]>(keyLines(symbol), []);
    writeJSON(
      keyLines(symbol),
      cur.filter((x) => x.id !== id)
    );
    if (get().selectedSymbol === symbol) set((s) => ({ ...s }));
  },
  replaceLines: (symbol, lines) => {
    writeJSON(keyLines(symbol), lines);
    if (get().selectedSymbol === symbol) set((s) => ({ ...s }));
  },

  // —— 笔记 —— //
  getNotes: (symbol) => readJSON<Note[]>(keyNotes(symbol), []),
  addNote: (symbol, text) => {
    const cur = readJSON<Note[]>(keyNotes(symbol), []);
    const id = `${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
    const date = new Date().toISOString().slice(0, 10);
    const next = [{ id, date, text }, ...cur];
    writeJSON(keyNotes(symbol), next);
    if (get().selectedSymbol === symbol) set((s) => ({ ...s }));
  },
  deleteNote: (symbol, id) => {
    const cur = readJSON<Note[]>(keyNotes(symbol), []);
    writeJSON(
      keyNotes(symbol),
      cur.filter((n) => n.id !== id)
    );
    if (get().selectedSymbol === symbol) set((s) => ({ ...s }));
  },
}));
