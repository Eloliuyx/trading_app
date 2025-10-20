import { create } from "zustand";

type Candle = {
  time: number | string | Date; // 允许多种输入；组件里会统一成秒级UTC
  open: number;
  high: number;
  low: number;
  close: number;
};

type State = {
  symbol: string | null;
  candles: Candle[];
  loadSeriesCDemo: () => void;
  clear: () => void;
};

export const useDataStore = create<State>((set) => ({
  symbol: "SERIES-C",
  candles: [],
  loadSeriesCDemo: () =>
    set(() => {
      // 生成 120 根日K，毫秒时间戳（有意用毫秒，验证转换逻辑）
      const now = Date.now();
      const day = 24 * 60 * 60 * 1000;
      const candles: Candle[] = Array.from({ length: 120 }).map((_, i) => {
        const t = now - (119 - i) * day;
        const base = 100 + i * 0.6;
        const open = +(base + (Math.random() - 0.5) * 2).toFixed(2);
        const high = +(open + Math.random() * 2.5).toFixed(2);
        const low = +(open - Math.random() * 2.5).toFixed(2);
        const close = +(low + Math.random() * (high - low)).toFixed(2);
        return { time: t, open, high, low, close };
      });
      return { candles };
    }),
  clear: () => set({ candles: [] }),
}));
