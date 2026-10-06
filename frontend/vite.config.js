import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: {
    // jsdom, not happy-dom: these tests exercise localStorage, cookies and
    // Intl number formatting, and jsdom's implementations are the ones that
    // match real browser behaviour most closely.
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    css: false,
    coverage: {
      provider: 'v8',
      reportsDirectory: './coverage',
      // Deliberately not enforcing a coverage threshold yet. A number picked
      // before the suite exists just gets lowered the first time it fails,
      // which teaches everyone to ignore it. Set one once real coverage is
      // measured (Phase 41).
      exclude: ['src/main.jsx', 'src/test/**', '**/*.config.js'],
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/health': { target: 'http://localhost:8000', changeOrigin: true }
    }
  }
})
