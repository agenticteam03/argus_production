// The read-only HTTP adapter for the Argus API. Only the routes in `docs/API-FOR-UI.md` are used,
// and the token (scope=read) only allows GETs. `apiFetch` logs the session out on any 401.
// Approvals and agent actions are writes: they have no route a read token may call, so they stay placeholders.
import { apiFetch, httpError } from "./http.js";

const getJson = async (path) => (await apiFetch(path)).json();

export const httpArgusAdapter = {
  async listIncidents({ limit = 30 } = {}) {
    return getJson(`/api/v1/incidents?limit=${limit}`);
  },

  async getIncident(id) {
    return getJson(`/api/v1/incidents/${id}`);
  },

  async getIncidentEvents(id, { after = 0 } = {}) {
    return getJson(`/api/v1/incidents/${id}/events?after=${after}`);
  },

  async getEvidence(id) {
    return getJson(`/api/v1/evidence/${encodeURIComponent(id)}`);
  },

  async listEscalations() {
    return getJson("/api/v1/escalations");
  },

  // The dashboard builds its incidents from the list and its escalations from their route;
  // approvals are writes and health has no route yet, so they stay empty.
  async getOverview() {
    const [incidents, escalations] = await Promise.all([
      httpArgusAdapter.listIncidents({ limit: 5 }),
      httpArgusAdapter.listEscalations(),
    ]);
    return { incidents, approvals: [], escalations, health: null };
  },

  // ACR-0012: the targets a UI may name (the inventory's refs), and the one write an investigate token may do.
  async listTargets() {
    return getJson("/api/v1/targets");
  },

  async startInvestigation({ target, requestKind = "report", reason = "" }) {
    const res = await apiFetch("/api/v1/investigations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target, request_kind: requestKind, reason }),
    });
    return res.json();
  },

  // The agent chat starts an investigation, which is a write a read token never gets: it stays a placeholder
  // until the ACR that gives the UI that scope is accepted (`brain/NEXT_STEP.md`).
  async askAgent() {
    return "The chat is a placeholder: Argus does not answer free-text questions yet. To start an investigation, use \"Start an investigation\" below.";
  },

  async decideApproval() {
    throw httpError(403, "This release is read-only: the UI cannot decide approvals.");
  },
};
