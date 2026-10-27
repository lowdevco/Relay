import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const backend = process.env.VITE_BACKEND_URL || 'http://localhost:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    // Lets an ngrok tunnel on 5173 serve the app; any *.ngrok-free.dev name works after a tunnel change.
    allowedHosts: ['.ngrok-free.dev'],
    // Same-origin API: session cookie + CSRF, nothing secret in browser storage.
    proxy: { '/api': { target: backend, changeOrigin: false } },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
  },
})
