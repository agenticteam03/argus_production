// Reads the real runbook library in the repository (`argus/runbooks/`, 21 runbooks). There is no API route
// for runbooks in the UI contract yet, so the app reads the Markdown that ships with the code.
// A future HTTP adapter must expose the same method: listRunbooks() -> [{ file, markdown }].
// The dev server needs `server.fs.allow: [".."]` (vite.config.js) to serve files outside `frontend/`.
const files = import.meta.glob("../../../argus/runbooks/RB-*.md", { query: "?raw", import: "default", eager: true });

export const fileRunbooksAdapter = {
  async listRunbooks() {
    return Object.entries(files).map(([path, markdown]) => ({ file: path.split("/").pop(), markdown }));
  },
};
