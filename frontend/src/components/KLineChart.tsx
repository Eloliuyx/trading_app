import React, { useEffect, useRef } from 'react';
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
} from 'lightweight-charts';

export type ReadyApis = {
  chart: IChartApi;
  candle: ISeriesApi<'Candlestick'>;
  containerEl: HTMLDivElement;
};

type Props = {
  data: CandlestickData[];          // time 必须是秒级 UTCTimestamp
  height?: number;
  onReady?(apis: ReadyApis): void;
};

const KLineChart: React.FC<Props> = ({ data, height = 460, onReady }) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const onReadyRef = useRef<Props['onReady']>(onReady);

  // 持有最新 onReady 引用（不触发重建）
  useEffect(() => {
    onReadyRef.current = onReady;
  }, [onReady]);

  // 创建/销毁图表（只创建一次；StrictMode 二次挂载有守卫）
  useEffect(() => {
    if (!containerRef.current) return;
    if (chartRef.current) return;

    const chart = createChart(containerRef.current, {
      height,
      autoSize: true,
      layout: { background: { color: '#ffffff' }, textColor: '#222' },
      grid: { vertLines: { visible: false }, horzLines: { color: '#eee' } },
      rightPriceScale: { borderVisible: false },
      leftPriceScale: { visible: false },
      crosshair: { mode: 0 },
    });

    chart.timeScale().applyOptions({
      rightOffset: 0,
      barSpacing: 6,
      fixLeftEdge: false,
      lockVisibleTimeRangeOnResize: true,
      rightBarStaysOnScroll: true,
      timeVisible: true,
      secondsVisible: false,
    });

    const series = chart.addCandlestickSeries({
      upColor: '#26a69a',
      downColor: '#ef5350',
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
      borderVisible: false,
    });

    chartRef.current = chart;
    candleRef.current = series;

    if (onReadyRef.current && containerRef.current) {
      onReadyRef.current({
        chart,
        candle: series,
        containerEl: containerRef.current,
      });
    }

    return () => {
      // 先清引用，再安全 remove
      candleRef.current = null;
      const c = chartRef.current;
      chartRef.current = null;
      try {
        c?.remove();
      } catch {
        /* 已释放时忽略 */
      }
    };
  }, [height]);

  // 数据变动时 setData
  useEffect(() => {
    if (!candleRef.current) return;
    if (!data?.length) {
      candleRef.current.setData([]);
      return;
    }
    candleRef.current.setData(data);
    chartRef.current?.timeScale().fitContent();
  }, [data]);

  return <div ref={containerRef} style={{ width: '100%', height }} />;
};

export default KLineChart;
