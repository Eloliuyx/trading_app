// src/components/FilterPanel.tsx
import React from "react";
import { useDataStore, FACTOR_CONFIG } from "../store";

/** ===== 改进版 UI 样式 =====
 * - 更干净的布局、更现代的灰白层次
 * - 统一字体与圆角
 * - hover 效果轻微强调
 * - 同 SymbolDetail 一致的字体体系
 */

const fontFamily =
  "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', sans-serif";

const wrapper: React.CSSProperties = {
  padding: "14px 20px",
  borderBottom: "1px solid #e5e7eb",
  background: "#f8fafc",
  display: "flex",
  flexDirection: "column",
  gap: 14,
  fontFamily,
};

const row: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: 14,
  alignItems: "center",
};

const label: React.CSSProperties = {
  fontSize: 14,
  color: "#4b5563",
  fontWeight: 500,
};

const input: React.CSSProperties = {
  padding: "8px 10px",
  fontSize: 14,
  borderRadius: 8,
  border: "1px solid #d1d5db",
  outline: "none",
  width: 220,
  transition: "all 0.2s ease",
  background: "#ffffff",
  fontFamily,
  color: "#111827",
};
const inputFocus: React.CSSProperties = {
  ...input,
  borderColor: "#93c5fd",
  boxShadow: "0 0 0 2px rgba(37,99,235,0.15)",
};

const checkboxLabel: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 6,
  fontSize: 14,
  color: "#1f2937",
  cursor: "pointer",
  padding: "4px 8px",
  borderRadius: 6,
  transition: "all 0.15s ease",
};

const checkboxLabelHover: React.CSSProperties = {
  ...checkboxLabel,
  background: "#f3f4f6",
};

const FilterPanel: React.FC = () => {
  const { filter, setFilter, toggleFlag } = useDataStore((s) => ({
    filter: s.filter,
    setFilter: s.setFilter,
    toggleFlag: s.toggleFlag,
  }));

  return (
    <div style={wrapper}>
      {/* 搜索框 */}
      <div style={row}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={label}>搜索</span>
          <input
            style={input}
            placeholder="输入代码 / 名称关键字…"
            value={filter.q}
            onChange={(e) => setFilter({ q: e.target.value })}
            onFocus={(e) => (e.currentTarget.style.boxShadow = inputFocus.boxShadow!)}
            onBlur={(e) => (e.currentTarget.style.boxShadow = "")}
          />
        </div>
      </div>

      {/* 因子筛选 */}
      <div style={row}>
        <span style={label}>多因子规则：</span>
        {FACTOR_CONFIG.map((f) => (
          <label
            key={f.key}
            style={checkboxLabel}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = "#f3f4f6";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = "transparent";
            }}
          >
            <input
              type="checkbox"
              checked={!!filter[f.key]}
              onChange={() => toggleFlag(f.key)}
              style={{
                width: 14,
                height: 14,
                accentColor: "#2563eb",
                cursor: "pointer",
              }}
            />
            <span>{f.label}</span>
          </label>
        ))}

        {/* F7：隐藏弱股（本地标记） */}
        <label
          style={checkboxLabel}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "#f3f4f6";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "transparent";
          }}
        >
          <input
            type="checkbox"
            checked={!!filter.F7}
            onChange={() => toggleFlag("F7")}
            style={{
              width: 14,
              height: 14,
              accentColor: "#2563eb",
              cursor: "pointer",
            }}
          />
          <span>F7: 隐藏弱股</span>
        </label>
      </div>
    </div>
  );
};

export default FilterPanel;
