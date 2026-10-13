// Placeholder for the Argus API. Swap for an HTTP adapter with the same methods (services/index.js).
// Every incident call is a GET and is recorded in `calls`, so tests can assert paths such as limit=30.
import { demoEscalations, demoEvents, demoEvidence, demoIncident, demoList } from "./demoIncidents.js";
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

  // The overview builds its incidents from the list, escalations from their route; approvals and health have
  // no endpoint today, so they stay empty ("No data").
  async getOverview() {
    return {
      incidents: await mockArgusAdapter.listIncidents({ limit: 5 }),
      approvals: [],
      escalations: await mockArgusAdapter.listEscalations(),
      health: { wireguard: null, prometheus: null, tokens: { used: null, limit: null }, resolvedToday: null },
    };
  },

  async listEscalations() {
    record("/api/v1/escalations");
    await wait(200);
    return demoEscalations();
  },

  // Like the server: only operator/approver may read one evidence record (GET /api/v1/evidence/{id}).
  async getEvidence(id) {
    record(`/api/v1/evidence/${id}`);
    await wait(150);
    if (demoSession.role !== "operator" && demoSession.role !== "approver") throw httpError(403, "This role may not read evidence.");
    const found = demoEvidence(id);
    if (!found) throw httpError(404, "Evidence not found");
    return found;
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
