import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Local-only control plane: bind localhost, proxy /api + /ws to the FastAPI
// backend so the browser talks same-origin in dev (PLAN.md §5.6, §10).
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    // Same-origin in dev too, so the code path exercised here is the one that
    // ships. `ws: true` also covers /api/ws, which lives under the same prefix.
    proxy: {
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: false, ws: true },
    },
  },
});
