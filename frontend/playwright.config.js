import { defineConfig, devices } from "@playwright/test";

// T-0016: acceptance tests against the BUILT app in real mode (VITE_ARGUS_MOCK=0), served by `vite preview`. The
// Argus API is faked in the browser from contracts/samples/*.json (e2e/fixtures.js), so no server and no VM are
// needed, and every test also runs the read-only network guard.
const PORT = 4179;
const CONSOLE_PORT = 4180;     // T-0016: a second build with the operator console's flag, for console-dock.e2e.js
const server = (port, outDir, env) => ({
  command: `npx vite build --outDir ${outDir} --emptyOutDir && npx vite preview --outDir ${outDir} --port ${port} --strictPort --host 127.0.0.1`,
  env, url: `http://127.0.0.1:${port}`, reuseExistingServer: !process.env.CI, timeout: 120_000,
});

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
    timezoneId: "America/Bogota",   // the UI shows the browser's zone; pin it so the zone label (COT) is stable
  },
  projects: [
    { name: "chromium", testIgnore: "**/console-dock.e2e.js", use: { ...devices["Desktop Chrome"] } },
    { name: "console", testMatch: "**/console-dock.e2e.js",
      use: { ...devices["Desktop Chrome"], baseURL: `http://127.0.0.1:${CONSOLE_PORT}`, viewport: { width: 1280, height: 800 } } },
  ],
  webServer: [
    server(PORT, "dist-e2e", { VITE_ARGUS_MOCK: "0", VITE_ARGUS_INSIGHTS: "1" }),   // ACR-0017: map and metrics calls in
    server(CONSOLE_PORT, "dist-e2e-console", { VITE_ARGUS_MOCK: "0", VITE_ARGUS_INSIGHTS: "1", VITE_ARGUS_CONSOLE: "1" }),
  ],
});
