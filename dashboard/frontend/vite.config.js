import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Served behind Apache at /status, so all assets are prefixed.
export default defineConfig({
  base: '/status/',
  plugins: [react()],
  server: {
    proxy: {
      '/status/api': 'http://localhost:8501',
    },
  },
})
