import React, { useMemo } from "react";
import { useDataStore } from "../store";

type FKeys =
  | "f_exclude_st" | "f_liquid_strong" | "f_price_floor"
  | "f_high_amt" | "f_high_vr" | "f_ind_rank_top5"
  | "f_strong_industry" | "f_bull_ma";

function activeFlags(filter: any): FKeys[] {
  const all: FKeys[] = [
    "f_exclude_st","f_liquid_strong","f_price_floor",
    "f_high_amt","f_high_vr","f_ind_rank_top5",
    "f_strong_industry","f_bull_ma",
  ];
  if (!filter) return [];
  return all.filter((k) => !!filter[k]);
}

function passByFlags(ft: any, flags: FKeys[]): boolean {
  if (!flags.length) return true;
  if (!ft) return false;
  for (const k of flags) if (!ft[k]) return false;
  return true;
}

export default function ResultList() {
  const stocks = useDataStore((s) => s.stocks);
  const filter: any = useDataStore((s) => s.filter as any);
  const setSelected = useDataStore((s: any) => s.setSelectedSymbol ?? (() => {}));
  const selected = useDataStore((s: any) => s.selectedSymbol ?? null);

  const flags = activeFlags(filter);

  const items = useMemo(() => {
    const arr = (stocks ?? []).filter((s) => passByFlags(s.features, flags));
    // 强度友好排序：先按 pct_rs20 再按 pct_amt
    arr.sort((a, b) => {
      const fa = a.features ?? {};
      const fb = b.features ?? {};
      const ar = Number(fa.pct_rs20 ?? -1);
      const br = Number(fb.pct_rs20 ?? -1);
      if (br !== ar) return br - ar;
      const aa = Number(fa.pct_amt ?? -1);
      const ba = Number(fb.pct_amt ?? -1);
      if (ba !== aa) return ba - aa;
      return (b.name ?? "").localeCompare(a.name ?? "");
    });
    return arr;
  }, [stocks, flags]);

  return (
    <div className="h-full flex flex-col">
      <div className="list-head">命中：{items.length} 条</div>
      <div className="list-scroll">
        {items.length === 0 ? (
          <div className="p-3 text-sm text-gray-500">当前条件下没有结果，试着取消一些勾选。</div>
        ) : (
          items.map((s) => {
            const active = selected === s.symbol;
            return (
              <button
                key={s.symbol}
                className={`list-item ${active ? "selected" : ""}`}
                onClick={() => {
                  (useDataStore as any).setState?.({ selectedSymbol: s.symbol });
                  setSelected?.(s.symbol);
                }}
              >
<div className="list-title">
  {s.name}
  <span className="ml-2" style={{ fontWeight: 500, fontSize: "12px", color: "#64748b" }}>
    &nbsp;&nbsp;{s.symbol}{s.industry ? ` · ${s.industry}` : ""}
  </span>
</div>
                {/* 不再显示“强流动性”等标签，保持简洁 */}
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}
