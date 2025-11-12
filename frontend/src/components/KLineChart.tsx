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

const wrapperStyle: React.CSSProperties = {
  position: "relative",
  width: "100%",
  height: "100%",
};

const chartContainerStyle: React.CSSProperties = {
  position: "absolute",
  inset: 0,
};

const toolbarStyle: React.CSSProperties = {
  position: "absolute",
  top: 6,
  right: 6,
  display: "flex",
  gap: 6,
  zIndex: 2,
};

const toolbarBtn: React.CSSProperties = {
  padding: "2px 8px",
  fontSize: 10,
  borderRadius: 999,
  border: "1px solid #e5e7eb",
  background: "rgba(255,255,255,0.96)",
  color: "#4b5563",
  cursor: "pointer",
};

const KLineChart: React.FC = () => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const lineMapRef = useRef<Map<string, any>>(new Map());
  const selectedSymbolRef = useRef<string | null>(null);

  const selectedSymbol = useDataStore((s) => s.selectedSymbol);
  const klineMap = useDataStore((s) => s.klineMap || {});
  const priceLines = useDataStore((s) => s.priceLines || {});
  const loadKline = useDataStore((s) => s.loadKline);
  const addLine = useDataStore((s) => s.addLine);
  const clearLines = useDataStore((s) => s.clearLines);

  // 从点击事件估算价格
  const getPriceFromClick = (
    param: MouseEventParams<Time>
  ): number | null => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    const anyParam = param as any;
    if (!chart || !series) return null;
    const point = anyParam?.point;
    if (!point) return null;

    // 优先从 seriesData 读取收盘价
    if (anyParam.seriesData) {
      const d =
        anyParam.seriesData.get?.(series as any) ??
        anyParam.seriesData[series as any];
      if (d && typeof d.close === "number") return d.close;
    }

    // 回退：用坐标换算价格
    const psFromSeries: any = (series as any).priceScale?.();
    if (psFromSeries?.coordinateToPrice) {
      const p = psFromSeries.coordinateToPrice(point.y);
      if (p != null && Number.isFinite(p)) return p;
    }

    const psFromChart: any = (chart as any).priceScale?.("right");
    if (psFromChart?.coordinateToPrice) {
      const p = psFromChart.coordinateToPrice(point.y);
      if (p != null && Number.isFinite(p)) return p;
    }

    return null;
  };

  // 初始化图表（只执行一次）
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

    const applySize = () => {
      if (!containerRef.current || !chartRef.current) return;
      const { clientWidth, clientHeight } = containerRef.current;
      if (clientWidth > 0 && clientHeight > 0) {
        chartRef.current.applyOptions({
          width: clientWidth,
          height: clientHeight,
        });
      }
    };

    applySize();
    window.addEventListener("resize", applySize);

    let ro: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver(() => applySize());
      ro.observe(containerRef.current);
    }

    const handleClick = (param: MouseEventParams<Time>) => {
      const symbol = selectedSymbolRef.current;
      if (!symbol) return;
      const price = getPriceFromClick(param);
      if (price == null || !Number.isFinite(price)) return;
      addLine(symbol, Number(price.toFixed(2)));
    };

    chart.subscribeClick(handleClick);

    return () => {
      window.removeEventListener("resize", applySize);
      chart.unsubscribeClick(handleClick);
      if (ro) ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      lineMapRef.current.clear();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 选中标的变化时，请求加载其日K
  useEffect(() => {
    selectedSymbolRef.current = selectedSymbol || null;
    if (selectedSymbol) {
      loadKline(selectedSymbol);
    }
  }, [selectedSymbol, loadKline]);

  // symbol / k线数据 / 水平线变化时，重绘
  useEffect(() => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    if (!chart || !series) return;

    // 清除旧的水平线
    lineMapRef.current.forEach((pl) => {
      try {
        series.removePriceLine(pl);
      } catch {
        // ignore
      }
    });
    lineMapRef.current.clear();

    if (!selectedSymbol) {
      series.setData([]);
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
      const from = bars[n - 80].time as Time;
      const to = bars[n - 1].time as Time;
      chart.timeScale().setVisibleRange({ from, to });
    } else {
      chart.timeScale().fitContent();
    }

    const lines: PriceLine[] = priceLines[selectedSymbol] || [];
    lines.forEach((l) => {
      const id = l.id || `pl_${selectedSymbol}_${l.price.toFixed(2)}`;
      const pl = series.createPriceLine({
        price: l.price,
        color: "#1d4ed8",
        lineWidth: 2,
        lineStyle: LineStyle.Dashed,
      });
      lineMapRef.current.set(id, pl);
    });
  }, [selectedSymbol, klineMap, priceLines]);

  const handleClear = () => {
    if (!selectedSymbol) return;
    clearLines(selectedSymbol);
  };

  return (
    <div style={wrapperStyle}>
      <div ref={containerRef} style={chartContainerStyle} />
      {selectedSymbol && (
        <div style={toolbarStyle}>
          <button style={toolbarBtn} onClick={handleClear}>
            清除本标的水平线
          </button>
        </div>
      )}
    </div>
  );
};

export default KLineChart;
