import time
from typing import Any, Dict

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本地开发先全开；上线请收紧
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- 结构（与前端保持一致）----
# Candle: {time, open, high, low, close}
# MA:     {name, values:[{time, value}]}
# Segment: [{time, value}]
# Zone:   {upper, lower, tStart, tEnd}


@app.get("/api/series-c/bundle")
def series_c_bundle(
    symbol: str = Query(...),
    tf: str = Query("1d"),
) -> Dict[str, Any]:
    # 1) 假数据/替换为你的数据源 & 计算逻辑
    now = int(time.time())
    day = 86400
    candles = []
    price = 100.0
    for i in range(120):
        t = now - (119 - i) * day
        o = price
        h = o + 1.5
        l = o - 1.5
        c = o + (0.8 if i % 5 == 0 else -0.4)
        candles.append(
            {
                "time": t,
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(l, 2),
                "close": round(c, 2),
            }
        )
        price = c

    # 2) 计算 MA20/MA60（示例）
    def ma(values, n):
        out = []
        s = 0.0
        for i, c in enumerate(values):
            s += c["close"]
            if i >= n:
                s -= values[i - n]["close"]
            if i >= n - 1:
                out.append({"time": c["time"], "value": round(s / n, 2)})
        return out

    ma20 = {"name": "MA20", "values": ma(candles, 20)}
    ma60 = {"name": "MA60", "values": ma(candles, 60)}

    # 3) 线段（示例：用三点标出一段走势）
    segments = [
        [
            {"time": candles[30]["time"], "value": candles[30]["close"]},
            {"time": candles[45]["time"], "value": candles[45]["close"]},
            {"time": candles[60]["time"], "value": candles[60]["close"]},
        ]
    ]

    # 4) 中枢/交易带（示例）
    zones = [
        {
            "upper": candles[70]["close"] + 1.2,
            "lower": candles[70]["close"] - 1.2,
            "tStart": candles[60]["time"],
            "tEnd": candles[85]["time"],
        }
    ]

    return {
        "symbol": symbol,
        "timeframe": tf,
        "candles": candles,
        "ma": [ma20, ma60],
        "segments": segments,
        "zones": zones,
    }
