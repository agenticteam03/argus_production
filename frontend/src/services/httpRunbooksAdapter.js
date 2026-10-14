// The runbook library in real mode (ACR-0011 §3.1 row 9): not in the bundle. The public edge (argus-v18-ui) serves
// /runbooks/index.json and /runbooks/RB-*.md only to a request whose bearer token passes GET /api/v1/me, so the UI
// loads them after login, with the same token and the same 401 handling as the API (apiFetch). In development and
// `vite preview`, vite.config.js serves the same paths from argus/runbooks.
import { apiFetch } from "./http.js";

const RUNBOOK_FILE = /^RB-\d+[\w.-]*\.md$/;          // a file name of the library, never a path

export const httpRunbooksAdapter = {
  pollMs: 0,                                          // the library changes with a deployment: load once
  async listRunbooks() {
    const index = await (await apiFetch("/runbooks/index.json")).json();
    const files = (Array.isArray(index) ? index : []).filter((f) => typeof f === "string" && RUNBOOK_FILE.test(f));
    return Promise.all(files.map(async (file) => ({ file, markdown: await (await apiFetch(`/runbooks/${file}`)).text() })));
  },
};
