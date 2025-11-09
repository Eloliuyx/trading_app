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
 * - 展示当前 universe 中，满足「搜索 + 勾选因子（F1-F6）」的标的；
 * - 与 FACTOR_CONFIG 完全一致：
 *    - FilterPanel 控制 FilterState.FX 开关
 *    - 这里用 FACTOR_CONFIG.test 做实际判断
 *    - SymbolDetail 也用同一套 FACTOR_CONFIG.test 展示通过情况
 */

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

const itemRead: React.CSSProperties = {
  ...itemBase,
  background: "#fff7ed",
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

/**
 * 文本搜索：
 * - 支持代码 & 名称关键字；
 * - 空字符串 = 不限制。
 */
function matchSearch(stock: StockItem, q: string): boolean {
  const text = q.trim();
  if (!text) return true;
  const t = text.toLowerCase();
  return (
    stock.symbol.toLowerCase().includes(t) ||
    (stock.name || "").toLowerCase().includes(t)
  );
}

/**
 * 多因子过滤：
 * - 使用 FACTOR_CONFIG 驱动；
 * - 若 filter[key] 为 true，则要求该因子 test(stock) 通过；
 * - 所有勾选因子均通过，才保留该标的。
 *
 * 注意：
 * - 这里以 FilterState 为输入（包含 q 和 F1-F6），实际只使用 FKey 部分。
 * - 与 SymbolDetail 中展示逻辑共用 FACTOR_CONFIG，保证定义唯一。
 */
function matchFactors(stock: StockItem, filter: FilterState): boolean {
  for (const cfg of FACTOR_CONFIG) {
    const key = cfg.key as FKey;
    if (!filter[key]) continue;      // 未勾选该因子 -> 不参与过滤
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

  /** 记录“某日已经点开看过”的标的，用于浅色标记 */
  const [readMap, setReadMap] = useState<Record<string, string>>({});
  const listRef = useRef<HTMLDivElement | null>(null);

  // 当交易日变更时，清空已读标记
  useEffect(() => {
    setReadMap({});
  }, [market?.last_bar_date, market?.asof]);

  /**
   * 根据「搜索 + 勾选因子」得到当前可见列表：
   * - 搜索命中；
   * - 且满足所有开启的 F1-F6。
   */
  const visible = useMemo(() => {
    if (!stocks?.length) return [];
    return stocks
      .filter((s) => matchSearch(s, filter.q))
      .filter((s) => matchFactors(s, filter));
  }, [stocks, filter]);

  /** 点击或键盘导航选中某个标的 */
  const handleSelect = (item: StockItem) => {
    setSelectedSymbol(item.symbol);
    const dayKey = market?.last_bar_date || market?.asof || "na";
    setReadMap((prev) => ({ ...prev, [item.symbol]: dayKey }));
  };

  /**
   * 键盘上下键导航：
   * - 在当前 visible 列表中移动选中项；
   * - 自动滚动到可见区域。
   */
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
          const style =
            isSelected ? itemSelected : isRead ? itemRead : itemBase;

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
