import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig, searchForWorkspaceRoot } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const RUNBOOKS = fileURLToPath(new URL("../argus/runbooks", import.meta.url));

// ACR-0011: in production the edge (argus-v18-ui) serves /runbooks/ after login. The dev server and `vite preview`
// serve the same paths from the repository so a real-mode run (VITE_ARGUS_MOCK=0) has its runbooks too. Local only:
// no token check here; the edge's check is in deploy/ui/nginx (tests/test_acr0011_ui_edge.py).
function localRunbooks() {
  const serve = (req, res, next) => {
    const m = /^\/runbooks\/(index\.json|RB-\d+[\w.-]*\.md)$/.exec((req.url ?? "").split("?")[0]);
    if (!m) return next();
    const files = readdirSync(RUNBOOKS).filter((f) => /^RB-\d+.*\.md$/.test(f)).sort();
    if (m[1] === "index.json") {
      res.setHeader("Content-Type", "application/json");
      return res.end(JSON.stringify(files));
    }
    if (!files.includes(m[1])) return next();
    res.setHeader("Content-Type", "text/markdown; charset=utf-8");
    return res.end(readFileSync(`${RUNBOOKS}/${m[1]}`));
  };
  return {
    name: "argus-local-runbooks",
    configureServer: (server) => { server.middlewares.use(serve); },
    configurePreviewServer: (server) => { server.middlewares.use(serve); },
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), localRunbooks()],
  server: {
    // Browser -> dev server -> vm-095: no CORS on the agent, so ARGUS_UI_ORIGINS stays empty.
    // Reach the API with: ssh -L 18000:127.0.0.1:18000 argus-vm095
    proxy: { "/api": "http://127.0.0.1:18000" },
    // The dev server serves the workspace and the runbook library (argus/runbooks, read by
    // fileRunbooksAdapter.js in mock mode), resolved from this file so it does not depend on the current directory.
    fs: {
      allow: [searchForWorkspaceRoot(process.cwd()), RUNBOOKS],
    },
  },
  // OP-014 step 4: `npm test` measures coverage over every source file (not only the ones a test loads) and fails
  // under these floors, set just below the current figures (2026-10-21: lines 43.6 %). Raise them as tests are added, never
  // lower them. The pages are mostly covered by Playwright (e2e/), which this does not count.
  test: {
    coverage: {
      provider: "v8",
      include: ["src/**/*.{js,jsx}"],
      exclude: ["src/**/*.test.{js,jsx}"],
      reporter: ["text-summary"],
      thresholds: { lines: 45, statements: 44, functions: 41, branches: 44 },
    },
  },
});
