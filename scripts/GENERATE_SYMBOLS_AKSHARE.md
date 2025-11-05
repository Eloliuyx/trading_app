# 生成 symbols.csv（AkShare）

目标：生成 `frontend/public/data/metadata/symbols.csv`，包含
`symbol,name,industry,market,is_st,exchange,code`

## 依赖安装
```bash
cd ~/Documents/Trading_App
source .venv/bin/activate  # 若有
pip install --upgrade akshare pandas

# 在Terminal一次性运行 建议每月或每季度重跑一次，以更新行业归属。
python - <<'EOF'
import os, pandas as pd, numpy as np
import akshare as ak

os.makedirs("frontend/public/data/metadata", exist_ok=True)

base = ak.stock_info_a_code_name()  # 代码、名称
base.rename(columns={"code":"code","name":"name"}, inplace=True)
base = base.dropna().drop_duplicates("code")

ind = ak.stock_board_industry_name_em()
frames = []
for _, row in ind.iterrows():
    n = row["板块名称"]
    try:
        cons = ak.stock_board_industry_cons_em(n)[["代码","名称"]].copy()
        cons["industry"] = n
        frames.append(cons)
    except Exception:
        pass
ind_df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["代码","名称","industry"])
ind_df.rename(columns={"代码":"code","名称":"name"}, inplace=True)

df = base.merge(ind_df[["code","industry"]], on="code", how="left")
df["industry"] = df["industry"].fillna("未知行业")

def ex(code):
    if code.startswith("6"): return "SH"
    if code.startswith(("0","3")): return "SZ"
    return "UNK"
def mk(code):
    if code.startswith("688"): return "科创板"
    if code.startswith("300"): return "创业板"
    if code.startswith(("0","6")): return "主板"
    return "其他"
def ts(code):
    e = ex(code)
    return f"{code}.{e}" if e in ("SH","SZ") else code

df["exchange"] = df["code"].apply(ex)
df["market"]   = df["code"].apply(mk)
df["symbol"]   = df["code"].apply(ts)
df["is_st"]    = df["name"].str.contains("ST", case=False, na=False)

df = df[["symbol","name","industry","market","is_st","exchange","code"]].drop_duplicates("symbol").sort_values("symbol")
out = "frontend/public/data/metadata/symbols.csv"
df.to_csv(out, index=False, encoding="utf-8")
print("✅ saved:", out, "rows:", len(df))
EOF
