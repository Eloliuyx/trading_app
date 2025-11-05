import React, { useEffect, useMemo, useState } from 'react';
import { useDataStore } from '../store';
import type { SymbolMeta } from '../types';

export default function SymbolPicker() {
  const { symbol, setSymbol, loadAllFor, symbols, loadSymbols } = useDataStore();
  const [query, setQuery] = useState(symbol ?? '');
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  // 初次挂载加载清单
  useEffect(() => { loadSymbols().catch(()=>{}); }, [loadSymbols]);

  // 搜索（简单节流）
  useEffect(() => {
    const h = setTimeout(async () => {
      if (!query || query.length < 2) { setOpen(false); return; }
      setLoading(true);
      try { await loadSymbols(query); setOpen(true); } finally { setLoading(false); }
    }, 220);
    return () => clearTimeout(h);
  }, [query, loadSymbols]);

  const onLoad = () => {
    // 允许输入 “名称（代码）” 或 直接代码
    const match = query.match(/\(([^)]+)\)\s*$/);
    const pick = match ? match[1] : query.trim();
    if (!pick) return;
    setSymbol(pick);
    loadAllFor(pick).catch(()=>{});
    setOpen(false);
  };

  const suggestions = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return symbols.slice(0, 20);
    return symbols.filter(s =>
      (s.symbol?.toLowerCase().includes(q) || s.name?.toLowerCase().includes(q))
    ).slice(0, 20);
  }, [symbols, query]);

  return (
    <div style={{ position:'relative', display:'flex', alignItems:'center', gap:8, flexWrap:'wrap' }}>
      <div style={{ position:'relative', flex:1, minWidth:280 }}>
        <input
          value={query}
          onChange={e=>setQuery(e.target.value)}
          onFocus={()=> setOpen(!!query && query.length>=2)}
          placeholder="输入代码或名称（至少 2 个字符）"
          style={{ width:'100%', padding:'8px 12px', borderRadius:10, border:'1px solid #e5e7eb' }}
        />
        {loading && <div style={{ position:'absolute', right:10, top:8, fontSize:12, color:'#9ca3af' }}>正在搜索…</div>}
        {open && suggestions.length>0 && (
          <div style={{
            position:'absolute', zIndex:30, top:'calc(100% + 6px)', left:0, right:0,
            background:'#fff', border:'1px solid #e5e7eb', borderRadius:12, boxShadow:'0 8px 24px rgba(0,0,0,0.06)',
            maxHeight:300, overflowY:'auto'
          }}>
            {suggestions.map(s => {
              const label = s.name ? `${s.name} (${s.symbol})` : s.symbol;
              return (
                <div
                  key={s.symbol}
                  onMouseDown={(e)=>{ e.preventDefault(); setQuery(label); setOpen(false);}}
                  style={{ padding:'8px 12px', cursor:'pointer' }}
                  onMouseEnter={(e)=> (e.currentTarget.style.background='#f9fafb')}
                  onMouseLeave={(e)=> (e.currentTarget.style.background='transparent')}
                >
                  {label}
                </div>
              );
            })}
          </div>
        )}
      </div>

      <button
        onClick={onLoad}
        style={{
          padding:'8px 14px', borderRadius:10, border:'1px solid #e5e7eb',
          background:'#111827', color:'#fff', fontWeight:600
        }}
      >
        载入
      </button>
      <a href="/market" style={{ textDecoration: 'none', color: '#6b21a8', fontWeight: 600 }}>
        全市场
      </a>
    </div>
  );
}
