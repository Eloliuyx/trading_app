// src/components/KLineChart.tsx
import React, { useEffect, useMemo, useRef } from "react";
import {
  createChart,
  ColorType,
  LineStyle,
  type DeepPartial,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type CandlestickData,
  type HistogramData,
  type CandlestickSeriesPartialOptions,
  type LineWidth,
} from "lightweight-charts";

export type Candle = CandlestickData & { time: string }; // YYYY-MM-DD
export type VolBar = HistogramData<string>;
export type PriceLineModel = { id: string; price: number; title?: string };

export type KLineChartProps = {
  data: Candle[];
  volume?: VolBar[];
  priceLines?: PriceLineModel[];
  onAddLineFromClick?: (price: number) => void;
  onRegister?: (api: {
    chart: IChartApi;
    candle: ISeriesApi<"Candlestick">;
    volume?: ISeriesApi<"Histogram">;
    ma?: { ma5?: ISeriesApi<"Line">; ma13?: ISeriesApi<"Line">; ma39?: ISeriesApi<"Line"> };
  }) => void;
  showMA?: boolean;
  showVolume?: boolean;
  autoscale?: boolean;
  className?: string;
};

function sma(values: number[], period: number): (number | null)[] {
  if (period <= 1) return values.map((v) => (Number.isFinite(v) ? v : null));
  const res: (number | null)[] = new Array(values.length).fill(null);
  let sum = 0;
  for (let i = 0; i < values.length; i++) {
    const v = values[i];
    sum += v;
    if (i >= period) sum -= values[i - period];
    if (i >= period - 1) res[i] = sum / period;
  }
  return res;
}

export default function KLineChart({
  data,
  volume,
  priceLines = [],
  onAddLineFromClick,
  onRegister,
  showMA = true,
  showVolume = true,
  autoscale = true,
  className = "w-full h-full",
}: KLineChartProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);

  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const maRefs = useRef<{ ma5?: ISeriesApi<"Line">; ma13?: ISeriesApi<"Line">; ma39?: ISeriesApi<"Line"> }>({});
  const lineMapRef = useRef<Map<string, IPriceLine>>(new Map());

  const maData = useMemo(() => {
    if (!showMA || data.length === 0) return null;
    const closes = data.map((d) => Number(d.close));
    const t = data.map((d) => d.time);
    const mk = (arr: (number | null)[]) =>
      arr.map((v, i) => (v == null ? null : { time: t[i], value: Number(v) }));
    return {
      ma5: mk(sma(closes, 5)),
      ma13: mk(sma(closes, 13)),
      ma39: mk(sma(closes, 39)),
    };
  }, [data, showMA]);

  // init
  useEffect(() => {
    if (!hostRef.current) return;
    const container = hostRef.current;

    const chart = createChart(container, {
      layout: { background: { type: ColorType.Solid, color: "#ffffff" }, textColor: "#333" },
      grid: { vertLines: { color: "#efefef" }, horzLines: { color: "#efefef" } },
      rightPriceScale: { borderColor: "#ddd", entireTextOnly: false },
      timeScale: { borderColor: "#ddd" }, // ✅ 去掉 tickMarkFormatter，避免隐式 any
      crosshair: { mode: 0 },
      watermark: { visible: false },
    });

    const candle = chart.addCandlestickSeries({
      upColor: "#26a69a",
      borderUpColor: "#26a69a",
      wickUpColor: "#26a69a",
      downColor: "#ef5350",
      borderDownColor: "#ef5350",
      wickDownColor: "#ef5350",
      priceLineVisible: false,
    } as DeepPartial<CandlestickSeriesPartialOptions>);

    chartRef.current = chart;
    candleRef.current = candle;

    const ro = new ResizeObserver(() => {
      chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
      if (autoscale) candle.priceScale().applyOptions({ autoScale: true });
    });
    ro.observe(container);

    const clickHandler = (param: any) => {
      if (!onAddLineFromClick || !param?.point || !candleRef.current) return;
      const p = candleRef.current.coordinateToPrice(param.point.y);
      if (typeof p === "number" && isFinite(p)) onAddLineFromClick(Number(p.toFixed(3)));
    };
    chart.subscribeClick(clickHandler);

    onRegister?.({ chart, candle });

    return () => {
      chart.unsubscribeClick(clickHandler);
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      volRef.current = null;
      lineMapRef.current.clear();
      maRefs.current = {};
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // set candles
  useEffect(() => {
    if (!candleRef.current) return;
    candleRef.current.setData(data);
    if (autoscale) chartRef.current?.timeScale().fitContent();
  }, [data, autoscale]);

  // volume pane
  useEffect(() => {
    if (!chartRef.current) return;
    const chart = chartRef.current;

    // 清旧
    if (volRef.current) {
      chart.removeSeries(volRef.current);
      volRef.current = null;
    }
    if (!showVolume) return;

    const volSeries = chart.addHistogramSeries({
      priceFormat: { type: "volume" },
      priceScaleId: "vol",
      color: "#90a4ae",
    });
    volSeries.priceScale().applyOptions({ scaleMargins: { top: 0.75, bottom: 0 } });
volSeries.applyOptions({ baseLineVisible: false });  // ✅

    // ✅ 正确姿势：对该序列所属的价格轴设置 scaleMargins
    volSeries.priceScale().applyOptions({ scaleMargins: { top: 0.75, bottom: 0 } });

    const volData =
      volume && volume.length ? volume : data.map((d) => ({ time: d.time, value: 0 }));
    volSeries.setData(volData);

    onRegister?.({ chart, candle: candleRef.current!, volume: volSeries, ma: maRefs.current });

    return () => {
      if (volRef.current) {
        chart.removeSeries(volRef.current);
        volRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showVolume, volume, data]);

  // MAs
  useEffect(() => {
    if (!chartRef.current) return;
    const chart = chartRef.current;
    const candle = candleRef.current!;
    // 清旧
    Object.values(maRefs.current).forEach((s) => s && chart.removeSeries(s));
    maRefs.current = {};

    if (!showMA || !maData) return;

    const addMA = (
      seriesData: ({ time: string; value: number } | null)[] | null,
      width: number,
      style: LineStyle
    ) => {
      if (!seriesData) return undefined;
      const s = chart.addLineSeries({
        color: "#546e7a",
        lineWidth: (width as LineWidth), // ✅ lineWidth 需要 LineWidth 类型
        lineStyle: style,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      s.setData(seriesData.filter(Boolean) as { time: string; value: number }[]);
      return s;
    };

    maRefs.current.ma5 = addMA(maData.ma5, 1, LineStyle.Solid);
    maRefs.current.ma13 = addMA(maData.ma13, 1, LineStyle.Dotted);
    maRefs.current.ma39 = addMA(maData.ma39, 1, LineStyle.Dashed);

    onRegister?.({ chart, candle, volume: volRef.current ?? undefined, ma: maRefs.current });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showMA, maData]);

  // controlled price lines
  useEffect(() => {
    const series = candleRef.current;
    if (!series) return;

    for (const [id, pl] of lineMapRef.current.entries()) {
      if (!priceLines.find((l) => l.id === id)) {
        series.removePriceLine(pl);
        lineMapRef.current.delete(id);
      }
    }

    priceLines.forEach((l) => {
      const prev = lineMapRef.current.get(l.id);
      if (prev) series.removePriceLine(prev);
      const pl = series.createPriceLine({
        price: l.price,
        color: "#9e9e9e",
        lineWidth: 1 as LineWidth, // ✅
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: l.title ?? "",
      });
      lineMapRef.current.set(l.id, pl);
    });
  }, [priceLines]);

  return <div ref={hostRef} className={className} />;
}
