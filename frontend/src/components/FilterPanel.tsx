// src/components/FilterPanel.tsx
import React from "react";
import { useDataStore, FACTOR_CONFIG } from "../store";

const wrapper: React.CSSProperties = {
  padding: "8px 12px",
  borderBottom: "1px solid #e5e7eb",
  background: "#f9fafb",
  display: "flex",
  flexDirection: "column",
  gap: 8,
};

const row: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: 12,
  alignItems: "center",
};

const label: React.CSSProperties = {
  fontSize: 12,
  color: "#6b7280",
};

const input: React.CSSProperties = {
  padding: "4px 8px",
  fontSize: 12,
  borderRadius: 4,
  border: "1px solid #d1d5db",
  outline: "none",
  width: 180,
};

const checkboxLabel: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 4,
  fontSize: 12,
  color: "#111827",
  cursor: "pointer",
};

const FilterPanel: React.FC = () => {
  const { filter, setFilter, toggleFlag } = useDataStore((s) => ({
    filter: s.filter,
    setFilter: s.setFilter,
    toggleFlag: s.toggleFlag,
  }));

  return (
    <div style={wrapper}>
      <div style={row}>
        <div
          style={{
            fontSize: 13,
            fontWeight: 600,
            color: "#111827",
          }}
        >
          多因子过滤
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={label}>搜索</span>
          <input
            style={input}
            placeholder="代码 / 名称关键字"
            value={filter.q}
            onChange={(e) => setFilter({ q: e.target.value })}
          />
        </div>
      </div>

      <div style={row}>
        <span style={label}>规则选择：</span>
        {FACTOR_CONFIG.map((f) => (
          <label key={f.key} style={checkboxLabel}>
            <input
              type="checkbox"
              checked={!!filter[f.key]}
              onChange={() => toggleFlag(f.key)}
              style={{ width: 12, height: 12 }}
            />
            <span>{f.label}</span>
          </label>
        ))}
      </div>
    </div>
  );
};

export default FilterPanel;
