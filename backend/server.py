# 仅示意：确保指向 public/out
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Trading_App API (trend-v0.3)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ROOT = Path(__file__).resolve().parents[1]
PROJ = ROOT.parent
PUBLIC = PROJ / "public"
MARKET_JSON = PUBLIC / "out" / "market_reco.json"


@app.get("/api/reco/market")
def market():
    if not MARKET_JSON.exists():
        raise HTTPException(404, "market_reco.json not found. run CLI first.")
    return json.loads(MARKET_JSON.read_text(encoding="utf-8"))
