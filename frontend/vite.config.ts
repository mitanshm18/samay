/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The front end talks only to SAMAY's local API (make api, 127.0.0.1:8000) through this
// proxy, so the browser sees one origin and the API needs no CORS settings.
const api = { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false } };

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: api,
    // The example bills in ../examples are offered as one-click samples.
    fs: { allow: [".."] },
  },
  preview: { host: "127.0.0.1", port: 4173, strictPort: true, proxy: api },
  test: {
    environment: "jsdom",
    globals: true,
    restoreMocks: true,
  },
});
