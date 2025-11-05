import React, { useEffect, useMemo, useState } from "react";
import { useDataStore, type PriceLine, type Note } from "../store";
import KLineChart from "./KLineChart";

/** 读取 CSV（public/data/{symbol}.csv） */
async function fetchCsv(symbol: string): Promise<string> {
  const p = `/data/${symbol}.csv`;
  const res = await fetch(p, { cache: "no-cache" });
  if (!res.ok) throw new Error(`HTTP ${res.status} @ ${p}`);
  return await res.text();
}

type Row = {
  Date: string;
  Open: number;
  High: number;
  Low: number;
  Close: number;
  Volume: number;
};

/** 兼容无 Volume；修正换行解析 */
function parseCsv(txt: string): Row[] {
  if (!txt.trim()) return [];
  const lines = txt.replace(/^\uFEFF/, "").trim().split(/\r?\n/);
  const headers = lines[0].split(",");
  const idx = (k: string) => headers.indexOf(k);
  const iD = idx("Date"),
    iO = idx("Open"),
    iH = idx("High"),
    iL = idx("Low"),
    iC = idx("Close"),
    iV = idx("Volume");
  if (iD < 0 || iO < 0 || iH < 0 || iL < 0 || iC < 0) return [];
  return lines.slice(1).map((ln) => {
    const a = ln.split(",");
    return {
      Date: a[iD],
      Open: Number(a[iO]),
      High: Number(a[iH]),
      Low: Number(a[iL]),
      Close: Number(a[iC]),
      Volume: iV >= 0 ? Number(a[iV]) : 0,
    };
  });
}

export default function SymbolDetail() {
  const selected = useDataStore((s) => s.selectedSymbol);
  const stocks = useDataStore((s) => s.stocks);

  // 水平线 API
  const getLines = useDataStore((s) => s.getLines);
  const addLine = useDataStore((s) => s.addLine);
  const replaceLines = useDataStore((s) => s.replaceLines);

  // 笔记 API
  const getNotes = useDataStore((s) => s.getNotes);
  const addNote = useDataStore((s) => s.addNote);
  const deleteNote = useDataStore((s) => s.deleteNote);

  const stock = useMemo(
    () => stocks.find((x) => x.symbol === selected),
    [stocks, selected]
  );

  const [kdata, setKdata] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [lines, setLines] = useState<PriceLine[]>([]);
  const [notes, setNotes] = useState<Note[]>([]);

  /** 加载 CSV + 本地 lines/notes */
  useEffect(() => {
    let mounted = true;
    (async () => {
      if (!selected) return;
      try {
        setLoading(true);
        const txt = await fetchCsv(selected);
        if (!mounted) return;
        const rows = parseCsv(txt);
        const data = rows.map((r) => ({
          time: r.Date,
          open: r.Open,
          high: r.High,
          low: r.Low,
          close: r.Close,
        }));
        setKdata(data);
      } catch (e) {
        console.warn("failed to fetch csv for", selected, e);
        setKdata([]);
      } finally {
        if (mounted) setLoading(false);
      }
      // 本地线/笔记
      setLines(getLines(selected));
      setNotes(getNotes(selected));
    })();
    return () => {
      mounted = false;
    };
  }, [selected, getLines, getNotes]);

  /** 唯一“昨收线”：存在则更新价格，不新增重复 */
  const addYesterdayClose = () => {
    if (!selected || !kdata.length) return;
    const last = kdata[kdata.length - 1];
    const price = Number(last.close);
    const cur = getLines(selected);
    const others = cur.filter((l) => l.title !== "昨收");
    const existing = cur.find((l) => l.title === "昨收");
    const id = existing?.id ?? `${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
    const next = [...others, { id, price, title: "昨收" }];
    replaceLines(selected, next);
    setLines(getLines(selected));
  };

  /** 点击图面新增一条价格线：标题直接用价格（显示更直观） */
  const handleAddLineFromClick = (price: number) => {
    if (!selected) return;
    const title = price.toFixed(2);
    addLine(selected, price, title);
    setLines(getLines(selected));
  };

  if (!stock) {
    return (
      <div className="h-full flex items-center justify-center text-gray-500">
        请选择左侧任意个股查看详情
      </div>
    );
  }

  return (
    <div
    className="h-full flex flex-col bg-white"
    style={{
      paddingLeft: "24px",   // ← 增加左侧留白
      paddingRight: "24px",  // ← 增加右侧留白（保持对称）
      paddingTop: "24px",
    }}
  >
{/* 头部：一行紧凑展示 */}
<div className="px-4 py-2 border-b bg-white">
  <div style={{fontSize:"15px", fontWeight:700, letterSpacing:"-.01em", color:"#0f172a"}}>
    {stock.name}
    <span className="ml-2" style={{fontSize:"12px", color:"#64748b", fontWeight:500}}>
      &nbsp;&nbsp;{stock.symbol}{stock.industry ? ` · ${stock.industry}` : ""}
    </span>
  </div>
</div>


      {/* 图表卡片 */}
      <div className="kline-wrap flex-1 overflow-auto">
        {loading ? (
          <div className="p-3 text-sm text-gray-500">加载 K 线…</div>
        ) : kdata.length === 0 ? (
          <div className="p-3 text-sm text-gray-500">暂无 K 线数据</div>
        ) : (
          <div className="card kline-card">
            <KLineChart
              className="kline-host"
              data={kdata as any}
              priceLines={lines}
              onAddLineFromClick={handleAddLineFromClick}
            />
          </div>
        )}
      </div>

      {/* 工具按钮条 */}
{/* 辅助按钮 */}
<div className="border-t bg-white" style={{ padding: "10px 16px", marginTop: 4 }}>
  <div className="toolbar" style={{ gap: 10 }}>
    <button className="btn btn--sm btn--primary" onClick={addYesterdayClose}>
      加昨收线
    </button>
    <button
      className="btn btn--sm btn--ghost"
      onClick={() => {
        if (!selected) return;
        replaceLines(selected, []);
        setLines([]);
      }}
    >
      清空水平线
    </button>
  </div>
</div>


      {/* 笔记区 */}
      <div className="notes border-t">
        <NotesPanel
          symbol={stock.symbol}
          notes={notes}
          onAdd={(text) => {
            addNote(stock.symbol, text);
            setNotes(getNotes(stock.symbol));
          }}
          onDelete={(id) => {
            deleteNote(stock.symbol, id);
            setNotes(getNotes(stock.symbol));
          }}
        />
      </div>
    </div>
  );
}

/* ============== 笔记组件 ============== */
function NotesPanel({
  symbol,
  notes,
  onAdd,
  onDelete,
}: {
  symbol: string;
  notes: Note[];
  onAdd: (text: string) => void;
  onDelete: (id: string) => void;
}) {
  const [text, setText] = useState("");

  return (
    <div>
      <h4 className="text-sm text-gray-500 mb-2">我的笔记（{symbol}）</h4>
      <div className="flex gap-2 mb-2">
  <input
    className="flex-1 border rounded px-2 py-1 text-sm"
    placeholder="写点什么…"
    value={text}
    onChange={(e) => setText(e.target.value)}
  />
  <button
    className="btn btn--sm btn--primary"
    onClick={() => {
      if (!text.trim()) return;
      onAdd(text.trim());
      setText("");
    }}
  >
    添加
  </button>
</div>

      {notes.length === 0 ? (
        <div className="text-xs text-gray-500">

        </div>
      ) : (
        <ul>
          {notes.map((n) => (
            <li key={n.id} className="row">
              <div>
                <div className="date">{n.date}</div>
                <div>{n.text}</div>
              </div>
              <button
  className="btn btn--xs btn--danger"
  onClick={() => onDelete(n.id)}
  title="删除"
>
  删除
</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
