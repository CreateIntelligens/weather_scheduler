import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const allowedHosts = env.VITE_ALLOWED_HOSTS
    ? env.VITE_ALLOWED_HOSTS.split(',').map((host) => host.trim()).filter(Boolean)
    : []

  return {
    plugins: [react()],
    server: {
      host: true, // 監聽所有 IP，這對 Docker 很重要
      port: Number(env.VITE_PORT || 5175),
      allowedHosts,
      proxy: {
        '/api': {
          target: env.VITE_API_PROXY_TARGET || 'http://weather-backend:8000',
          changeOrigin: true,
          secure: false,
        },
      },
      watch: {
          usePolling: true // 在某些 Docker 環境下需要這個來確保熱重載正常
      }
    }
  }
})
