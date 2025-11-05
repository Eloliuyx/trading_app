# ALGO SPEC — trend-v0.3 (practical + weak-to-strong)

版本标识：`rules_version = "trend-v0.3"`
时区：`Asia/Shanghai`
数据口径：**未复权日线**，输入字段：`Date,Open,High,Low,Close,Volume`

---

## 1. 记号与窗口
- `t`：当日索引（最后一根 K 线）
- `MAk(X)[t]`：`X` 在 `t` 时刻的 k 日简单移动均值
- `std_k`：近 `k` 日样本标准差（使用 `ddof=0` 固定口径）
- `rankpct(x, S)`：`x` 在集合 `S` 中的百分位秩，定义为 `(rank-1)/(N-1)`；若 `N=1` 则返回 `1.0`
- `percentile(S, p)`：线性插值法（`method="linear"`）的 p 分位

---

## 2. 硬条件（全部满足）

### 2.1 趋势方向
1) `MA5(Close)[t] > MA13(Close)[t] > MA39(Close)[t]`
2) `MA13(Close)[t] > MA13(Close)[t-1]`
3) `Close[t] > MA13(Close)[t]`

> 注：均使用收盘价简单算术均值；采用严格不等式保证确定性。

### 2.2 量价确认
1) `Volume[t] ≥ 1.5 × MA5(Volume)[t]`
2) `Close[t] ≥ 0.98 × max(High[t-4..t])`（近 5 日最高价的 98%）

### 2.3 涨幅过滤
记 `pct = (Close[t] / Close[t-1] - 1) × 100`
要求：`3 ≤ pct ≤ 6`

### 2.4 筹码结构（近似）
1) **活跃度**：`VolActive10 = Volume[t] / MA10(Volume)[t] ≥ 1.2`
2) **收敛度**：`std10 = std(Close[t-9..t])`，`std30 = std(Close[t-29..t])`，要求 `std10 / std30 ≤ 0.8`
3) **位置**：`Close[t] ≥ percentile(Close[t-29..t], 0.80)`

### 2.5 风险过滤（自动）— 连板 ≥ 3 日剔除
- 由 `symbols.csv` 推断：
  - `is_st == True` → `LIM_PCT = 0.05`
  - `market ∈ {创业板, 科创板}` → `LIM_PCT = 0.20`
  - 其他 → `LIM_PCT = 0.10`
- 定义容差：`EPS = 0.002`（0.2%）
- 定义“涨停日”：
  - `chg = Close[t]/Close[t-1] - 1`
  - `is_limit[t] = (chg ≥ LIM_PCT - EPS)`
- 连板天数（含当日）：
  `streak[t] = is_limit[t] ? 1 + streak[t-1] : 0`
- 规则：`streak[t] ≥ 3` → **剔除**

> 建议增加“上市 ≤ N 日剔除”（新股无涨跌限制期），默认 `N=10` 可选。

### 2.6 结构确认（弱转强）
`max(Open[t], Close[t]) > max(Open[t-1], Close[t-1])`

---

## 3. 评分（排序用，入池后才计算）
score = 0.4 * Trend + 0.35 * VolumePrice + 0.25 * Chips

- `Trend = 1`（所有趋势条件满足）；否则不入池
- `VolumePrice = 0.5 * clamp( Volume[t] / (1.5*MA5Vol[t]), 0, 1 )
                 + 0.5 * clamp( Close[t] / (0.98*maxHigh5[t]), 0, 1 )`
- `Chips = 0.34 * clamp( VolActive10 / 1.2, 0, 1 )
         + 0.33 * clamp( 0.8 / (std10/std30), 0, 1 )
         + 0.33 * rankpct( Close[t], Close[t-29..t] )`

---

## 4. 缺失与边界处理
- 任一指标窗口不足（例如不足 39 根）→ 判定为**不满足**（不入池）
- 全部使用 `ddof=0` 的标准差；`percentile` 采用 `linear` 方法
- 价格与量均为**未复权**口径；仅使用**相邻日相对涨跌**参与连板判定
- 任何等号边界按本文定义执行，避免实现歧义

---

## 5. 输出字段（摘要）
见 `backend/docs/API_CONTRACT.md`。推荐项包含：
- `symbol, name, industry, market, score`
- `checks`（各模块 pass 与关键数值）
- `reasons`（人类可读的简要理由）
- `notes`（如“风险项需人工复核：炸板/极端乖离”等）
