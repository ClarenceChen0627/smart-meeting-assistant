import { defineConfig } from 'vite'
import path from 'path'
import { fileURLToPath } from 'url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const devProxyTarget = process.env.SMART_MEETING_DEV_PROXY_TARGET || 'http://localhost:8080'


function localAssetResolver() {
  return {
    name: 'local-asset-resolver',
    resolveId(id: string) {
      if (id.startsWith('figma:asset/')) {
        const filename = id.replace('figma:asset/', '')
        return path.resolve(__dirname, 'src/assets', filename)
      }
    },
  }
}

export default defineConfig({
  base: './',
  plugins: [
    localAssetResolver(),
    // The React and Tailwind plugins are both required by the Vite UI setup.
    react(),
    tailwindcss(),
  ],
  resolve: {
    alias: {
      // Alias @ to the src directory
      '@': path.resolve(__dirname, './src'),
    },
  },

  server: {
    proxy: {
      '/api': {
        target: devProxyTarget,
        changeOrigin: true,
      },
      '/ws': {
        target: devProxyTarget,
        changeOrigin: true,
        ws: true,
      },
    },
  },

  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return
          }

          if (id.includes('recharts') || id.includes('d3-') || id.includes('victory-vendor')) {
            return 'charts'
          }

          if (id.includes('lucide-react')) {
            return 'icons'
          }

          if (id.includes('@radix-ui')) {
            return 'radix-ui'
          }

          return 'vendor'
        },
      },
    },
  },

  // File types to support raw imports. Never add .css, .tsx, or .ts files to this.
  assetsInclude: ['**/*.svg', '**/*.csv'],
})
