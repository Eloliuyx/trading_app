// src/components/SymbolDetail.tsx
import React, { useMemo, useState } from "react";
import {
  useDataStore,
  FACTOR_CONFIG,
  type StockItem,
} from "../store";

const container: React.CSSProperties = {
  padding: "10px 12px",
  borderTop: "1px solid #e5e7eb",
  background: "#ffffff",
  display: "flex",
  flexDirection: "column",
  gap: 6,
};

const title: React.CSSProperties = {
  fontSize: 16,
  fontWeight: 600,
  color: "#111827",
};

const subtitle: React.CSSProperties = {
  fontSize: 11,
  color: "#6b7280",
};

const tagRow: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: 6,
};

const tagBase: React.CSSProperties = {
  padding: "2px 6px",
  borderRadius: 999,
  fontSize: 10,
  border: "1px solid #e5e7eb",
};

const tagPass: React.CSSProperties = {
  ...tagBase,
  color: "#047857",
  borderColor: "#bbf7d0",
  background: "#ecfdf5",
};

const tagFail: React.CSSProperties = {
  ...tagBase,
  color: "#6b7280",
  background: "#f9fafb",
};

const secTitle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  color: "#111827",
  marginTop: 4,
};

const reason: React.CSSProperties = {
  fontSize: 11,
  color: "#4b5563",
  lineHeight: 1.5,
};

const noteInput: React.CSSProperties = {
  width: "100%",
  minHeight: 40,
  padding: "4px 6px",
  fontSize: 11,
  borderRadius: 4,
  border: "1px solid #e5e7eb",
  resize: "vertical",
};

const noteItem: React.CSSProperties = {
  padding: "4px 6px",
  background: "#f9fafb",
  borderRadius: 4,
  fontSize: 10,
  color: "#4b5563",
  display: "flex",
  justifyContent: "space-between",
  gap: 6,
};

function findStock(stocks: StockItem[], symbol: string | null): StockItem | null {
  if (!symbol) return null;
  return stocks.find((s) => s.symbol === symbol) || null;
}

const SymbolDetail: React.FC = () => {
  const {
    stocks,
    selectedSymbol,
    market,
    getNotes,
    addNote,
    deleteNote,
  } = useDataStore((s) => ({
    stocks: s.stocks,
    selectedSymbol: s.selectedSymbol,
    market: s.market,
    getNotes: s.getNotes,
    addNote: s.addNote,
    deleteNote: s.deleteNote,
  }));

  const item = useMemo(
    () => findStock(stocks, selectedSymbol),
    [stocks, selectedSymbol]
  );

  const [noteText, setNoteText] = useState("");

  if (!item) {
    return (
      <div style={container}>
        <div style={{ fontSize: 12, color: "#9ca3af" }}>
          左侧选择一只股票，查看多因子结果与个人备注。
        </div>
      </div>
    );
  }

  const asof =
    item.last_date ||
    market?.last_bar_date ||
    market?.asof ||
    "";

  const notes = getNotes(item.symbol);

  const handleAddNote = () => {
    if (!noteText.trim()) return;
    addNote(item.symbol, noteText);
    setNoteText("");
  };

  return (
    <div style={container}>
      <div style={title}>
        {item.symbol} {item.name}
      </div>
      <div style={subtitle}>
        {item.industry ? `${item.industry}｜` : ""}
        {item.market || ""}
        {item.is_st && "｜ST"}
        {asof && ` ｜ 数据截至：${asof}`}
      </div>

      <div style={{ display: "flex", gap: 10 }}>
        {typeof item.score === "number" && (
          <span style={{ fontSize: 11, color: "#2563eb" }}>
            综合评分 {Math.round(item.score)}
          </span>
        )}
        {item.bucket && (
          <span style={{ fontSize: 11, color: "#059669" }}>
            {item.bucket}
          </span>
        )}
      </div>

      <div style={secTitle}>多因子规则通过情况</div>
      <div style={tagRow}>
        {FACTOR_CONFIG.map((f) => {
          const pass = f.test(item);
          const style = pass ? tagPass : tagFail;
          const prefix = pass ? "✅" : "·";
          return (
            <span key={f.key} style={style}>
              {prefix} {f.label}
            </span>
          );
        })}
      </div>

      {Array.isArray(item.reasons) && item.reasons.length > 0 && (
        <>
          <div style={secTitle}>机器解读 / 备注</div>
          <div>
            {item.reasons.map((r, i) => (
              <div key={i} style={reason}>
                • {r}
              </div>
            ))}
          </div>
        </>
      )}

      {/* 个股记笔记 */}
      <div style={secTitle}>我的笔记</div>
      <div>
        <textarea
          style={noteInput}
          placeholder="记录你对这个标的的逻辑、买卖计划..."
          value={noteText}
          onChange={(e) => setNoteText(e.target.value)}
          onKeyDown={(e) => {
            if (e.metaKey && e.key === "Enter") {
              e.preventDefault();
              handleAddNote();
            }
          }}
        />
        <div style={{ marginTop: 4, display: "flex", justifyContent: "space-between" }}>
          <button
            style={{
              padding: "2px 8px",
              fontSize: 10,
              borderRadius: 4,
              border: "1px solid #d1d5db",
              background: "#111827",
              color: "#f9fafb",
              cursor: "pointer",
            }}
            onClick={handleAddNote}
          >
            保存笔记
          </button>
          <div
            style={{
              fontSize: 9,
              color: "#9ca3af",
              alignSelf: "center",
            }}
          >
            笔记仅保存在本机（localStorage）
          </div>
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 4 }}>
        {notes.map((n) => (
          <div key={n.id} style={noteItem}>
            <div>
              <div>{n.text}</div>
              <div style={{ fontSize: 9, color: "#9ca3af", marginTop: 2 }}>
                {new Date(n.ts).toLocaleString()}
              </div>
            </div>
            <button
              onClick={() => deleteNote(item.symbol, n.id)}
              style={{
                border: "none",
                background: "transparent",
                fontSize: 10,
                color: "#9ca3af",
                cursor: "pointer",
              }}
            >
              删除
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};

export default SymbolDetail;
