# API 契约 — trend-v0.3

## 1. 全市场推荐（文件或接口）
- 路径（文件）：`/out/market_reco.json`
- 路径（接口，建议）：`GET /api/reco/market`

**响应：**
```json
{
  "asof": "2025-11-03T14:30:00+08:00",
  "last_bar_date": "2025-11-03",
  "rules_version": "trend-v0.3",
  "count": 102,
  "list": [
    {
      "symbol": "600519.SH",
      "name": "贵州茅台",
      "industry": "饮料制造",
      "market": "主板",
      "score": 0.88,
      "checks": {
        "trend": { "pass": true },
        "volume_price": {
          "pass": true,
          "volume_mult": 1.8,
          "high_5d": 1685.0,
          "close_ratio_to_high5": 0.992
        },
        "chips": {
          "pass": true,
          "vol_active10": 1.33,
          "std10": 4.5,
          "std30": 7.0,
          "std_ratio": 0.64,
          "position30": 0.86
        },
        "pct_change": 4.1,
        "limit_streak": 0,
        "weak_to_strong": true
      },
      "reasons": [
        "趋势：MA5>MA13>MA39 且 MA13 上拐",
        "量价：量能为5日均量1.8倍，收盘价接近5日高点",
        "涨幅：+4.1%，动能健康",
        "筹码：活跃度↑、收敛、位于近30日上侧区间",
        "结构：今日实体区间上移（弱转强）"
      ],
      "notes": ["（提示）炸板/极端乖离仍需人工复核"]
    }
  ]
}
