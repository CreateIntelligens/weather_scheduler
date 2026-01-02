import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // 監聽所有 IP，這對 Docker 很重要
    port: 5173,
    watch: {
        usePolling: true // 在某些 Docker 環境下需要這個來確保熱重載正常
    }
  }
})