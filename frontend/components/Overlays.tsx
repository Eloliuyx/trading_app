import React, { useEffect, useMemo, useRef } from 'react';
import { chartCtx } from './KLineChart';
import { useDataStore } from '../store';
import type { Candle } from '../types';
import { ColorType } from 'lightweight-charts';

const Overlays: React.FC = () => {
  const { candles, outJson } = useDataStore();
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // --- 建立笔/段为 line series ---
  useEffect(() => {
    const { chart, candleSeries } = chartCtx;
    if (!chart || !candleSeries || !outJson) return;

    // 清理旧的线
    const existing = (chart as any).__overlaySeries as any[] | undefined;
    existing?.forEach((s) => chart.removeSeries(s));

    const overlaySeries: any[] = [];

    const addLine = (color: string) => {
      const s = chart.addLineSeries({
        color, lineWidth: 2, lastValueVisible: false, priceLineVisible: false,
      });
      overlaySeries.push(s);
      return s;
    };

    // 笔：红=up, 蓝=down
    const biUp = addLine('#ef4444');
    const biDn = addLine('#3b82f6');

    const toPoint = (idx: number) => {
      const c = candles[idx];
      return { time: c.time as any, value: c.close }; // 端点以收盘近似（或可用 High/Low 端点）
    };

    const upData: any[] = [];
    const dnData: any[] = [];
    outJson.bis.forEach(b => {
      const a = toPoint(b.start), z = toPoint(b.end);
      if (b.dir === 'up') { upData.push(a, z, { time: z.time, value: NaN }); }
      else { dnData.push(a, z, { time: z.time, value: NaN }); }
    });
    biUp.setData(upData);
    biDn.setData(dnData);

    // 线段：更粗
    const segUp = chart.addLineSeries({ color: '#b91c1c', lineWidth: 3, lastValueVisible: false, priceLineVisible: false });
    const segDn = chart.addLineSeries({ color: '#1d4ed8', lineWidth: 3, lastValueVisible: false, priceLineVisible: false });
    overlaySeries.push(segUp, segDn);

    const segUpData: any[] = [];
    const segDnData: any[] = [];
    outJson.segments.forEach(sg => {
      const a = toPoint(sg.start), z = toPoint(sg.end);
      if (sg.dir === 'up') { segUpData.push(a, z, { time: z.time, value: NaN }); }
      else { segDnData.push(a, z, { time: z.time, value: NaN }); }
    });
    segUp.setData(segUpData);
    segDn.setData(segDnData);

    // 分型：markers
    const markers = outJson.fractals.map(fr => {
      const c = candles[fr.idx];
      return {
        time: c.time as any,
        position: fr.type === 'top' ? 'aboveBar' : 'belowBar',
        shape: fr.type === 'top' ? 'arrowDown' : 'arrowUp',
        color: fr.type === 'top' ? '#ef4444' : '#10b981',
        size: 2,
      } as const;
    });
    candleSeries.setMarkers(markers);

    // 存引用便于下次清理
    (chart as any).__overlaySeries = overlaySeries;

    return () => {
      overlaySeries.forEach(s => chart.removeSeries(s));
      candleSeries.setMarkers([]);
      (chart as any).__overlaySeries = [];
    };
  }, [outJson, candles]);

  // --- 中枢：Canvas 叠加 ---
  useEffect(() => {
    const { chart, candleSeries } = chartCtx;
    const cvs = canvasRef.current!;
    if (!chart || !candleSeries || !outJson) return;

    const parent = (chart as any).chartElement ?? (cvs.parentElement as HTMLElement);
    // 让画布覆盖图表内容
    const syncSize = () => {
      const rect = parent.getBoundingClientRect();
      cvs.width = Math.floor(rect.width * window.devicePixelRatio);
      cvs.height = Math.floor(rect.height * window.devicePixelRatio);
      cvs.style.width = `${rect.width}px`;
      cvs.style.height = `${rect.height}px`;
    };
    syncSize();

    const ro = new ResizeObserver(syncSize);
    ro.observe(parent);

    const draw = () => {
      const ctx = cvs.getContext('2d')!;
      ctx.clearRect(0, 0, cvs.width, cvs.height);

      const ts = chart.timeScale();
      outJson.zhongshus.forEach(zs => {
        const t0 = candles[zs.start]?.time;
        const t1 = candles[zs.end]?.time;
        if (!t0 || !t1) return;

        const x0 = ts.timeToCoordinate(t0 as any);
        const x1 = ts.timeToCoordinate(t1 as any);
        const yHi = candleSeries.priceToCoordinate(zs.price_range[1]);
        const yLo = candleSeries.priceToCoordinate(zs.price_range[0]);
        if (x0 == null || x1 == null || yHi == null || yLo == null) return;

        const dpr = window.devicePixelRatio || 1;
        const left = Math.min(x0, x1) * dpr;
        const right = Math.max(x0, x1) * dpr;
        const top = Math.min(yHi, yLo) * dpr;
        const bottom = Math.max(yHi, yLo) * dpr;
        const w = Math.max(1, right - left);
        const h = Math.max(1, bottom - top);

        // 半透明灰框
        ctx.fillStyle = 'rgba(107,114,128,0.15)';
        ctx.fillRect(left, top, w, h);
        ctx.strokeStyle = 'rgba(107,114,128,0.6)';
        ctx.lineWidth = 1 * dpr;
        ctx.strokeRect(left, top, w, h);
      });
    };

    const sub1 = chart.timeScale().subscribeVisibleTimeRangeChange(draw);
    const sub2 = chart.subscribeCrosshairMove(draw);
    draw();

    return () => {
      ro.disconnect();
      chart.timeScale().unsubscribeVisibleTimeRangeChange(draw);
      chart.unsubscribeCrosshairMove(draw);
      const ctx = cvs.getContext('2d')!;
      ctx.clearRect(0, 0, cvs.width, cvs.height);
    };
  }, [outJson, candles]);

  return <canvas ref={canvasRef} style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }} />;
};

export default Overlays;
