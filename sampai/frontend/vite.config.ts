import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// Dev server proxies /api to the host-run LightRAG server so the SPA and API
// share an origin (no CORS in dev). Override the target with VITE_API_TARGET.
const API_TARGET = process.env.VITE_API_TARGET || 'http://localhost:9621'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
