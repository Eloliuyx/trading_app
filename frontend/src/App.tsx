import React, { useMemo } from 'react';
import type { CandlestickData, UTCTimestamp } from 'lightweight-charts';
import KLineChart, { type ReadyApis } from './components/KLineChart';
import Overlays from './components/Overlays';
import SymbolPicker from './components/SymbolPicker';
import InsightPanel from './components/InsightPanel';
import { useDataStore } from './store';

// 仅用于“载入默认示例”的备用路径（如果你想保留）
const DEFAULT_SYMBOL = '600519.SH';

const App: React.FC = () => {
  const {
    symbol,
    candles,           // 来自 store（秒级 UTC）
    outJson,           // 分型/线段/中枢/势/建议等
    loading,
    error,
    loadSeriesCDemo,   // 载入本地示例 (/public/data + /public/out)
  } = useDataStore();

  const [apis, setApis] = React.useState<ReadyApis | null>(null);

  // store.Candle -> lightweight-charts 的 CandlestickData（结构一致，这里只做显式声明）
  const data: CandlestickData[] = useMemo(() => {
    return (candles ?? []).map(c => ({
      time: c.time as UTCTimestamp,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));
  }, [candles]);

  // overlays 数据：优先 segments，否则 bis；其余按存在性兜底
  const fractals = outJson?.fractals ?? [];
  const segments = outJson?.segments?.length ? outJson.segments
    : (outJson?.bis ?? []);
  const zhongshus = outJson?.zhongshus ?? [];

  return (
    <div style={{ padding: 12, display: 'grid', gridTemplateColumns: '1fr 320px', gap: 12, alignItems: 'start' }}>
      <div>
        {/* 顶部工具条：选择股票 + 载入示例 + 状态 */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <SymbolPicker />
          <button onClick={() => loadSeriesCDemo()}>载入示例（{DEFAULT_SYMBOL}）</button>
          {loading && <span>加载中…</span>}
          {error && <span style={{ color: 'crimson' }}>错误：{error}</span>}
          {symbol && !loading && !error && (
            <span style={{ color: '#6b7280', fontSize: 12 }}>当前：{symbol}</span>
          )}
        </div>

        {/* 主图 */}
        <KLineChart data={data} onReady={(r) => setApis(r)} />

        {/* 叠加层（需要 KLineChart ready + 有数据） */}
        {apis && data.length > 0 && (
          <Overlays
            chart={apis.chart}
            candle={apis.candle}
            containerEl={apis.containerEl}
            data={data}
            fractals={fractals}
            segments={segments}
            zhongshus={zhongshus}
          />
        )}
      </div>

      {/* 右侧信息卡 */}
      <div style={{
        border: '1px solid #e5e7eb',
        borderRadius: 12,
        padding: 12,
        position: 'sticky',
        top: 12,
        background: '#fff'
      }}>
        <InsightPanel />
      </div>
    </div>
  );
};

export default App;
