// src/components/StockCard.tsx
import React from "react";
import type { StockItem } from "../store";

type Props = {
  item: StockItem;
  selected?: boolean;
  onClick?: () => void;
};

const base: React.CSSProperties = {
  padding: "6px 10px",
  borderBottom: "1px solid #f3f4f6",
  cursor: "pointer",
  display: "flex",
  flexDirection: "column",
  gap: 2,
};

const selectedStyle: React.CSSProperties = {
  ...base,
  background: "#eff6ff",
};

const title: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  color: "#111827",
};

const subtitle: React.CSSProperties = {
  fontSize: 11,
  color: "#6b7280",
};

const infoRow: React.CSSProperties = {
  display: "flex",
  gap: 8,
  fontSize: 10,
};

const scoreStyle: React.CSSProperties = { color: "#2563eb" };
const bucketStyle: React.CSSProperties = { color: "#059669" };

const StockCard: React.FC<Props> = ({ item, selected, onClick }) => {
  return (
    <div
      style={selected ? selectedStyle : base}
      onClick={onClick}
      data-symbol={item.symbol}
    >
      <div style={title}>
        {item.symbol} {item.name}
      </div>
      <div style={subtitle}>
        {item.industry ? `${item.industry}｜` : ""}
        {item.market || ""}
        {item.is_st && "｜ST"}
      </div>
      <div style={infoRow}>
        {typeof item.score === "number" && (
          <span style={scoreStyle}>Score {Math.round(item.score)}</span>
        )}
        {item.bucket && <span style={bucketStyle}>{item.bucket}</span>}
      </div>
    </div>
  );
};

export default StockCard;
