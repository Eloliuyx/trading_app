# Trading_App

> 一个**完全确定性**的「缠中说禅」结构识别与可视化系统。
> 目标：从 CSV 日K 生成客观、可复现的结构（分型/笔/线段/中枢/势），并输出当日建议与买点强度。

## 结构
Trading_App/
├── core/ # Python 分析引擎（无随机、可复现）
├── app/ # React+Vite 前端可视化（中文 UI）
├── data/ # CSV（日K，前复权，Asia/Shanghai）
├── out/ # 分析输出 JSON
└── .github/ # CI

markdown
Copy code

## 快速开始
- Python: `cd core && uv venv && uv pip install -e . && pre-commit install && pytest -q`
- Web: `cd app && npm i && npm run dev`

数据规范与输出格式见 `/README.data.md`（后续补充）。
