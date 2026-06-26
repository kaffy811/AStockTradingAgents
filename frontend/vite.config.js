import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 3000,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/tests/**/*.test.js'],
  },
})
