// import React from 'react';
// import { useDataStore } from '../store';
// import { pct } from '../utils/format';

// /** 进度条颜色随强度变化 */
// function barColor(v:number){
//   if (v >= 0.8) return '#16a34a';        // 强买点 — 绿
//   if (v >= 0.6) return '#ea580c';        // 潜在买点 — 橙
//   return '#6b7280';                      // 中性 — 灰
// }

// export default function InsightPanel() {
//   const { outJson } = useDataStore();
//   if (!outJson) return <div style={{padding:12, color:'#9ca3af'}}>空态：请选择股票或点击载入示例数据</div>;

//   const { shi, recommendation_for_today: rec, meta, rules_version } = outJson;
//   const buyStrength = rec?.buy_strength ?? 0;
//   const strengthPct = Math.round((buyStrength)*100);

//   // 从 rec.invalidate_if 中尝试解析数值（例如“跌破中枢上沿 -1%”无法解析，将返回 null）
//   const priceMatch = rec?.invalidate_if ? rec.invalidate_if.match(/([0-9]+(?:\.[0-9]+)?)/) : null;
//   const parsedPrice = priceMatch ? Number(priceMatch[1]) : null;

//   const onEnterInvalidate = () => {
//     if (parsedPrice) {
//       window.dispatchEvent(new CustomEvent('hlprice', { detail: parsedPrice }));
//     }
//   };
//   const onLeaveInvalidate = () => {
//     window.dispatchEvent(new CustomEvent('hlprice', { detail: null }));
//   };

//   return (
//     <div>
//       {/* 头部信息 */}
//       <div style={{ display:'flex', alignItems:'baseline', justifyContent:'space-between', marginBottom: 8 }}>
//         <div style={{ fontSize: 16, fontWeight: 600 }}>分析信息</div>
//         <div style={{ fontSize: 12, color: '#6b7280' }}>
//           {meta.symbol}｜规则 {rules_version}｜截至 {outJson.meta.last_bar_date}
//         </div>
//       </div>

//       {/* 势与建议 */}
//       <section style={{
//         background:'#fafafa', border:'1px solid #eee', borderRadius:12, padding:12, marginBottom:12
//       }}>
//         <div style={{ display:'flex', gap:16, flexWrap:'wrap', alignItems:'center' }}>
//           <div style={{ minWidth: 180 }}>
//             <div style={{ color:'#374151', fontWeight:600, marginBottom:6 }}>今日建议</div>
//             <div><span style={{fontWeight:700}}>{rec.action}</span> ｜ 势：{shi.class}</div>
//           </div>
//           {/* 进度条 */}
//           <div style={{ flex:1, minWidth:220 }}>
//             <div style={{ display:'flex', justifyContent:'space-between', fontSize:12, color:'#6b7280', marginBottom:6 }}>
//               <span>买点强度</span>
//               <span>{strengthPct}%</span>
//             </div>
//             <div style={{ position:'relative', height:10, background:'#f1f5f9', borderRadius:999 }}>
//               <div style={{
//                 position:'absolute', left:0, top:0, bottom:0,
//                 width:`${strengthPct}%`,
//                 background: barColor(buyStrength),
//                 borderRadius:999, transition:'width 240ms ease'
//               }}/>
//             </div>
//           </div>
//         </div>
//         {rec.rationale && <div style={{ marginTop: 10 }}>{rec.rationale}</div>}
//         {rec.invalidate_if && (
//           <div
//             onMouseEnter={onEnterInvalidate}
//             onMouseLeave={onLeaveInvalidate}
//             title="悬停高亮图中的无效位（若可解析数值）"
//             style={{ marginTop: 6, fontSize: 12, color: '#6b7280', cursor: parsedPrice? 'pointer':'default', display:'inline-block' }}
//           >
//             无效条件：{rec.invalidate_if}{parsedPrice? '（悬停高亮）':''}
//           </div>
//         )}
//       </section>

//       {/* 统计信息 */}
//       <section>
//         <div style={{ color: '#374151', fontWeight: 600 }}>结构统计</div>
//         <div style={{ marginTop: 6, fontSize: 12, color: '#6b7280' }}>
//           分型 {outJson.fractals.length} ｜ 笔 {outJson.bis.length} ｜ 段 {outJson.segments.length} ｜ 中枢 {outJson.zhongshus.length}
//         </div>
//       </section>
//     </div>
//   );
// }
