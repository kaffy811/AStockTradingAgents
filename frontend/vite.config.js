import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/echarts') || id.includes('node_modules/zrender')) {
            return 'echarts'
          }
          if (id.includes('node_modules/xlsx')) {
            return 'xlsx'
          }
          // Keep vue ecosystem together
          if (id.includes('node_modules/vue') || id.includes('node_modules/@vue')) {
            return 'vue-vendor'
          }
        }
      }
    }
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/tests/**/*.test.js'],
  },
})
