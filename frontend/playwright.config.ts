import { defineConfig, devices } from '@playwright/test'

// A separate, real-browser layer on top of the vitest unit suite (see
// vite.config.ts) -- this drives the actual running frontend + backend
// over HTTP/DOM, the same way a real user would, rather than importing
// React components directly. See e2e/README.md for how deterministic vs.
// live specs are split, and why.
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  // Live specs (golden-path, downloads) call a real LLM provider chain --
  // one worker avoids piling up concurrent conversations/generations
  // against the same backend process and keeps output easier to read
  // locally. Deterministic specs are fast either way.
  workers: 1,
  reporter: [['list'], ['html', { open: 'never' }]],

  use: {
    baseURL: 'http://localhost:5173',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    // Opt-in slow motion for watching a run with your own eyes -- e.g.
    // `SLOW_MO=300 npx playwright test comparator.spec.ts --headed`.
    // There's no `--slowMo` CLI flag for `playwright test` (only for
    // some standalone Playwright scripts), so this is the actual way to
    // get it. Off by default: 0ms adds no delay, keeping normal/CI runs
    // at full speed.
    launchOptions: {
      slowMo: process.env.SLOW_MO ? Number(process.env.SLOW_MO) : 0,
    },
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  // Reuses whatever's already running locally (both dev servers are
  // typically already up during development) -- only actually launches
  // its own server in a clean environment (e.g. CI). `stdout: 'pipe'`
  // keeps server logs out of the test report; run with DEBUG=pw:webserver
  // to see them if a server fails to start.
  webServer: [
    {
      command: 'npm run dev -- --port 5173 --strictPort',
      url: 'http://localhost:5173',
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: 'uv run uvicorn app.app:app --host 0.0.0.0 --port 8000',
      cwd: '..',
      url: 'http://localhost:8000/v1/health',
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
})
