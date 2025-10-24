import React, { useEffect } from 'react';
import type {
  IChartApi,
  ISeriesApi,
  Time,
  SeriesMarker,
  CandlestickData,
} from 'lightweight-charts';

export type Fractal = { idx: number; type: 'top' | 'bottom' };
export type Segment = { start: number; end: number; dir: 'up' | 'down' };
export type Zhongshu = { start: number; end: number; price_range: [number, number] };

/** 颜色常量（文件内定义，避免未导出报错） */
const TOP_COLOR = '#e53935';    // 顶分型/下跌色
const BOTTOM_COLOR = '#1e88e5'; // 底分型/上升色

type Props = {
  chart: IChartApi;
  candle: ISeriesApi<'Candlestick'>;
  containerEl: HTMLDivElement;              // 从 KLineChart onReady 传入
  data: CandlestickData[];                  // 为了取端点价格
  fractals?: Fractal[];
  segments?: Segment[];
  zhongshus?: Zhongshu[];
};

const Overlays: React.FC<Props> = ({
  chart,
  candle,
  containerEl,
  data,
  fractals = [],
  segments = [],
  zhongshus = [],
}) => {
  const times: Time[] = data.map(d => d.time);

  // 1) 分型 markers（严格用与该 bar 完全一致的 time）
  useEffect(() => {
    if (!candle || !times.length) return;
    const markers: SeriesMarker<Time>[] = fractals
      .filter(f => f.idx >= 0 && f.idx < times.length)
      .map(f => ({
        time: times[f.idx],
        position: f.type === 'top' ? 'aboveBar' : 'belowBar',
        shape: f.type === 'top' ? 'arrowDown' : 'arrowUp',
        text: f.type === 'top' ? '顶分型' : '底分型',
        size: 1,
        color: f.type === 'top' ? TOP_COLOR : BOTTOM_COLOR,
      }));
    candle.setMarkers(markers);
    return () => {
      // 组件卸载或依赖变化时清空，避免残留
      candle.setMarkers([]);
    };
  }, [candle, times, fractals]);

  // 2) 线段/中枢：用自建 Canvas 叠加层（坐标来自官方 API，避免位移）
  useEffect(() => {
    if (!chart || !candle || !containerEl || !times.length) return;

    // 叠加层 Canvas（附着在容器内，避免访问内部私有 DOM）
    let overlay = containerEl.querySelector<HTMLCanvasElement>(':scope > canvas.__overlay__');
    if (!overlay) {
      overlay = document.createElement('canvas');
      overlay.className = '__overlay__';
      overlay.style.position = 'absolute';
      overlay.style.left = '0';
      overlay.style.top = '0';
      overlay.style.pointerEvents = 'none';
      overlay.style.zIndex = '2'; // 确保在主图之上
      if (!containerEl.style.position) {
        containerEl.style.position = 'relative';
      }
      containerEl.appendChild(overlay);
    }

    const dpr = window.devicePixelRatio || 1;

    // 从 idx 获取屏幕坐标
    const ixToX = (i: number) => {
      const t = times[i];
      const x = chart.timeScale().timeToCoordinate(t as Time);
      return x ?? -9999;
    };
    // 从价格获取屏幕坐标（使用 series.priceToCoordinate）
    const pToY = (p: number) => {
      const y = candle.priceToCoordinate(p);
      return y ?? -9999;
    };
    const priceAt = (i: number) => {
      // 用收盘价；若要画“笔端价位”，可改为 high/low 或后端提供的端点价
      const bar = data[i] as CandlestickData;
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

      // —— 画线段（按端点 idx 连接端点价）——
      ctx.lineWidth = 2;
      segments.forEach(seg => {
        const s = Math.max(0, Math.min(data.length - 1, seg.start));
        const e = Math.max(0, Math.min(data.length - 1, seg.end));
        const x1 = ixToX(s);
        const x2 = ixToX(e);
        if (x1 < 0 || x2 < 0) return;
        const y1 = pToY(priceAt(s));
        const y2 = pToY(priceAt(e));
        if (y1 < 0 || y2 < 0) return;
        ctx.strokeStyle = seg.dir === 'up' ? TOP_COLOR : BOTTOM_COLOR;
        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      });

      // —— 画中枢（半透明矩形）——
      zhongshus.forEach(zs => {
        const s = Math.max(0, Math.min(data.length - 1, zs.start));
        const e = Math.max(0, Math.min(data.length - 1, zs.end));
        const x1 = ixToX(s);
        const x2 = ixToX(e);
        const [L, U] = zs.price_range;
        const yU = pToY(U);
        const yL = pToY(L);
        if (x1 < 0 || x2 < 0 || yU < 0 || yL < 0) return;
        const x = Math.min(x1, x2);
        const w = Math.max(1, Math.abs(x2 - x1));
        const y = Math.min(yU, yL);
        const h = Math.max(1, Math.abs(yL - yU));
        ctx.fillStyle = 'rgba(128,128,128,0.18)';
        ctx.fillRect(x, y, w, h);
        ctx.strokeStyle = 'rgba(90,90,90,0.5)';
        ctx.strokeRect(x, y, w, h);
      });
    };

    // 初次 + 视窗变化时重绘
    redraw();
    const ts = chart.timeScale();
    const onRange = () => redraw();
    ts.subscribeVisibleTimeRangeChange(onRange);

    const ro = new ResizeObserver(() => redraw());
    ro.observe(containerEl);

    return () => {
      ts.unsubscribeVisibleTimeRangeChange(onRange);
      ro.disconnect();
      // overlay 保留以便复用
    };
  }, [chart, candle, containerEl, data, segments, zhongshus, times]);
  // 说明：
  // - 依赖中包含 data/segments/zhongshus，使其更新时触发重绘
  // - 包含 times（由 data 推导）以确保坐标映射同步

  return null;
};

export default Overlays;
