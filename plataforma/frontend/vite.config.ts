import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Em desenvolvimento o Vite roda separado e repassa /api para o backend (seção 4).
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": { target: "http://localhost:8000", changeOrigin: true },
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Bibliotecas grandes em arquivos próprios: mudam pouco e ficam em cache.
        manualChunks: {
          graficos: ["recharts"],
          react: ["react", "react-dom", "react-router-dom"],
        },
      },
    },
  },
  test: {
    environment: "node",
  },
});
