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

  /** 从点击事件中尽力推导价格（兼容不同版本 lightweight-charts） */
  const getPriceFromClick = (param: MouseEventParams<Time>): number | null => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    const anyParam = param as any;
    if (!chart || !series) return null;

    const point = anyParam?.point;
    if (!point) return null;

    // 方案1：seriesData.close（有的话最稳）
    if (anyParam.seriesData) {
      const d =
        anyParam.seriesData.get?.(series as any) ??
        anyParam.seriesData[series as any];
      if (d && typeof d.close === "number") {
        return d.close;
      }
    }

    // 方案2：series.priceScale().coordinateToPrice
    const psFromSeries: any = (series as any).priceScale?.();
    if (psFromSeries?.coordinateToPrice) {
      const p = psFromSeries.coordinateToPrice(point.y);
      if (p != null && Number.isFinite(p)) return p;
    }

    // 方案3：chart.priceScale('right').coordinateToPrice
    const psFromChart: any = (chart as any).priceScale?.("right");
    if (psFromChart?.coordinateToPrice) {
      const p = psFromChart.coordinateToPrice(point.y);
      if (p != null && Number.isFinite(p)) return p;
    }

    return null;
  };

  /** 初始化图表和点击事件（只跑一次） */
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

    const handleClick = (param: MouseEventParams<Time>) => {
      const symbol = selectedSymbolRef.current;
      if (!symbol) return;

      const price = getPriceFromClick(param);
      if (price == null || !Number.isFinite(price)) return;

      const rounded = Number(price.toFixed(2));
      addLine(symbol, rounded); // 去重 & 持久化都在 store 里
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /** 选中标的变化时：更新 ref & 懒加载 K 线数据 */
  useEffect(() => {
    selectedSymbolRef.current = selectedSymbol || null;
    if (selectedSymbol) {
      loadKline(selectedSymbol);
    }
  }, [selectedSymbol, loadKline]);

  /**
   * 当 symbol / kline / priceLines 变化时：
   * - 设置 K 线数据
   * - 基于当前 symbol 的 priceLines 重画水平线
   */
  useEffect(() => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    if (!chart || !series) return;

    // 清理旧线
    lineMapRef.current.forEach((pl) => {
      try {
        series.removePriceLine(pl);
      } catch {}
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

    // 默认展示最近 80 根
    const n = bars.length;
    if (n > 80) {
      const from = bars[n - 80].time as any;
      const to = bars[n - 1].time as any;
      chart.timeScale().setVisibleRange({ from, to });
    } else {
      chart.timeScale().fitContent();
    }

    // 画出当前 symbol 的水平线
    const lines: PriceLine[] = priceLines[selectedSymbol] || [];
    lines.forEach((l) => {
      const id = l.id || `pl_${selectedSymbol}_${l.price.toFixed(2)}`;
      const pl = series.createPriceLine({
        price: l.price,
        // 不设置 title，避免“8.30 8.30”双标签，只保留一个轴标签
        color: "#1d4ed8", // 更醒目的橙色
        lineWidth: 1,     // 比默认更粗
        lineStyle: LineStyle.Dashed,
      });
      lineMapRef.current.set(id, pl);
    });
  }, [selectedSymbol, klineMap, priceLines]);

  /** 清除当前标的所有水平线 */
  const handleClear = () => {
    if (!selectedSymbol) return;
    clearLines(selectedSymbol);
    // priceLines 变化会触发上面的 effect 自动清除图上线
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
