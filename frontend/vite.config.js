import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server runs on 5173 and proxies /api/* to the FastAPI backend on 8000.
// This way the frontend never needs to know the backend's absolute URL — it
// just hits /api/login, /api/chat/stream, etc., and Vite forwards the request.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
