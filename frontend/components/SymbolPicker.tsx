import React, { useEffect, useState } from 'react';
import { useDataStore } from '../store';

const PRESETS = ['600519.SH', '000001.SZ', '300750.SZ'];

export default function SymbolPicker() {
  const { symbol, setSymbol, loadAllFor, market } = useDataStore();
  const [input, setInput] = useState(symbol ?? '');

  useEffect(() => { if (symbol) setInput(symbol); }, [symbol]);

  const onLoad = () => {
    if (!input) return;
    setSymbol(input);
    loadAllFor(input);
  };

  return (
    <div style={{ display: 'flex', gap: 8 }}>
      <select value={symbol ?? ''} onChange={e => { setSymbol(e.target.value); loadAllFor(e.target.value); }}>
        <option value="" disabled>选择示例</option>
        {PRESETS.map(s => <option key={s} value={s}>{s}</option>)}
      </select>

      <input value={input} onChange={e=>setInput(e.target.value)} placeholder="输入代码（含后缀）如 600036.SH" />
      <button onClick={onLoad}>载入</button>

      {/* 市场页入口（占位） */}
      <a href="/market" style={{ marginLeft: 8, textDecoration: 'none' }}>全市场</a>
    </div>
  );
}
