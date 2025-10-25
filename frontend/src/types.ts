// frontend/src/types.ts
import type { Time } from 'lightweight-charts';

export type Fractal = { idx: number; type: 'top' | 'bottom' };
export type Bi = { start: number; end: number; dir: 'up' | 'down' };
export type Segment = { start: number; end: number; dir: 'up' | 'down' };
export type Zhongshu = {
  start: number; end: number;
  price_range: [number, number];
  move?: 'up' | 'down' | 'flat';
  legs?: [number, number][];
};
export type ShiResult = {
  class: '中枢上破进行中' | '中枢下破进行中' | '中枢震荡未破' |
         '上行背驰待确证' | '下行背驰待确证' |
         '上行背驰确立' | '下行背驰确立';
  confidence: number;
  momentum?: number;
  risk?: number;
  evidence?: string[];
};
export type Recommendation = {
  at_close_of: string;
  action: '买' | '观察买点' | '持有' | '止盈' | '回避';
  buy_strength: number;
  rationale: string;
  invalidate_if: string;
  components?: Record<string, number>;
};
export type OutputJson = {
  meta: { symbol: string; asof: string; last_bar_date: string; tz: string; };
  rules_version: string;
  fractals: Fractal[];
  bis: Bi[];
  segments: Segment[];
  zhongshus: Zhongshu[];
  shi: ShiResult;
  recommendation_for_today: Recommendation;
};

export type Candle = {
  time: Time;                 // ✅ 用 LWC 的 Time（品牌类型）
  open: number; high: number; low: number; close: number;
};

export type MarketIndex = {
  asof: string;
  rules_version: string;
  mode: 'precision' | 'recall';
  buckets: Record<'买'|'观察买点'|'持有'|'止盈'|'回避', string[]>;
  buy_strength: Record<string, number>;
};

export type SymbolMeta = {
  symbol: string;
  name?: string;
  market?: string;   // SH/SZ/...
  industry?: string;
  area?: string;
};

export type Zone = { upper: number; lower: number; tStart: number; tEnd: number };

export type LinePoint = { time: number; value: number };
export type MALine = { name: string; values: LinePoint[] };
export type SeriesCBundle = {
  symbol: string;
  timeframe: string;
  candles: Candle[];          // ✅ 跟随改为 Time
  ma: MALine[];
  segments: Segment[];
  zones: Zone[];
};
