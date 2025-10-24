import React from 'react';
import { useDataStore } from '../store';
import { pct } from '../utils/format';

export default function InsightPanel() {
  const { outJson } = useDataStore();
  if (!outJson) return <div>空态：请选择股票或点击载入示例数据</div>;

  const { shi, recommendation_for_today: rec, meta, rules_version } = outJson;
  return (
    <div>
      <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>分析信息</div>
      <div style={{ fontSize: 12, color: '#6b7280', marginBottom: 12 }}>
        {meta.symbol}｜规则版本 {rules_version}｜数据截至 {outJson.meta.last_bar_date}
      </div>

      <section style={{ marginBottom: 16 }}>
        <div style={{ color: '#374151', fontWeight: 600 }}>当前势</div>
        <div style={{ marginTop: 4 }}>{shi.class}</div>
        <div style={{ marginTop: 4, fontSize: 12, color: '#6b7280' }}>
          结构置信度：{pct(shi.confidence)}{shi.momentum!=null ? ` ｜ 动能：${pct(shi.momentum)}`:''}{shi.risk!=null ? ` ｜ 风险：${pct(shi.risk)}`:''}
        </div>
        {shi.evidence?.length ? (
          <ul style={{ marginTop: 6, paddingLeft: 18 }}>
            {shi.evidence.map((e, i) => <li key={i} style={{ fontSize: 12 }}>{e}</li>)}
          </ul>
        ) : null}
      </section>

      <section style={{ marginBottom: 16 }}>
        <div style={{ color: '#374151', fontWeight: 600 }}>今日建议（{rec.at_close_of}）</div>
        <div style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ padding: '2px 8px', borderRadius: 999, background: '#eef2ff', color: '#4338ca', fontWeight: 600 }}>{rec.action}</span>
          <span>买点强度：{pct(rec.buy_strength)}</span>
        </div>
        <div style={{ marginTop: 6 }}>{rec.rationale}</div>
        <div style={{ marginTop: 6, fontSize: 12, color: '#6b7280' }}>无效条件：{rec.invalidate_if}</div>
      </section>

      <section>
        <div style={{ color: '#374151', fontWeight: 600 }}>结构统计</div>
        <div style={{ marginTop: 6, fontSize: 12, color: '#6b7280' }}>
          分型 {outJson.fractals.length} ｜ 笔 {outJson.bis.length} ｜ 段 {outJson.segments.length} ｜ 中枢 {outJson.zhongshus.length}
        </div>
      </section>
    </div>
  );
}
