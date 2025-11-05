import React, { useEffect, useRef } from "react";
import { createChart, IChartApi, ISeriesApi, CandlestickData } from "lightweight-charts";

function getParam(name: string): string | null {
  return new URLSearchParams(window.location.search).get(name);
}

export default function SymbolPage() {
  const symbol = getParam("symbol") || "";
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const c = createChart(ref.current, { height: 420 });
    const s = c.addCandlestickSeries();
    chartRef.current = c;
    seriesRef.current = s;
    return () => c.remove();
  }, []);

  useEffect(() => {
    if (!symbol || !seriesRef.current) return;
    fetch(`/data/${symbol}.csv`)
      .then((r) => r.text())
      .then((txt) => {
        const lines = txt.trim().split(/\r?\n/);
        const head = lines.shift()!;
        const idx = head.split(",");
        const mapIndex = (k: string) => idx.indexOf(k);
        const iDate = mapIndex("Date"), iOpen = mapIndex("Open"), iHigh = mapIndex("High"), iLow = mapIndex("Low"), iClose = mapIndex("Close");
        const rows: CandlestickData[] = lines.map((ln) => {
          const a = ln.split(",");
          return {
            time: a[iDate] as any,
            open: Number(a[iOpen]),
            high: Number(a[iHigh]),
            low: Number(a[iLow]),
            close: Number(a[iClose]),
          };
        });
        seriesRef.current!.setData(rows);
      });
  }, [symbol]);

  return (
    <div className="p-4 max-w-5xl mx-auto">
      <div className="mb-3 flex items-center justify-between">
        <h1 className="text-xl font-semibold">个股：{symbol}</h1>
        <a className="border px-3 py-2 rounded" href="/">返回</a>
      </div>
      <div ref={ref} />
      <div className="mt-3 text-sm opacity-70">
        数据口径：未复权日线（/public/data/{symbol}.csv）
      </div>
    </div>
  );
}
