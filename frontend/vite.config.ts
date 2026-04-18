import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, '')
  const apiBaseUrl = env.VITE_API_BASE_URL || 'http://localhost:8080'
  const wsBaseUrl = env.VITE_WS_BASE_URL || 'ws://localhost:8080'
  const allowedHosts = [
    'localhost',
    '127.0.0.1',
    '.run.pinggy-free.link',
    '.loca.lt',
    '.trycloudflare.com'
  ]

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': resolve(__dirname, 'src')
      }
    },
    server: {
      port: 3000,
      host: '0.0.0.0',
      allowedHosts,
      proxy: {
        '/api': {
          target: apiBaseUrl,
          changeOrigin: true
        },
        '/ws': {
          target: wsBaseUrl,
          ws: true
        }
      }
    }
  }
})
