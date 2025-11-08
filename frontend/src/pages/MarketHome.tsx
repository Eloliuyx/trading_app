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
  fontSize: 18,
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
  minHeight: 0,
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
  background: "#ffffff",
};

const MarketHome: React.FC = () => {
  const { market, loadMarket } = useDataStore((s) => ({
    market: s.market,
    loadMarket: s.loadMarket,
  }));

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
          <div style={titleStyle}>日线多因子趋势过滤器</div>
          <a
            href="/reco_logic_zh.html"
            target="_blank"
            rel="noreferrer"
            style={linkStyle}
          >
            规则解释（F1–F9）
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
            <div
              style={{
                flex: 1,
                minHeight: 0,
                borderBottom: "1px solid #e5e7eb",
              }}
            >
              <KLineChart />
            </div>
            <div style={{ flex: "0 0 auto" }}>
              <SymbolDetail />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MarketHome;
