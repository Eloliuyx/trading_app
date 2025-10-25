// frontend/src/utils/format.ts
import type { Time } from 'lightweight-charts';

export const toUTCTime = (dateStr: string): Time => {
  const [y, m, d] = dateStr.split('-').map(Number);
  const secs = Math.floor(Date.UTC(y, m - 1, d, 0, 0, 0) / 1000);
  // 轻量图的 UTCTimestamp 是带品牌的 number，需要断言为 Time
  return secs as unknown as Time;
};

export const pct = (v: number) => `${Math.round(v * 100)}%`;

export function toUTCTS(dateStr: string): number {
  const clean = dateStr.replace(/T/, " ").replace(/Z$/, "");
  const d = new Date(clean);
  return Math.floor(d.getTime() / 1000);
}
