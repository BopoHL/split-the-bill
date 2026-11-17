import { defineConfig } from 'vitest/config';
import path from 'node:path';

// Minimal vitest setup for the project. Uses jsdom for component tests,
// the dot reporter to keep CI / agent output small, and a single setup
// file that wires up @testing-library/jest-dom matchers.
//
// TZ is pinned to UTC because the relative-date helpers compare calendar days.
// The fixtures are written in UTC, so on a UTC+5 machine they land on the next
// calendar day and the suite fails for reasons unrelated to the code — green in
// CI (UTC runners), red locally. Pinning makes both agree.
process.env.TZ = 'UTC';

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    css: false,
    reporters: ['dot'],
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
});
