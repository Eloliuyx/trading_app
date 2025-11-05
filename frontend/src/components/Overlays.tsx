import React, { useEffect } from 'react';
import type { IChartApi, ISeriesApi, Time } from 'lightweight-charts';

/** 统一的 K 线条形类型（兼容你自定义的 Candle[] 和 LWC 的 CandlestickData<Time>[]） */
type Bar = {
  time: Time | number; // 允许 number 秒级时间戳
  open: number;
  high: number;
  low: number;
  close: number;
};

export type Segment = { start: number; end: number; dir: 'up' | 'down' };
export type Zhongshu = { start: number; end: number; price_range: [number, number] };

/** 颜色常量 */
const COLOR_UP = '#e53935';
const COLOR_DOWN = '#1e88e5';
const ZS_FILL = 'rgba(128,128,128,0.18)';
const ZS_STROKE = 'rgba(90,90,90,0.5)';

type Props = {
  chart: IChartApi;
  candle: ISeriesApi<'Candlestick'>;
  containerEl: HTMLDivElement;
  data: Bar[];                   // ✅ 放宽为 Bar[]
  segments?: Segment[];
  zhongshus?: Zhongshu[];
  /** 可选：过滤太短的段/中枢，避免噪点（按原始K索引跨度） */
  minSpanBars?: number;          // 默认 2
};

const Overlays: React.FC<Props> = ({
  chart,
  candle,
  containerEl,
  data,
  segments = [],
  zhongshus = [],
  minSpanBars = 2,
}) => {
  // —— 无效位高亮：监听全局事件 ——
  const priceLineRef = React.useRef<ReturnType<typeof candle.createPriceLine> | null>(null);
  const currentPriceRef = React.useRef<number | null>(null);

  React.useEffect(() => {
    const handler = (e: any) => {
      const price = e?.detail ?? null;
      currentPriceRef.current = (typeof price === 'number') ? price : null;
      if (!candle) return;
      // 清除旧线
      if (priceLineRef.current) {
        candle.removePriceLine(priceLineRef.current);
        priceLineRef.current = null;
      }
      if (typeof price === 'number') {
        priceLineRef.current = candle.createPriceLine({
          price,
          color: '#ef4444',
          lineWidth: 2,
          lineStyle: 2, // dashed
          axisLabelVisible: true,
          title: '无效位'
        });
      }
    };
    window.addEventListener('hlprice', handler as any);
    return () => window.removeEventListener('hlprice', handler as any);
  }, [candle]);

  // 将 data.time 提取为 Time[]，供 timeToCoordinate 使用
  const times: Time[] = data.map(d => (d.time as Time));

  useEffect(() => {
    if (!chart || !candle || !containerEl || times.length === 0) return;

    // —— 叠加层 Canvas（固定挂在容器内）——
    let overlay = containerEl.querySelector<HTMLCanvasElement>(':scope > canvas.__overlay__');
    if (!overlay) {
      overlay = document.createElement('canvas');
      overlay.className = '__overlay__';
      overlay.style.position = 'absolute';
      overlay.style.left = '0';
      overlay.style.top = '0';
      overlay.style.pointerEvents = 'none';
      overlay.style.zIndex = '2';
      if (!containerEl.style.position) containerEl.style.position = 'relative';
      containerEl.appendChild(overlay);
    }

    const dpr = window.devicePixelRatio || 1;

    const ixToX = (i: number) => {
      const t = times[i];
      const x = chart.timeScale().timeToCoordinate(t);
      return x ?? -9999;
    };
    const pToY = (p: number) => candle.priceToCoordinate(p) ?? -9999;
    const priceAt = (i: number) => {
      const bar = data[i];
      return bar?.close ?? bar?.open ?? 0;
    };

    const redraw = () => {
      const box = containerEl.getBoundingClientRect();
      overlay!.width = Math.floor(box.width * dpr);
      overlay!.height = Math.floor(box.height * dpr);
      overlay!.style.width = `${box.width}px`;
      overlay!.style.height = `${box.height}px`;

      const ctx = overlay!.getContext('2d')!;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, box.width, box.height);

      // —— 线段 —— //
      ctx.lineWidth = 2;
      segments.forEach(seg => {
        if (seg.end - seg.start < Math.max(1, minSpanBars)) return;
        const s = Math.max(0, Math.min(data.length - 1, seg.start));
        const e = Math.max(0, Math.min(data.length - 1, seg.end));
        const x1 = ixToX(s); const x2 = ixToX(e);
        if (x1 < 0 || x2 < 0) return;
        const y1 = pToY(priceAt(s)); const y2 = pToY(priceAt(e));
        if (y1 < 0 || y2 < 0) return;
        ctx.strokeStyle = seg.dir === 'up' ? COLOR_UP : COLOR_DOWN;
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
      });

      // —— 中枢 —— //
      zhongshus.forEach(zs => {
        if (zs.end - zs.start < Math.max(1, minSpanBars)) return;
        const s = Math.max(0, Math.min(data.length - 1, zs.start));
        const e = Math.max(0, Math.min(data.length - 1, zs.end));
        const x1 = ixToX(s); const x2 = ixToX(e);
        const [L, U] = zs.price_range;
        const yU = pToY(U); const yL = pToY(L);
        if (x1 < 0 || x2 < 0 || yU < 0 || yL < 0) return;
        const x = Math.min(x1, x2);
        const w = Math.max(1, Math.abs(x2 - x1));
        const y = Math.min(yU, yL);
        const h = Math.max(1, Math.abs(yL - yU));
        ctx.fillStyle = ZS_FILL;
        ctx.fillRect(x, y, w, h);
        ctx.strokeStyle = ZS_STROKE;
        ctx.strokeRect(x, y, w, h);
      });
    };

    // 初次与可视窗口变化时重绘
    redraw();
    const ts = chart.timeScale();
    const onRange = () => redraw();
    ts.subscribeVisibleTimeRangeChange(onRange);

    const ro = new ResizeObserver(() => redraw());
    ro.observe(containerEl);

    return () => {
      ts.unsubscribeVisibleTimeRangeChange(onRange);
      ro.disconnect();
    };
  }, [chart, candle, containerEl, data, segments, zhongshus, times, minSpanBars]);

  return null;
};

export default Overlays;
