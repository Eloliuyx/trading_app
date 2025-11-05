import React, { useEffect, useState } from "react";
import { useDataStore, type StockItem } from "../store";
import FilterPanel from "../components/FilterPanel";
import ResultList from "../components/ResultList";
import SymbolDetail from "../components/SymbolDetail";

type AnyJson = Record<string, any>;

function normalizeList(json: AnyJson): StockItem[] {
  const raw = (json?.list ?? json?.items ?? json?.data ?? []) as AnyJson[];
  if (!Array.isArray(raw)) return [];
  const out: StockItem[] = [];
  for (const it of raw) {
    const features = (it.features ?? it.feat ?? {}) as Record<string, any>;
    const symbol: string = it.symbol ?? it.ts_code ?? it.code ?? "";
    const name: string = it.name ?? it.security_name ?? it.title ?? symbol ?? "";
    if (!symbol || !name) continue;
    out.push({
      symbol,
      name,
      industry: it.industry ?? "",
      market: it.market ?? (symbol.endsWith(".SH") ? "SH" : symbol.endsWith(".SZ") ? "SZ" : undefined),
      score: it.score,
      reco: it.reco,
      features,
    });
  }
  return out;
}

async function fetchUniverse(): Promise<{ asof: string | null; list: StockItem[] }> {
  const paths = ["/out/universe.json", "/universe.json", "/out/market_reco.json"]; // 最后一个只是容错
  let lastErr: any = null;
  for (const p of paths) {
    try {
      const res = await fetch(p, { cache: "no-cache" });
      if (!res.ok) throw new Error(`HTTP ${res.status} @ ${p}`);
      const j = (await res.json()) as AnyJson;
      const list = normalizeList(j);
      const asof = j.asof ?? j.date ?? null;
      if (list.length > 0) return { asof, list };
      lastErr = new Error(`Parsed empty list from ${p}`);
    } catch (e) {
      lastErr = e;
    }
  }
  throw lastErr ?? new Error("No universe json found");
}

export default function MarketHome() {
  const setStocks = useDataStore((s) => s.setStocks);
  const [asof, setAsof] = useState<string | null>(null);
  const [loadMsg, setLoadMsg] = useState<string>("正在加载全市场矩阵…");

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const { asof, list } = await fetchUniverse();
        if (!mounted) return;
        setAsof(asof);
        setStocks(list);
        console.info("[Trading_App] universe loaded:", list.length, "items; asof:", asof ?? "(null)");
        setLoadMsg(list.length > 0 ? "" : "JSON 已加载，但 list 为空。请检查 export_universe 的输出。");
      } catch (e: any) {
        if (!mounted) return;
        console.error("[Trading_App] failed to load universe:", e);
        setLoadMsg("未能加载 /out/universe.json。请确认文件是否在 public/ 下且结构正确。");
        setStocks([]);
      }
    })();
    return () => { mounted = false; };
  }, [setStocks]);

// 只展示修改后的 return 部分
// 只贴 return 部分，其他逻辑不变
return (
  <div className="w-full h-full" style={{ background: "var(--bg)" }}>
    {/* 页面容器：左右留白 */}
    <div className="container" style={{ paddingTop: 12, paddingBottom: 12 }}>
      {/* 顶部标题行（保留） */}
      <div
        className="card"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "10px 14px",
          marginBottom: 12,
        }}
      >
<div
  className="h1"
  style={{
    fontSize: 22,            // ✅ 变大
    fontWeight: 700,         // ✅ 加粗
    letterSpacing: "-0.02em",
    color: "var(--fg)",      // ✅ 保持主题色
  }}
>
  日线多因子趋势过滤器
</div>

        <div className="sub" style={{ fontSize: 12 }}>{asof ? `asof ${asof}` : ""}</div>
      </div>

      {/* 筛选区域 */}
      <div className="card" style={{ marginBottom: 12, padding: 12 }}>
        <FilterPanel />
      </div>

      {/* 主体两栏：左列表 + 右K线 */}
      <div
  className="two-pane"
  style={{
    gridTemplateColumns: "260px minmax(0,1fr)", // ← 左栏更窄
    columnGap: "24px",                           // ← 两栏留白更舒服
  }}
>
        <div className="col-left">
          <div className="card" style={{ padding: 0 }}>
            <ResultList />
            {loadMsg && (
              <div className="px-3 py-2 text-xs text-amber-600 border-t bg-amber-50">
                {loadMsg}
              </div>
            )}
          </div>
        </div>
        <div className="col-right">
          <div className="kline-wrap">
            <div className="kline-card">
              <SymbolDetail />
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
);
}
