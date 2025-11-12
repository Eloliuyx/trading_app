// src/pages/MarketHome.tsx

import React, { useEffect } from "react";
import { useDataStore } from "../store";
import FilterPanel from "../components/FilterPanel";
import ResultList from "../components/ResultList";
import KLineChart from "../components/KLineChart";
import SymbolDetail from "../components/SymbolDetail";

const pageStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  height: "100vh",
  background: "#f3f4f6",
};

const headerStyle: React.CSSProperties = {
  padding: "10px 14px 6px",
  borderBottom: "1px solid #e5e7eb",
  background: "#ffffff",
};

const headerRowStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: 12,
};

const titleStyle: React.CSSProperties = {
  fontSize: 22,
  fontWeight: 700,
  color: "#111827",
};

const linkStyle: React.CSSProperties = {
  fontSize: 12,
  color: "#2563eb",
  textDecoration: "none",
  cursor: "pointer",
  whiteSpace: "nowrap",
};

const subtitleStyle: React.CSSProperties = {
  marginTop: 2,
  fontSize: 11,
  color: "#6b7280",
};

const warningStyle: React.CSSProperties = {
  marginTop: 2,
  fontSize: 10,
  color: "#b91c1c",
};

const contentWrapper: React.CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  minHeight: 0, // 关键：让内部 flex 区域可以正确分配高度
};

const mainStyle: React.CSSProperties = {
  flex: 1,
  display: "flex",
  minHeight: 0,
};

const rightPanel: React.CSSProperties = {
  flex: 1,
  display: "flex",
  flexDirection: "column",
  minWidth: 0,
  minHeight: 0,
  background: "#ffffff",
};

/** 上方 K 线区域：固定高度，防止撑爆下面详情区 */
const klineWrapper: React.CSSProperties = {
  flex: "0 0 380px", // 你可以根据喜好调 240-320
  minHeight: 220,
  borderBottom: "1px solid #e5e7eb",
  overflow: "hidden",
};

/** 下方详情 + 笔记区域：吃掉剩余高度，可以滚动 */
const detailWrapper: React.CSSProperties = {
  flex: 1,
  minHeight: 0,
  overflowY: "auto",
};

const MarketHome: React.FC = () => {
  const { market, loadMarket } = useDataStore((s) => ({
    market: s.market,
    loadMarket: s.loadMarket,
  }));

  // 页面首次渲染时自动加载 universe.json。
  useEffect(() => {
    loadMarket();
  }, [loadMarket]);

  const status = market?.status;
  const asof = market?.last_bar_date || market?.asof;
  const rulesVersion = market?.rules_version;

  return (
    <div style={pageStyle}>
      <header style={headerStyle}>
        <div style={headerRowStyle}>
          <div style={titleStyle}>A股日线多因子选股器</div>
          <a
            href="/reco_logic_zh.html"
            target="_blank"
            rel="noreferrer"
            style={linkStyle}
          >
            筛选规则解释
          </a>
        </div>
        <div style={subtitleStyle}>
          数据源：universe.json
          {rulesVersion && ` ｜ 规则版本：${rulesVersion}`}
          {asof && ` ｜ 数据截至：${asof}`}
          {status === "OK" && " ｜ 状态：正常"}
          {status === "NO_DATA" && " ｜ 状态：未找到有效数据"}
          {status === "ERROR" && " ｜ 状态：加载失败"}
        </div>
        {status === "ERROR" && (
          <div style={warningStyle}>
            无法加载 universe.json，请检查文件是否存在于 /public/out 或
            /public，及其 JSON 格式。
          </div>
        )}
      </header>

      <div style={contentWrapper}>
        <FilterPanel />
        <div style={mainStyle}>
          <ResultList />
          <div style={rightPanel}>
            <div style={klineWrapper}>
              <KLineChart />
            </div>
            <div style={detailWrapper}>
              <SymbolDetail />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MarketHome;
