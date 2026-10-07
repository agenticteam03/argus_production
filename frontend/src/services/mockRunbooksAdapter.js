// DEMO ONLY: reads the .md files in ./demoRunbooks (delete that folder with this adapter later).
// A real adapter must expose the same method: listRunbooks() -> [{ file, markdown }],
// e.g. GET /api/v1/runbooks returning the raw Markdown of every runbook.
const files = import.meta.glob("./demoRunbooks/*.md", { query: "?raw", import: "default", eager: true });

export const mockRunbooksAdapter = {
  async listRunbooks() {
    return Object.entries(files).map(([path, markdown]) => ({ file: path.split("/").pop(), markdown }));
  },
};
