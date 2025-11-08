// src/components/KLineChart.tsx
import React, { useEffect, useRef } from "react";
import {
  createChart,
  LineStyle,
  IChartApi,
  ISeriesApi,
  MouseEventParams,
  Time,
} from "lightweight-charts";
import {
  useDataStore,
  type PriceLine,
  type KLineBar,
} from "../store";

/**
 * 日K图：
 * - 根据 selectedSymbol 展示 K 线
 * - 点击图表：在点击 Y 坐标对应的价格处生成水平线（存入全局 store）
 * - 为适配不同版本 lightweight-charts，我们在点击回调里使用 `as any`
 */

const containerStyle: React.CSSProperties = {
  width: "100%",
  height: "100%",
};

const KLineChart: React.FC = () => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const lineMapRef = useRef<Map<string, any>>(new Map());
  const selectedSymbolRef = useRef<string | null>(null);

  const selectedSymbol = useDataStore((s) => s.selectedSymbol);
  const klineMap = useDataStore((s) => s.klineMap);
  const loadKline = useDataStore((s) => s.loadKline);
  const getLines = useDataStore((s) => s.getLines);
  const addLine = useDataStore((s) => s.addLine);

  /** 初始化图表和点击事件 */
  useEffect(() => {
    if (!containerRef.current || chartRef.current) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: "#ffffff" },
        textColor: "#6b7280",
      },
      rightPriceScale: { borderColor: "#e5e7eb" },
      timeScale: { borderColor: "#e5e7eb", rightOffset: 2 },
      grid: {
        vertLines: { color: "#f3f4f6" },
        horzLines: { color: "#f3f4f6" },
      },
      crosshair: { mode: 1 },
    });

    const series = chart.addCandlestickSeries({
      upColor: "#ef4444",
      downColor: "#22c55e",
      borderUpColor: "#ef4444",
      borderDownColor: "#22c55e",
      wickUpColor: "#ef4444",
      wickDownColor: "#22c55e",
    });

    chartRef.current = chart;
    seriesRef.current = series;

    const handleResize = () => {
      if (!containerRef.current || !chartRef.current) return;
      const { clientWidth, clientHeight } = containerRef.current;
      chartRef.current.applyOptions({
        width: clientWidth,
        height: clientHeight,
      });
    };
    handleResize();
    window.addEventListener("resize", handleResize);

    // 点击生成水平线：用像素 -> 价格，全部用 any 规避类型差异
    const handleClick = (param: MouseEventParams<Time>) => {
      const symbol = selectedSymbolRef.current;
      if (!symbol || !seriesRef.current) return;

      const anyParam = param as any;
      const point = anyParam?.point;
      if (!point) return;

      const priceScale: any = (seriesRef.current as any).priceScale?.();
      if (!priceScale || typeof priceScale.coordinateToPrice !== "function") {
        // 某些极端版本没有该方法，就直接跳过，保证不报错
        return;
      }

      const price = priceScale.coordinateToPrice(point.y);
      if (price == null || !Number.isFinite(price)) return;

      const line: PriceLine = {
        id: `pl_${symbol}_${price.toFixed(2)}_${Date.now()}`,
        price,
        title: price.toFixed(2),
      };
      addLine(symbol, line);
    };

    chart.subscribeClick(handleClick);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.unsubscribeClick(handleClick);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      lineMapRef.current.clear();
    };
  }, [addLine]);

  /** 跟踪当前选中 symbol，懒加载 K 线 */
  useEffect(() => {
    selectedSymbolRef.current = selectedSymbol || null;
    if (selectedSymbol) {
      loadKline(selectedSymbol);
    }
  }, [selectedSymbol, loadKline]);

  /** 更新图表数据 & 水平线 */
  useEffect(() => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    if (!chart || !series) return;

    if (!selectedSymbol) {
      series.setData([]);
      lineMapRef.current.forEach((pl) => {
        try {
          series.removePriceLine(pl);
        } catch {}
      });
      lineMapRef.current.clear();
      return;
    }

    const bars: KLineBar[] = klineMap[selectedSymbol] || [];
    if (!bars.length) {
      series.setData([]);
      return;
    }

    series.setData(bars as any);

    const n = bars.length;
    if (n > 80) {
      const from = bars[n - 80].time as any;
      const to = bars[n - 1].time as any;
      chart.timeScale().setVisibleRange({ from, to });
    } else {
      chart.timeScale().fitContent();
    }

    // 清理旧线
    lineMapRef.current.forEach((pl) => {
      try {
        series.removePriceLine(pl);
      } catch {}
    });
    lineMapRef.current.clear();

    // 绘制当前 symbol 的线
    const lines = getLines(selectedSymbol) || [];
    lines.forEach((l) => {
      const pl = series.createPriceLine({
        price: l.price,
        title: l.title,
        color: "#6b7280",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
      });
      lineMapRef.current.set(l.id, pl);
    });
  }, [selectedSymbol, klineMap, getLines]);

  return <div ref={containerRef} style={containerStyle} />;
};

export default KLineChart;
