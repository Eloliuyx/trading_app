import React, { useState } from 'react';
import KLineChart, { ReadyApis } from './components/KLineChart';
import Overlays from './components/Overlays';
import InsightPanel from './components/InsightPanel';
import SymbolPicker from './components/SymbolPicker';
import { useDataStore } from './store';

export default function App() {
  const { candles, outJson } = useDataStore();
  const [apis, setApis] = useState<ReadyApis | null>(null);

  const segments = outJson?.segments ?? [];
  const zhongshus = outJson?.zhongshus ?? [];

  return (
    <div style={{ minHeight: '100vh', background: '#fff' }}>
      {/* 顶栏 */}
      <header style={{
        position: 'sticky', top: 0, zIndex: 10, backdropFilter: 'saturate(150%) blur(4px)',
        background: 'rgba(255,255,255,0.85)', borderBottom: '1px solid #eee'
      }}>
        <div style={{
          maxWidth: 1180, margin: '0 auto', padding: '10px 16px',
          display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap'
        }}>
          <a href="/market" style={{ textDecoration: 'none', color: '#6b21a8', fontWeight: 700, fontSize: 16 }}>
            全市场
          </a>
          <div style={{ flex: 1 }} />
          <SymbolPicker />
        </div>
      </header>

      {/* 主体：图表 + 面板（纵向） */}
      <main style={{ maxWidth: 1180, margin: '0 auto', padding: '12px 16px 32px' }}>
        <section style={{ position: 'relative', width: '100%', minHeight: 420 }}>
          <KLineChart
            data={candles}
            height={480}
            onReady={(r) => setApis(r)}
          />
          {apis && (
            <Overlays
              chart={apis.chart}
              candle={apis.candle}
              containerEl={apis.containerEl}
              data={candles}
              segments={segments}
              zhongshus={zhongshus}
              minSpanBars={2}
            />
          )}
        </section>

        {/* 深度分析/结构信息 —— 放在图表下方，天然响应式 */}
        <section style={{
          marginTop: 16,
          border: '1px solid #eee',
          borderRadius: 12,
          padding: 16,
          boxShadow: '0 1px 2px rgba(0,0,0,0.04)'
        }}>
          <InsightPanel />
        </section>
      </main>
    </div>
  );
}
