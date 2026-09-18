import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Las rutas mas especificas van primero: /api/v1/sagas debe resolverse contra
// el saga-service antes de que /api caiga en el Gateway.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api/v1/sagas": { target: "http://localhost:8004", changeOrigin: true },
      "/accounts": { target: "http://localhost:8001", changeOrigin: true },
      "/api": { target: "http://localhost:8000", changeOrigin: true },
      "/health": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
});
