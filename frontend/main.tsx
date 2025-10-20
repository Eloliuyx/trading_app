// frontend/main.tsx
import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'


const root = document.getElementById('root')
if (!root) {
  throw new Error('Missing #root element in index.html')
}

createRoot(root).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
