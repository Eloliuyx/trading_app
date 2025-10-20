import React, { useEffect, useLayoutEffect, useRef } from "react";
import {
  createChart,
  ColorType,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type UTCTimestamp,
} from "lightweight-charts";
import { useDataStore } from "../store";

export default function KLineChart() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  const candles = useDataStore((s) => s.candles);

  // 1) 创建图表（一次）
  useLayoutEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: { background: { type: ColorType.Solid, color: "#fff" }, textColor: "#222" },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
      grid: { vertLines: { color: "#efefef" }, horzLines: { color: "#efefef" } },
      autoSize: true, // 关键：让图表跟随容器大小
    });
    const series = chart.addCandlestickSeries();
    chart.timeScale().fitContent();

    chartRef.current = chart;
    seriesRef.current = series;

    // 自适应容器尺寸
    const ro = new ResizeObserver(() => chart.applyOptions({ autoSize: true }));
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, []);

  // 2) 数据变化时更新
  useEffect(() => {
    if (!seriesRef.current) return;
    if (!candles || candles.length === 0) {
      seriesRef.current.setData([]);
      return;
    }

    // 将任何“毫秒时间戳/Date/字符串”统一成 秒级 UTCTimestamp
    const toUtcSec = (t: any): UTCTimestamp => {
      if (typeof t === "number") {
        // 既兼容毫秒也兼容秒：>1e12 基本就是毫秒
        const sec = t > 1e12 ? Math.floor(t / 1000) : Math.floor(t);
        return sec as UTCTimestamp;
      }
      if (t instanceof Date) return Math.floor(t.getTime() / 1000) as UTCTimestamp;
      // ISO 字符串
      const d = new Date(t);
      return Math.floor(d.getTime() / 1000) as UTCTimestamp;
    };

    const data: CandlestickData[] = candles.map((c: any) => ({
      time: toUtcSec(c.time),
      open: Number(c.open),
      high: Number(c.high),
      low: Number(c.low),
      close: Number(c.close),
    }));

    seriesRef.current.setData(data);
    chartRef.current?.timeScale().fitContent();
  }, [candles]);

  // 关键：容器必须有非零高度
  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height: 420, border: "1px solid #c3c6d1", borderRadius: 6 }}
    />
  );
}
