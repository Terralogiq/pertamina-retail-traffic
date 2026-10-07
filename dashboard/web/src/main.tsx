import "./theme/tokens.css";
import "@fontsource-variable/epilogue";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./theme/echarts";
import { applyDataPalette } from "./theme/palette";

applyDataPalette(document.documentElement);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
