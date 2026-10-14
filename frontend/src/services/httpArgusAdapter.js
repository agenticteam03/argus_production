// The HTTP adapter for the UI contract. An investigate token permits GETs and the one bounded investigation POST.
// `apiFetch` logs the session out on any 401; approvals still have no UI route.
import { apiFetch, httpError } from "./http.js";
import { answerMetricQuestion, parseInvestigationRequest, parseMetricQuestion } from "./metricQuestion.js";

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

  async getHostMetrics() {
    return getJson("/api/v1/host-metrics");
  },

  // The dashboard reads only the named host metrics in the UI contract. Approvals have no read route yet.
  // A failed metrics read (slow or down Prometheus) leaves the card empty; it never hides incidents and escalations.
  async getOverview() {
    const [incidents, escalations, metrics] = await Promise.allSettled([
      httpArgusAdapter.listIncidents({ limit: 5 }),
      httpArgusAdapter.listEscalations(),
      httpArgusAdapter.getHostMetrics(),
    ]);
    for (const result of [incidents, escalations]) if (result.status === "rejected") throw result.reason;
    if (metrics.status === "rejected" && metrics.reason?.status === 401) throw metrics.reason;
    const hostMetrics = metrics.status === "fulfilled" ? metrics.value : [];
    return { incidents: incidents.value, approvals: [], escalations: escalations.value, hostMetrics };
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

  async askAgent(question, canStartInvestigation = false) {
    const investigation = parseInvestigationRequest(question);
    if (investigation) {
      if (!canStartInvestigation) return { text: "Your account cannot start investigations. You can still ask for a current host metric." };
      const { incident_id } = await httpArgusAdapter.startInvestigation({ target: investigation.target,
        requestKind: "check", reason: question.slice(0, 500) });
      // ACR-0014: a `check` ("is it healthy?"); with no matching symptom it ends quietly as no_incident.
      return { text: `Health check queued for ${investigation.label}. If Argus finds a problem it diagnoses it; follow the result in the incident.`, incidentId: incident_id };
    }
    if (!parseMetricQuestion(question)) return { text: answerMetricQuestion(question, []) };
    return { text: answerMetricQuestion(question, await httpArgusAdapter.getHostMetrics()) };
  },

  async decideApproval() {
    throw httpError(403, "This release is read-only: the UI cannot decide approvals.");
  },
};
