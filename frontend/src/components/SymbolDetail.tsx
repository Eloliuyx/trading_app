// src/components/SymbolDetail.tsx
import React, { useMemo, useState } from "react";
import {
  useDataStore,
  FACTOR_CONFIG,
  type StockItem,
} from "../store";

/** ====== 视觉样式改进版 ======
 * 目标：
 * - 字体层级清晰，留白舒适；
 * - 中英文都友好；
 * - 强调层次：标题>副标题>标签>笔记；
 * - 统一现代 Web App 感。
 */

const fontFamily =
  "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', sans-serif";

const container: React.CSSProperties = {
  padding: "16px 20px",
  borderTop: "1px solid #e5e7eb",
  background: "#ffffff",
  display: "flex",
  flexDirection: "column",
  gap: 12,
  fontFamily,
};

const title: React.CSSProperties = {
  fontSize: 22,
  fontWeight: 600,
  color: "#111827",
  letterSpacing: "-0.01em",
};

const subtitle: React.CSSProperties = {
  fontSize: 13,
  color: "#6b7280",
  marginTop: -4,
};

const infoRow: React.CSSProperties = {
  display: "flex",
  gap: 12,
  alignItems: "center",
  marginTop: 2,
  fontSize: 13,
};

const scoreStyle: React.CSSProperties = {
  color: "#2563eb",
  fontWeight: 500,
};

const bucketStyle: React.CSSProperties = {
  color: "#059669",
  fontWeight: 500,
};

const secTitle: React.CSSProperties = {
  fontSize: 15,
  fontWeight: 600,
  color: "#111827",
  marginTop: 10,
};

const tagRow: React.CSSProperties = {
  display: "flex",
  flexWrap: "wrap",
  gap: 8,
  marginTop: 4,
};

const tagBase: React.CSSProperties = {
  padding: "4px 10px",
  borderRadius: 999,
  fontSize: 13,
  border: "1px solid #e5e7eb",
  transition: "all 0.2s ease",
};

const tagPass: React.CSSProperties = {
  ...tagBase,
  color: "#047857",
  borderColor: "#bbf7d0",
  background: "#ecfdf5",
};

const tagFail: React.CSSProperties = {
  ...tagBase,
  color: "#9ca3af",
  background: "#f9fafb",
};

const reason: React.CSSProperties = {
  fontSize: 14,
  color: "#374151",
  lineHeight: 1.6,
  paddingLeft: 4,
};

const noteInput: React.CSSProperties = {
  width: "100%",
  minHeight: 60,
  padding: "8px 10px",
  fontSize: 14,
  borderRadius: 6,
  border: "1px solid #d1d5db",
  resize: "vertical",
  fontFamily,
  color: "#111827",
};

const noteItem: React.CSSProperties = {
  padding: "8px 10px",
  background: "#f9fafb",
  borderRadius: 6,
  fontSize: 14,
  color: "#374151",
  display: "flex",
  justifyContent: "space-between",
  alignItems: "flex-start",
  gap: 8,
  lineHeight: 1.4,
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
        <div style={{ fontSize: 14, color: "#9ca3af" }}>
          左侧选择一只股票，查看多因子结果与个人备注。
        </div>
      </div>
    );
  }

  const asof =
    item.last_date || market?.last_bar_date || market?.asof || "";

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

      <div style={infoRow}>
        {typeof item.score === "number" && (
          <span style={scoreStyle}>
            综合评分 {Math.round(item.score)}
          </span>
        )}
        {item.bucket && <span style={bucketStyle}>{item.bucket}</span>}
      </div>

      <div style={secTitle}>多因子规则通过情况</div>
      <div style={tagRow}>
        {FACTOR_CONFIG.map((f) => {
          const pass = f.test(item);
          const style = pass ? tagPass : tagFail;
          const prefix = pass ? "✓" : "•";
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

      {/* 笔记输入区域 */}
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
        <div
          style={{
            marginTop: 6,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <button
            style={{
              padding: "6px 14px",
              fontSize: 14,
              fontWeight: 500,
              borderRadius: 6,
              border: "1px solid #d1d5db",
              background: "#111827",
              color: "#f9fafb",
              cursor: "pointer",
              fontFamily,
            }}
            onClick={handleAddNote}
          >
            保存笔记
          </button>
          <div
            style={{
              fontSize: 11,
              color: "#9ca3af",
              fontFamily,
            }}
          >
            笔记仅保存在本机（localStorage）
          </div>
        </div>
      </div>

      {/* 笔记列表 */}
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 6,
          marginTop: 6,
        }}
      >
        {notes.map((n) => (
          <div key={n.id} style={noteItem}>
            <div style={{ flex: 1 }}>
              <div>{n.text}</div>
              <div
                style={{
                  fontSize: 12,
                  color: "#9ca3af",
                  marginTop: 2,
                }}
              >
                {new Date(n.ts).toLocaleString()}
              </div>
            </div>
            <button
              onClick={() => deleteNote(item.symbol, n.id)}
              style={{
                border: "none",
                background: "transparent",
                fontSize: 12,
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
