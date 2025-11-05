import React, { useEffect } from "react";
import { useDataStore } from "../store";

type FKeys =
  | "f_exclude_st"
  | "f_liquid_strong"
  | "f_price_floor"
  | "f_high_amt"
  | "f_high_vr"
  | "f_ind_rank_top5"
  | "f_strong_industry"
  | "f_bull_ma";

const DEFAULT_ON: FKeys[] = ["f_exclude_st", "f_liquid_strong", "f_price_floor", "f_bull_ma"];

export default function FilterPanel() {
  const filter: any = useDataStore((s) => s.filter as any);
  const setFilter = useDataStore((s) => (s as any).setFilter as (p: any) => void);

  // 初始化默认勾选（仅在首次未设置时）
  useEffect(() => {
    const hasAnyF =
      filter &&
      Object.keys(filter).some((k) =>
        ["f_exclude_st","f_liquid_strong","f_price_floor","f_high_amt","f_high_vr","f_ind_rank_top5","f_strong_industry","f_bull_ma"].includes(k)
      );
    if (!hasAnyF) {
      const init: any = {};
      DEFAULT_ON.forEach((k) => (init[k] = true));
      setFilter(init);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onToggle = (key: FKeys) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setFilter({ [key]: e.target.checked });
  };

  const checked = (k: FKeys) => !!filter?.[k];

  return (
    <div className="filters">
      <div className="font-medium mr-2">筛选：</div>

      <label><input type="checkbox" checked={checked("f_liquid_strong")} onChange={onToggle("f_liquid_strong")} /> 强流动性</label>
      <label><input type="checkbox" checked={checked("f_price_floor")} onChange={onToggle("f_price_floor")} /> 价格底线</label>
      <label><input type="checkbox" checked={checked("f_exclude_st")} onChange={onToggle("f_exclude_st")} /> 剔除ST股</label>
      <label><input type="checkbox" checked={checked("f_high_amt")} onChange={onToggle("f_high_amt")} /> 高成交额</label>
      <label><input type="checkbox" checked={checked("f_high_vr")} onChange={onToggle("f_high_vr")} /> 高量能相对均量</label>
      <label><input type="checkbox" checked={checked("f_ind_rank_top5")} onChange={onToggle("f_ind_rank_top5")} /> 高行业排名（Top5）</label>
      <label><input type="checkbox" checked={checked("f_strong_industry")} onChange={onToggle("f_strong_industry")} /> 强势板块</label>
      <label><input type="checkbox" checked={checked("f_bull_ma")} onChange={onToggle("f_bull_ma")} /> 多头结构</label>

      <div className="ml-auto flex gap-2">
  <button
    className="btn btn--sm btn--muted"
    onClick={() => {
      const next: any = {};
      DEFAULT_ON.forEach((k) => (next[k] = true));
      setFilter(next);
    }}
  >
    恢复默认
  </button>
  <button
    className="btn btn--sm btn--ghost"
    onClick={() => setFilter({})}
  >
    全部取消
  </button>
</div>

    </div>
  );
}
