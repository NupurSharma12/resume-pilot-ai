import { configDefaults, defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/testSetup.ts'],
    css: false,
    // e2e/ holds Playwright specs (*.spec.ts), a separate real-browser
    // suite with its own runner/config (playwright.config.ts) -- without
    // this, vitest's default include glob picks them up too and fails
    // immediately on Playwright-only APIs (test.describe, page fixtures).
    exclude: [...configDefaults.exclude, 'e2e/**'],
  },
})
