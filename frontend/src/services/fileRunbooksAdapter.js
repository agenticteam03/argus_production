// Mock mode only: the runbook library of the repository (`argus/runbooks/`, 21 runbooks) compiled into the demo
// bundle. A real build drops this module (package.json "sideEffects"); httpRunbooksAdapter.js loads the library
// from the edge after login (ACR-0011). Same method: listRunbooks() -> [{ file, markdown }].
const files = import.meta.glob("../../../argus/runbooks/RB-*.md", { query: "?raw", import: "default", eager: true });

export const fileRunbooksAdapter = {
  pollMs: 10_000,                       // a .md edited during `npm run dev` shows up on its own
  async listRunbooks() {
    return Object.entries(files).map(([path, markdown]) => ({ file: path.split("/").pop(), markdown }));
  },
};
