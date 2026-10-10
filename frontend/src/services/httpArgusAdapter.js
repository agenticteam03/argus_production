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

  // The dashboard builds its incidents from the list; approvals and health have no route yet, so they are empty.
  async getOverview() {
    return { incidents: await httpArgusAdapter.listIncidents({ limit: 5 }), approvals: [], health: null };
  },

  // The agent chat starts an investigation, which is a write a read token never gets: it stays a placeholder
  // until the ACR that gives the UI that scope is accepted (`brain/NEXT_STEP.md`).
  async askAgent() {
    return "Argus is read-only in this release, so the chat is a placeholder. Starting an investigation needs a new ACR.";
  },

  async decideApproval() {
    throw httpError(403, "This release is read-only: the UI cannot decide approvals.");
  },
};
