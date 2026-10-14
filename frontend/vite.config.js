import { fileURLToPath } from "node:url";
import { defineConfig, searchForWorkspaceRoot } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Browser -> dev server -> vm-095: no CORS on the agent, so ARGUS_UI_ORIGINS stays empty.
    // Reach the API with: ssh -L 18000:127.0.0.1:18000 argus-vm095
    proxy: { "/api": "http://127.0.0.1:18000" },
    // The dev server serves the workspace and the runbook library (argus/runbooks, read by
    // fileRunbooksAdapter.js), resolved from this file so it does not depend on the current directory.
    fs: {
      allow: [
        searchForWorkspaceRoot(process.cwd()),
        fileURLToPath(new URL("../argus/runbooks", import.meta.url)),
      ],
    },
  },
});
