import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Served at the site root behind Apache; the API lives under /api.
export default defineConfig({
  base: '/',
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8501',
    },
  },
})
