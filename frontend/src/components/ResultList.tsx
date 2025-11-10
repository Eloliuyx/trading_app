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
  type FilterState,
} from "../store";

/**
 * 左侧结果列表：
 * - 展示当前 universe 中，满足「搜索 + 勾选因子（F1-F6）」的标的
 * - 与 FACTOR_CONFIG.test 完全一致
 * - SymbolDetail 共用同一套 FACTOR_CONFIG 展示通过情况
 *
 * 已读规则：
 * - 点击个股时，将 { [symbol]: dayKey } 写入本地状态 & localStorage
 * - dayKey = market.last_bar_date || market.asof || "na"
 * - 刷新页面：从 localStorage 恢复 -> 同一交易日内不丢失已读
 * - 交易日变化时：仅保留当前 dayKey，等价于「只在更新数据后清空已读」
 */

const fontFamily =
  "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', sans-serif";

const READ_MAP_KEY = "ta_read_map_v1";

/** 从 localStorage 恢复 readMap */
function loadReadMap(): Record<string, string> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(READ_MAP_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object") {
      return parsed as Record<string, string>;
    }
  } catch {
    // ignore
  }
  return {};
}

/** 持久化 readMap 到 localStorage */
function persistReadMap(map: Record<string, string>) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(READ_MAP_KEY, JSON.stringify(map));
  } catch {
    // ignore quota / privacy errors
  }
}

const containerStyle: React.CSSProperties = {
  flex: "0 0 260px", // 左侧宽度，可按需再微调
  display: "flex",
  flexDirection: "column",
  borderRight: "1px solid #e5e7eb",
  background: "#f9fafb",
  overflow: "hidden",
  fontFamily,
};

const headerStyle: React.CSSProperties = {
  padding: "8px 12px",
  borderBottom: "1px solid #e5e7eb",
  fontSize: 11,
  color: "#6b7280",
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  background: "#ffffff",
};

const listStyle: React.CSSProperties = {
  flex: 1,
  overflowY: "auto",
};

const itemBase: React.CSSProperties = {
  padding: "8px 10px",
  borderBottom: "1px solid #f3f4f6",
  cursor: "pointer",
  display: "flex",
  flexDirection: "column",
  gap: 2,
  background: "#ffffff",
  transition: "background 0.15s ease, box-shadow 0.15s ease, transform 0.05s ease",
};

const itemHover: React.CSSProperties = {
  background: "#f9fafb",
};

const itemSelected: React.CSSProperties = {
  ...itemBase,
  background: "#eef2ff",
  boxShadow: "inset 2px 0 0 #4f46e5",
};

const itemRead: React.CSSProperties = {
  ...itemBase,
  background: "#fff7ed",
};

const titleStyle: React.CSSProperties = {
  fontSize: 13,
  fontWeight: 600,
  color: "#111827",
  letterSpacing: "-0.01em",
};

const subtitleStyle: React.CSSProperties = {
  fontSize: 10,
  color: "#9ca3af",
};

const infoRowStyle: React.CSSProperties = {
  display: "flex",
  gap: 6,
  fontSize: 9,
  alignItems: "center",
};

const scoreStyle: React.CSSProperties = {
  color: "#2563eb",
  fontWeight: 500,
};

const bucketStyle: React.CSSProperties = {
  padding: "0 6px",
  borderRadius: 999,
  border: "1px solid #bbf7d0",
  fontSize: 9,
  color: "#16a34a",
};

/** 文本搜索：支持代码 & 名称关键字 */
function matchSearch(stock: StockItem, q: string): boolean {
  const text = q.trim();
  if (!text) return true;
  const t = text.toLowerCase();
  return (
    stock.symbol.toLowerCase().includes(t) ||
    (stock.name || "").toLowerCase().includes(t)
  );
}

/** 多因子过滤：仅对勾选的因子应用 test */
function matchFactors(stock: StockItem, filter: FilterState): boolean {
  for (const cfg of FACTOR_CONFIG) {
    const key = cfg.key as FKey;
    if (!filter[key]) continue;
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

  const [readMap, setReadMap] = useState<Record<string, string>>(
    () => loadReadMap()
  );
  const listRef = useRef<HTMLDivElement | null>(null);

  // readMap -> localStorage
  useEffect(() => {
    persistReadMap(readMap);
  }, [readMap]);

  // 交易日变化时，仅保留当前交易日的已读记录
  useEffect(() => {
    const dayKey = market?.last_bar_date || market?.asof || "";
    if (!dayKey) return;
    setReadMap((prev) => {
      const next: Record<string, string> = {};
      for (const [sym, dk] of Object.entries(prev)) {
        if (dk === dayKey) next[sym] = dk;
      }
      return next;
    });
  }, [market?.last_bar_date, market?.asof]);

  // 当前可见标的列表
  const visible = useMemo(() => {
    if (!stocks?.length) return [];
    return stocks
      .filter((s) => matchSearch(s, filter.q))
      .filter((s) => matchFactors(s, filter));
  }, [stocks, filter]);

  // 点击选中 & 标记已读
  const handleSelect = (item: StockItem) => {
    setSelectedSymbol(item.symbol);
    const dayKey = market?.last_bar_date || market?.asof || "na";
    setReadMap((prev) => {
      if (prev[item.symbol] === dayKey) return prev;
      return { ...prev, [item.symbol]: dayKey };
    });
  };

  // 键盘上下键导航
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
        container.scrollTop =
          bottom - container.clientHeight + 8;
      }
    }
  };

  const status = market?.status;

  return (
    <div
      style={containerStyle}
      tabIndex={0}
      onKeyDown={onKeyDown}
    >
      {/* 顶部状态栏 */}
      <div style={headerStyle}>
        <span>结果 {visible.length} 条</span>
        <span>
          {status === "ERROR" && "数据加载失败"}
          {status === "NO_DATA" && "无数据"}
          {status === "OK" && "来自 universe.json"}
        </span>
      </div>

      {/* 列表 */}
      <div ref={listRef} style={listStyle}>
        {visible.map((item) => {
          const dayKey = market?.last_bar_date || market?.asof || "na";
          const isRead = readMap[item.symbol] === dayKey;
          const isSelected = item.symbol === selectedSymbol;

          let style = itemBase;
          if (isSelected) style = itemSelected;
          else if (isRead) style = itemRead;

          return (
            <div
              key={item.symbol}
              data-symbol={item.symbol}
              style={style}
              onMouseEnter={(e) => {
                if (!isSelected && !isRead) {
                  Object.assign(e.currentTarget.style, itemHover);
                }
              }}
              onMouseLeave={(e) => {
                if (!isSelected && !isRead) {
                  Object.assign(e.currentTarget.style, {
                    background: itemBase.background as string,
                    boxShadow: "none",
                  });
                }
              }}
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
              fontSize: 11,
              color: "#9ca3af",
            }}
          >
            当前条件下暂无标的。建议放宽筛选条件，逐步叠加 F1-F6 检查。
          </div>
        )}
      </div>
    </div>
  );
};

export default ResultList;
