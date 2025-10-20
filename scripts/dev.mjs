import { spawn } from "node:child_process";

const argv = process.argv.slice(2);
const getArg = (k, def = null) => {
  const hit = argv.find(a => a.startsWith(`--${k}=`));
  if (hit) return hit.split("=")[1];
  return argv.includes(`--${k}`) ? true : def;
};

// 支持参数：--symbol=600519.SH --mode=precision --t=2025-09-30 --workers=4 --no-frontend
const symbol = getArg("symbol", null);
const mode = getArg("mode", symbol ? "precision" : "recall"); // 单股默认 precision，全市场默认 recall
const cutoff = getArg("t", null);
const workers = getArg("workers", null);
const noFrontend = getArg("no-frontend", false);
const port = getArg("port", null);

// 拼接后端命令
let backendCmd = "";
if (symbol) {
  backendCmd = `cd core && python -m core.cli analyze ${symbol} --mode ${mode}${cutoff ? ` --t=${cutoff}` : ""}`;
} else {
  backendCmd = `cd core && python -m core.cli analyze-all --mode ${mode}${cutoff ? ` --t=${cutoff}` : ""}${workers ? ` --workers=${workers}` : ""}`;
}

// 前端命令（可选端口）
const frontendCmd = port
  ? `cd frontend && cross-env PORT=${port} npm run dev`
  : `cd frontend && npm run dev`;

const composite = noFrontend
  ? backendCmd
  : `npx concurrently "${backendCmd}" "${frontendCmd}"`;

console.log(`[dev] backend: ${backendCmd}`);
if (!noFrontend) console.log(`[dev] frontend: ${frontendCmd}`);

const child = spawn(composite, { shell: true, stdio: "inherit" });
child.on("exit", code => process.exit(code ?? 0));
