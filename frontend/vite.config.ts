import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Forward API calls to the Flask backend so the browser sees one origin (no CORS in dev).
    proxy: {
      '/api': process.env.API_PROXY_TARGET ?? 'http://127.0.0.1:5000',
    },
  },
})
