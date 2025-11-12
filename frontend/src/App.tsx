// src/App.tsx
import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import MarketHome from "./pages/MarketHome";
import SymbolPage from "./pages/Symbol"; //

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MarketHome />} />
        <Route path="/symbol" element={<SymbolPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
