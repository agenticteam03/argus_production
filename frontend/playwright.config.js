import { defineConfig, devices } from "@playwright/test";

// T-0016: acceptance tests against the BUILT app in real mode (VITE_ARGUS_MOCK=0), served by `vite preview`. The
// Argus API is faked in the browser from contracts/samples/*.json (e2e/fixtures.js), so no server and no VM are
// needed, and every test also runs the read-only network guard.
const PORT = 4179;

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.e2e.js",          // not *.test.js / *.spec.js: Vitest must not pick these up
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `npx vite build --outDir dist-e2e --emptyOutDir && npx vite preview --outDir dist-e2e --port ${PORT} --strictPort --host 127.0.0.1`,
    env: { VITE_ARGUS_MOCK: "0" },
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
