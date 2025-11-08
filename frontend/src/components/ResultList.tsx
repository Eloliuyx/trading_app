// src/components/ResultList.tsx
import React, {
  useMemo,
  useEffect,
  useRef,
  useState,
  KeyboardEvent,
} from "react";
import {
  useDataStore,
  FACTOR_CONFIG,
  type StockItem,
  type FKey,
} from "../store";

const containerStyle: React.CSSProperties = {
  flex: "0 0 340px",
  display: "flex",
  flexDirection: "column",
  borderRight: "1px solid #e5e7eb",
  background: "#ffffff",
  overflow: "hidden",
};

const headerStyle: React.CSSProperties = {
  padding: "6px 10px",
  borderBottom: "1px solid #e5e7eb",
  fontSize: 11,
  color: "#6b7280",
  display: "flex",
  justifyContent: "space-between",
};

const listStyle: React.CSSProperties = {
  flex: 1,
  overflowY: "auto",
};

const itemBase: React.CSSProperties = {
  padding: "6px 10px",
  borderBottom: "1px solid #f3f4f6",
  cursor: "pointer",
  display: "flex",
  flexDirection: "column",
  gap: 2,
};

const itemSelected: React.CSSProperties = {
  ...itemBase,
  background: "#eff6ff",
};

// ✅ 已读颜色改成浅橘色，比较醒目
const itemRead: React.CSSProperties = {
  ...itemBase,
  background: "#fff7ed", // tailwind 的 orange-50 类似
};

const titleStyle: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  color: "#111827",
};

const subtitleStyle: React.CSSProperties = {
  fontSize: 11,
  color: "#6b7280",
};

const infoRowStyle: React.CSSProperties = {
  display: "flex",
  gap: 8,
  fontSize: 10,
};

const scoreStyle: React.CSSProperties = { color: "#2563eb" };
const bucketStyle: React.CSSProperties = { color: "#059669" };

const FLAG_KEYS: FKey[] = FACTOR_CONFIG.map((f) => f.key);

function matchSearch(stock: StockItem, q: string): boolean {
  const text = q.trim();
  if (!text) return true;
  const t = text.toLowerCase();
  return (
    stock.symbol.toLowerCase().includes(t) ||
    (stock.name || "").toLowerCase().includes(t)
  );
}

function matchFactors(stock: StockItem, filter: Record<FKey, boolean>): boolean {
  for (const cfg of FACTOR_CONFIG) {
    if (!filter[cfg.key]) continue;
    if (!cfg.test(stock)) return false;
  }
  return true;
}

const ResultList: React.FC = () => {
  const {
    stocks,
    filter,
    selectedSymbol,
    setSelectedSymbol,
    market,
  } = useDataStore((s) => ({
    stocks: s.stocks,
    filter: s.filter,
    selectedSymbol: s.selectedSymbol,
    setSelectedSymbol: s.setSelectedSymbol,
    market: s.market,
  }));

  const [readMap, setReadMap] = useState<Record<string, string>>({});
  const listRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setReadMap({});
  }, [market?.last_bar_date, market?.asof]);

  const visible = useMemo(() => {
    if (!stocks?.length) return [];
    const f = filter;
    return stocks
      .filter((s) => matchSearch(s, f.q))
      .filter((s) => matchFactors(s, f as any));
  }, [stocks, filter]);

  const handleSelect = (item: StockItem) => {
    setSelectedSymbol(item.symbol);
    const dayKey = market?.last_bar_date || market?.asof || "na";
    setReadMap((prev) => ({ ...prev, [item.symbol]: dayKey }));
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!visible.length) return;
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();

    const idx = visible.findIndex((s) => s.symbol === selectedSymbol);
    let nextIdx = idx;

    if (e.key === "ArrowDown") {
      nextIdx = idx < 0 ? 0 : Math.min(visible.length - 1, idx + 1);
    } else {
      nextIdx = idx <= 0 ? 0 : idx - 1;
    }

    const next = visible[nextIdx];
    if (!next) return;
    handleSelect(next);

    const container = listRef.current;
    const el = container?.querySelector<HTMLDivElement>(
      `[data-symbol="${next.symbol}"]`
    );
    if (container && el) {
      const top = el.offsetTop;
      const bottom = top + el.offsetHeight;
      if (top < container.scrollTop) {
        container.scrollTop = top - 8;
      } else if (bottom > container.scrollTop + container.clientHeight) {
        container.scrollTop = bottom - container.clientHeight + 8;
      }
    }
  };

  const status = market?.status;

  return (
    <div style={containerStyle} tabIndex={0} onKeyDown={onKeyDown}>
      <div style={headerStyle}>
        <span>结果 {visible.length} 条</span>
        <span>
          {status === "ERROR" && "数据加载失败"}
          {status === "NO_DATA" && "无数据"}
          {status === "OK" && "来自 universe.json"}
        </span>
      </div>

      <div ref={listRef} style={listStyle}>
        {visible.map((item) => {
          const dayKey = market?.last_bar_date || market?.asof || "na";
          const isRead = readMap[item.symbol] === dayKey;
          const isSelected = item.symbol === selectedSymbol;
          const style = isSelected
            ? itemSelected
            : isRead
            ? itemRead
            : itemBase;

          return (
            <div
              key={item.symbol}
              data-symbol={item.symbol}
              style={style}
              onClick={() => handleSelect(item)}
            >
              <div style={titleStyle}>
                {item.symbol} {item.name}
              </div>
              <div style={subtitleStyle}>
                {item.industry ? `${item.industry}｜` : ""}
                {item.market || ""}
                {item.is_st && "｜ST"}
              </div>
              <div style={infoRowStyle}>
                {typeof item.score === "number" && (
                  <span style={scoreStyle}>
                    Score {Math.round(item.score)}
                  </span>
                )}
                {item.bucket && (
                  <span style={bucketStyle}>{item.bucket}</span>
                )}
              </div>
            </div>
          );
        })}

        {visible.length === 0 && (
          <div
            style={{
              padding: 16,
              fontSize: 12,
              color: "#9ca3af",
            }}
          >
            当前条件下暂无标的。
            建议先取消全部 F，再逐个开启排查。
          </div>
        )}
      </div>
    </div>
  );
};

export default ResultList;
