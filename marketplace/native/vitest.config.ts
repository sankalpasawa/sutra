import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    include: ['tests/**/*.test.ts'],
    globals: true,
    environment: 'node',
    coverage: {
      reporter: ['text', 'json', 'html'],
      thresholds: { lines: 80, functions: 80, branches: 80, statements: 80 }
    }
  }
})
