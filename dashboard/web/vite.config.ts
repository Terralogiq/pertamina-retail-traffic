import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev: `npm run dev` on :5173 proxies /api to the FastAPI app (uvicorn dashboard.api.main:app --port 8080).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8080" },
  },
});
