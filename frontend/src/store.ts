// src/store.ts
import { create } from "zustand";

/** ========= 基础类型 ========= */

export type PriceLine = {
  id: string;
  price: number;
  title?: string;
};

export type Note = {
  id: string;
  ts: string; // ISO 字符串，SymbolDetail 用于显示时间
  text: string;
};

export type MarketSnapshot = {
  asof?: string; // universe 计算口径日期
  last_bar_date?: string; // 可选：最后一根K线日期
  rules_version?: string; // 规则版本号（由后端写入）
  status?: "OK" | "NO_DATA" | "ERROR";
};

export type StockItem = {
  symbol: string;
  name: string;
  industry?: string;
  market?: string;
  is_st?: boolean;

  // 多因子通过标记（由 export_universe.py 写入）
  pass_liquidity_v2?: boolean;      // F2: 高流动性
  pass_price_compliance?: boolean;  // F3: 合理价格区间
  pass_trend?: boolean;             // F5: 多头趋势结构
  pass_volume_confirm?: boolean;    // F4: 放量确认
  pass_industry_leader?: boolean;   // F6: 强板块龙头

  last_date?: string;               // 该票数据截止日期

  // 允许透传 features 等调试字段，不强约束
  [k: string]: any;
};

/** ========= 多因子筛选配置 =========
 * FilterPanel / ResultList / SymbolDetail 共用
 */

export type FactorKey = "F1" | "F2" | "F3" | "F4" | "F5" | "F6";

export type FilterState = {
  q: string; // 搜索关键字（代码 / 名称）
} & Partial<Record<FactorKey, boolean>>;

type FactorCfg = {
  key: FactorKey;
  label: string;
  test: (s: StockItem) => boolean;
};

export const FACTOR_CONFIG: FactorCfg[] = [
  // F1：剔除 ST 股
  {
    key: "F1",
    label: "F1: 剔除ST股",
    // is_st === true 的剔除；缺失视为正常
    test: (s) => s.is_st !== true,
  },

  // F2：高流动性
  {
    key: "F2",
    label: "F2: 高流动性",
    // 后端根据成交额 & 换手率写入 pass_liquidity_v2
    // 这里只接受明确 false 为不通过，缺失可以按需要调整
    test: (s) => s.pass_liquidity_v2 !== false,
  },

  // F3：合理价格区间
  {
    key: "F3",
    label: "F3: 合理价格区间",
    test: (s) => s.pass_price_compliance !== false,
  },

  // F4：放量确认
  {
    key: "F4",
    label: "F4: 放量确认",
    test: (s) => s.pass_volume_confirm === true,
  },

  // F5：多头趋势结构
  {
    key: "F5",
    label: "F5: 多头趋势结构",
    test: (s) => s.pass_trend === true,
  },

  // F6：强板块龙头
  {
    key: "F6",
    label: "F6: 强板块龙头",
    test: (s) => s.pass_industry_leader === true,
  },
];

/** ========= 日K数据 ========= */

export type KLineBar = {
  time: string; // yyyy-MM-dd
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  [k: string]: any;
};

/** ========= 本地存储 ========= */

const LS_KEY_NOTES = "ta_symbol_notes_v1";
const LS_KEY_PLINES = "ta_price_lines_v1";

function safeParseJSON<T>(raw: string | null): T | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

/** notes: { [symbol]: Note[] } */
function loadNotes(): Record<string, Note[]> {
  if (typeof window === "undefined") return {};
  return safeParseJSON<Record<string, Note[]>>(
    window.localStorage.getItem(LS_KEY_NOTES)
  ) || {};
}

function saveNotes(data: Record<string, Note[]>) {
  try {
    window.localStorage.setItem(LS_KEY_NOTES, JSON.stringify(data));
  } catch {
    // ignore
  }
}

/** priceLines: { [symbol]: PriceLine[] } */
function loadPriceLines(): Record<string, PriceLine[]> {
  if (typeof window === "undefined") return {};
  return safeParseJSON<Record<string, PriceLine[]>>(
    window.localStorage.getItem(LS_KEY_PLINES)
  ) || {};
}

function savePriceLines(data: Record<string, PriceLine[]>) {
  try {
    window.localStorage.setItem(LS_KEY_PLINES, JSON.stringify(data));
  } catch {
    // ignore
  }
}

/** ========= 全局状态 ========= */

type AppState = {
  /** 多因子 universe 列表 */
  stocks: StockItem[];
  /** 市场元信息（asof, status 等） */
  market: MarketSnapshot | null;

  /** 左侧筛选状态 */
  filter: FilterState;

  /** 当前选中标的 */
  selectedSymbol: string | null;

  /** 日K缓存：symbol -> bars */
  klineMap: Record<string, KLineBar[]>;

  /** 个股笔记：symbol -> Note[] */
  notesMap: Record<string, Note[]>;

  /** 水平线：symbol -> PriceLine[] */
  priceLines: Record<string, PriceLine[]>;

  /** —— 动作 —— */

  // 筛选
  setFilter: (patch: Partial<FilterState>) => void;
  resetFilter: () => void;
  toggleFlag: (key: FactorKey) => void;

  // 选中标的
  setSelectedSymbol: (symbol: string | null) => void;

  // 数据加载
  loadMarket: () => Promise<void>;
  loadKline: (symbol: string) => Promise<void>;

  // 笔记
  getNotes: (symbol: string) => Note[];
  addNote: (symbol: string, text: string) => void;
  deleteNote: (symbol: string, id: string) => void;

  // 水平线
  getLines: (symbol: string) => PriceLine[];
  addLine: (symbol: string, price: number) => void;
  clearLines: (symbol: string) => void;
};

export const useDataStore = create<AppState>((set, get) => ({
  stocks: [],
  market: null,

  filter: {
    q: "",
    F1: true, // 默认只开 F1：先排除 ST
  },

  selectedSymbol: null,
  klineMap: {},

  notesMap: loadNotes(),
  priceLines: loadPriceLines(),

  /** —— 筛选 —— */

  setFilter: (patch) =>
    set((state) => ({
      filter: {
        ...state.filter,
        ...patch,
      },
    })),

  resetFilter: () =>
    set({
      filter: { q: "", F1: true },
    }),

  toggleFlag: (key: FactorKey) =>
    set((state) => {
      const current = !!state.filter[key];
      return {
        filter: {
          ...state.filter,
          [key]: !current,
        },
      };
    }),

  /** —— 当前选中 —— */

  setSelectedSymbol: (symbol) => set({ selectedSymbol: symbol }),

  /** —— 加载 universe / market —— */

  loadMarket: async () => {
    if (typeof window === "undefined") return;

    const tryUrls = ["/out/universe.json", "/universe.json"];
    let data: any = null;

    for (const url of tryUrls) {
      try {
        const res = await fetch(url, { cache: "no-cache" });
        if (!res.ok) continue;
        data = await res.json();
        break;
      } catch {
        // try next
      }
    }

    if (!data) {
      set({
        stocks: [],
        market: { status: "ERROR" },
      });
      return;
    }

    let stocks: StockItem[] = [];
    const market: MarketSnapshot = { status: "OK" };

    // 结构 1: 直接是数组
    if (Array.isArray(data)) {
      stocks = data as StockItem[];
    }
    // 结构 2: { asof, last_bar_date, rules_version, list: [...] }
    else if (Array.isArray(data.list)) {
      stocks = data.list as StockItem[];
      if (data.asof) market.asof = data.asof;
      if (data.last_bar_date) market.last_bar_date = data.last_bar_date;
      if (data.rules_version) market.rules_version = data.rules_version;
    }
    // 兜底：尝试从 data.stocks / data.items 等读取
    else {
      if (Array.isArray(data.stocks)) {
        stocks = data.stocks as StockItem[];
      }
      market.asof = data.asof || data.date || market.asof;
      market.last_bar_date = data.last_bar_date || market.last_bar_date;
      market.rules_version = data.rules_version || market.rules_version;
    }

    if (!stocks.length) {
      market.status = "NO_DATA";
    }

    set({ stocks, market });
  },

  /** —— 加载单个 symbol 的日K（CSV） —— */

  loadKline: async (symbol: string) => {
    if (!symbol) return;

    const { klineMap } = get();
    if (klineMap[symbol]?.length) return; // 已有缓存

    if (typeof window === "undefined") return;

    const tryUrls = [`/data/${symbol}.csv`, `/out/${symbol}.csv`];

    for (const url of tryUrls) {
      try {
        const res = await fetch(url, { cache: "no-cache" });
        if (!res.ok) continue;

        const txt = await res.text();
        const lines = txt.trim().split(/\r?\n/);
        if (lines.length <= 1) continue;

        const header = lines[0].split(",");
        const idx = (name: string) => header.indexOf(name);

        const iDate = idx("Date");
        const iOpen = idx("Open");
        const iHigh = idx("High");
        const iLow = idx("Low");
        const iClose = idx("Close");
        const iVol = idx("Volume");

        const bars: KLineBar[] = lines
          .slice(1)
          .map((ln) => ln.split(","))
          .filter((a) => a.length >= 5)
          .map((a) => ({
            time: a[iDate],
            open: Number(a[iOpen]),
            high: Number(a[iHigh]),
            low: Number(a[iLow]),
            close: Number(a[iClose]),
            volume: iVol >= 0 ? Number(a[iVol]) || undefined : undefined,
          }));

        set((state) => ({
          klineMap: {
            ...state.klineMap,
            [symbol]: bars,
          },
        }));
        return;
      } catch {
        // try next url
      }
    }
  },

  /** —— 笔记 —— */

  getNotes: (symbol: string) => {
    if (!symbol) return [];
    const { notesMap } = get();
    return notesMap[symbol] || [];
  },

  addNote: (symbol: string, text: string) => {
    if (!symbol || !text.trim()) return;

    const trimmed = text.trim();

    set((state) => {
      const prev = state.notesMap[symbol] || [];
      const nextNote: Note = {
        id: `n_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        ts: new Date().toISOString(),
        text: trimmed,
      };

      const nextMap = {
        ...state.notesMap,
        [symbol]: [nextNote, ...prev],
      };

      saveNotes(nextMap);
      return { ...state, notesMap: nextMap };
    });
  },

  deleteNote: (symbol: string, id: string) => {
    if (!symbol || !id) return;

    set((state) => {
      const prev = state.notesMap[symbol];
      if (!prev) return state;

      const nextList = prev.filter((n) => n.id !== id);
      const nextMap = { ...state.notesMap, [symbol]: nextList };

      saveNotes(nextMap);
      return { ...state, notesMap: nextMap };
    });
  },

  /** —— 水平线 —— */

  getLines: (symbol: string) => {
    if (!symbol) return [];
    const { priceLines } = get();
    return priceLines[symbol] || [];
  },

  addLine: (symbol: string, price: number) => {
    if (!symbol || !Number.isFinite(price)) return;

    const rounded = Number(price.toFixed(2));

    set((state) => {
      const prev = state.priceLines[symbol] || [];

      // 同一价格只画一次
      if (prev.some((pl) => Number(pl.price.toFixed(2)) === rounded)) {
        return state;
      }

      const nextLine: PriceLine = {
        id: `pl_${symbol}_${rounded}`,
        price: rounded,
        title: rounded.toFixed(2),
      };

      const nextAll = {
        ...state.priceLines,
        [symbol]: [...prev, nextLine],
      };

      savePriceLines(nextAll);
      return { ...state, priceLines: nextAll };
    });
  },

  clearLines: (symbol: string) => {
    if (!symbol) return;

    set((state) => {
      if (!state.priceLines[symbol]) return state;

      const nextAll = { ...state.priceLines };
      delete nextAll[symbol];

      savePriceLines(nextAll);
      return { ...state, priceLines: nextAll };
    });
  },
}));
