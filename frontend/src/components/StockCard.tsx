import React from "react";
import { StockLite, useDataStore } from "../store";


export default function StockCard({ s }: { s: StockLite }) {
const sel = useDataStore(st => st.selectedSymbol);
const setSel = useDataStore(st => st.setSelectedSymbol);
const ft = s.features || {};
const risk = (ft.is_one_word || (ft.limit_count_5d ?? 0) >= 3 || ft.is_st);


const tag = (t: string) => <span className="text-xs px-2 py-0.5 rounded bg-slate-100 border">{t}</span>;


return (
<div className={`p-3 border-b cursor-pointer ${sel===s.symbol ? "bg-amber-50" : "hover:bg-slate-50"}`} onClick={()=>setSel(s.symbol)}>
<div className="flex items-center justify-between">
<div className="font-medium">{s.name} <span className="text-slate-400 text-xs">{s.symbol}</span></div>
<div className="flex items-center gap-2">
{s.bucket && <span className="text-xs px-1.5 py-0.5 rounded bg-emerald-50 border border-emerald-200">{s.bucket}</span>}
{typeof s.score === 'number' && <span className="text-xs text-slate-500">{s.score}</span>}
{risk && <span title="高风险：连板/一字/ST" className="text-xs text-red-600">⚠️</span>}
</div>
</div>
<div className="mt-1 text-slate-500 text-xs">{s.industry} · {s.market}</div>
<div className="mt-2 flex flex-wrap gap-1">
{ft.ma_alignment && tag("MA 5>13>39")}
{typeof ft.pct_ind_rs20 === 'number' && tag(`行业RS p${Math.round(ft.pct_ind_rs20*100)}`)}
{typeof ft.pct_vr === 'number' ? tag(`VR p${Math.round(ft.pct_vr*100)}`) : (typeof ft.pct_amt === 'number' && tag(`额 p${Math.round(ft.pct_amt*100)}`))}
{typeof ft.prox_h9 === 'number' && tag(`HHV9 ${(ft.prox_h9*100).toFixed(1)}%`) }
{typeof ft.compress === 'number' && tag(`ATR压缩 ${ft.compress.toFixed(2)}`)}
</div>
</div>
);
}
