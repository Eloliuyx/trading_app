import React from "react";
import KLineChart from "./components/KLineChart";
import { useDataStore } from "./store";

export default function App() {
  const symbol = useDataStore((s) => s.symbol);
  const load = useDataStore((s) => s.loadSeriesCDemo);
  const clear = useDataStore((s) => s.clear);

  return (
    <div style={{ padding: 16 }}>
      <h1>Trading_App</h1>
      <p>
        当前标的： <b>{symbol}</b>{" "}
        <button onClick={load} style={{ marginLeft: 8 }}>
          载入 Series-C Demo 数据
        </button>
        <button onClick={clear} style={{ marginLeft: 8 }}>清空</button>
      </p>

      <KLineChart />

      <p style={{ marginTop: 16, color: "#4caf50" }}>
        ✅ 如果能看到蜡烛图，说明 store 与图表工作正常；下一步即可对接后端 API。
      </p>
    </div>
  );
}
