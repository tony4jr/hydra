import path from 'path'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react-swc'
import tailwindcss from '@tailwindcss/vite'
import { tanstackRouter } from '@tanstack/router-plugin/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    tanstackRouter({
      target: 'react',
      autoCodeSplitting: true,
    }),
    react(),
    tailwindcss(),
  ],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
      '/accounts': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/brands': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/campaigns': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/videos': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/settings': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/system': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/pools': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/logs': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/export': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
})
