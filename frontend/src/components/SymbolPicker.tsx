import React, { useEffect, useMemo, useState } from 'react';
import { useDataStore } from '../store';
import type { SymbolMeta } from '../types';

export default function SymbolPicker() {
  const { symbol, setSymbol, loadAllFor, symbols, loadSymbols } = useDataStore();
  const [query, setQuery] = useState(symbol ?? '');

  // 初次挂载先拉一波清单（不带 q）
  useEffect(() => { loadSymbols().catch(()=>{}); }, [loadSymbols]);

  // 输入变化时做简单节流搜索
  useEffect(() => {
    const h = setTimeout(() => {
      if (query && query.length >= 2) loadSymbols(query).catch(()=>{});
    }, 180);
    return () => clearTimeout(h);
  }, [query, loadSymbols]);

  useEffect(() => { if (symbol) setQuery(symbol); }, [symbol]);

  const onLoad = () => {
    if (!query) return;
    // 若用户选择了“名称 (代码)”的格式，提取代码
    const m = query.match(/\((\d{6}\.(SH|SZ|BJ))\)$/i);
    const picked = m ? m[1].toUpperCase() : query.trim().toUpperCase();
    setSymbol(picked);
    loadAllFor(picked);
  };

  const options = useMemo(() => {
    const list = symbols ?? [];
    return list.slice(0, 500); // 防止 datalist 过长
  }, [symbols]);

  return (
    <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
      <label style={{ fontSize: 12, color: '#6b7280' }}>选择股票</label>

      <input
        list="__symbol_list__"
        value={query}
        onChange={(e)=>setQuery(e.target.value)}
        placeholder="代码或名称，例如 600036.SH / 招商银行"
        style={{ minWidth: 280 }}
        onKeyDown={(e)=>{ if (e.key === 'Enter') onLoad(); }}
      />
      <datalist id="__symbol_list__">
        {options.map((s: SymbolMeta) => {
          const label = s.name ? `${s.name} (${s.symbol})` : s.symbol;
          return <option key={s.symbol} value={label} />;
        })}
      </datalist>

      <button onClick={onLoad}>载入</button>

      {/* 唯一的市场入口 */}
      <a href="/market" style={{ marginLeft: 8, textDecoration: 'none', color: '#6b21a8', fontWeight: 600 }}>
        全市场
      </a>
    </div>
  );
}
