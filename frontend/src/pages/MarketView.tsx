import React, { useEffect } from 'react';
import { useDataStore } from '../store';

export default function MarketView() {
  const { market, loadMarket } = useDataStore();
  useEffect(()=>{ loadMarket(); }, [loadMarket]);

  if (!market) return <div style={{ padding: 16 }}>正在加载 market_index.json …</div>;

  const tabs = ['买','观察买点','持有','止盈','回避'] as const;

  return (
    <div style={{ padding: 16 }}>
      <h2>全市场视图</h2>
      <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
        规则版本 {market.rules_version} ｜ 模式 {market.mode} ｜ asof {market.asof}
      </div>

      {tabs.map(tab => (
        <section key={tab} style={{ marginBottom: 16 }}>
          <h3 style={{ marginBottom: 8 }}>{tab}</h3>
          <table width="100%" style={{ borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ textAlign: 'left', background: '#f9fafb' }}>
                <th style={{ padding: 8 }}>代码</th>
                <th style={{ padding: 8 }}>买点强度</th>
              </tr>
            </thead>
            <tbody>
              {(market.buckets[tab] ?? []).map(sym => (
                <tr key={sym} style={{ borderTop: '1px solid #e5e7eb' }}>
                  <td style={{ padding: 8 }}>{sym}</td>
                  <td style={{ padding: 8 }}>{(market.buy_strength[sym] ?? 0).toFixed(2)}</td>
                </tr>
              ))}
              {(!market.buckets[tab] || market.buckets[tab].length===0) && (
                <tr><td colSpan={2} style={{ padding: 8, color: '#9ca3af' }}>（空）</td></tr>
              )}
            </tbody>
          </table>
        </section>
      ))}
    </div>
  );
}
