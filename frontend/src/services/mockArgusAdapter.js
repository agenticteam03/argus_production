// Placeholder for the Argus API. Swap for an HTTP/SSE adapter with the same methods:
// GET /api/v1/incidents, GET /api/v1/approvals/pending, POST /api/v1/investigations,
// POST /api/v1/incidents/{id}/approve|deny. Everything is empty until then.
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export const mockArgusAdapter = {
  async getOverview() {
    return {
      incidents: [], // { id, target, title, status, trigger: "alert|scheduled|manual", severity, createdAt }
      approvals: [], // { id, action, target, expiresAt }
      health: { wireguard: null, prometheus: null, tokens: { used: null, limit: null }, resolvedToday: null },
    };
  },
  async askAgent(text, onStatus) {
    for (const step of ["Analyzing Prometheus metrics…", "Querying incident history…"]) {
      onStatus(step);
      await wait(900);
    }
    return "The backend isn't connected yet, so this is a placeholder reply. Once the API is wired up, Argus will answer here.";
  },
  async decideApproval() {},
};
