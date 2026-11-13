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
        // React em arquivo próprio: muda pouco e fica em cache entre versões do painel.
        // O resto (gráficos, formulários, tabelas, calendário) já vai em arquivos separados
        // porque as telas e o gráfico do Início são carregados sob demanda.
        manualChunks: {
          react: ["react", "react-dom", "react-dom/client", "react-router-dom"],
        },
      },
    },
  },
  test: {
    environment: "node",
  },
});
