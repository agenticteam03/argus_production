// Placeholder for the Argus API. Swap for an HTTP adapter with the same methods (services/index.js).
// Every incident call is a GET and is recorded in `calls`, so tests can assert paths such as limit=30.
import { demoEvents, demoIncident, demoList } from "./demoIncidents.js";
import { demoSession } from "./demoSession.js";

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const httpError = (status, message) => Object.assign(new Error(message), { status });
const calls = [];
const record = (path) => calls.push({ method: "GET", path });

export const mockArgusAdapter = {
  calls,

  async listIncidents({ limit = 30 } = {}) {
    record(`/api/v1/incidents?limit=${limit}`);
    await wait(250);
    return demoList().slice(0, limit);
  },

  async getIncident(id) {
    record(`/api/v1/incidents/${id}`);
    await wait(250);
    const incident = demoIncident(id);
    if (!incident) throw httpError(404, "Incident not found");
    // Like the server: a viewer gets no evidence/audit keys at all (not empty lists).
    if (demoSession.role === "operator" || demoSession.role === "approver") return incident;
    const { evidence, audit, ...visible } = incident;
    return visible;
  },

  async getIncidentEvents(id, { after = 0 } = {}) {
    record(`/api/v1/incidents/${id}/events?after=${after}`);
    await wait(150);
    const all = demoEvents(id);
    if (!all) throw httpError(404, "Incident not found");
    return all.filter((e) => e.seq > after);
  },

  // The overview has no endpoint today (only GET /healthz): incidents come from the list, health stays "No data".
  async getOverview() {
    return {
      incidents: await mockArgusAdapter.listIncidents({ limit: 5 }),
      approvals: [],
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
