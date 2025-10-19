import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

function App() {
  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', padding: 16 }}>
      <h1>Trading_App</h1>
      <p>这是前端 MVP 的起点。接下来会接入日K图与叠加层。</p>
      <ul>
        <li>✅ 中文 UI</li>
        <li>✅ Vite + React + TS</li>
        <li>⏳ 即将加入：轻量图表 lightweight-charts</li>
      </ul>
    </div>
  )
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>
)
