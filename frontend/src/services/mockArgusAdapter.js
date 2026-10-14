// Placeholder for the Argus API. Swap for an HTTP adapter with the same methods (services/index.js).
// Every incident call is a GET and is recorded in `calls`, so tests can assert paths such as limit=30.
import { demoEscalations, demoEvents, demoEvidence, demoIncident, demoList } from "./demoIncidents.js";
import { demoSession } from "./demoSession.js";
import { answerMetricQuestion, parseInvestigationRequest } from "./metricQuestion.js";

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

  async getHostMetrics() {
    record("/api/v1/host-metrics");
    await wait(100);
    return [
      { host: "vm-095", target: "vm-095/host:vm-095", available: true, observed_at: new Date().toISOString(),
        values: { cpu_busy_ratio: 0.25, memory_used_ratio: 0.4, disk_used_ratio: 0.7 } },
      { host: "vm-166", target: "vm-166/host:vm-166", available: true, observed_at: new Date().toISOString(),
        values: { cpu_busy_ratio: 0.8, memory_used_ratio: 0.6, disk_used_ratio: 0.9 } },
    ];
  },

  // A demo overview has illustrative metrics, identified as demo data by the Dashboard's source pill.
  async getOverview() {
    return {
      incidents: await mockArgusAdapter.listIncidents({ limit: 5 }),
      approvals: [],
      escalations: await mockArgusAdapter.listEscalations(),
      hostMetrics: await mockArgusAdapter.getHostMetrics(),
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

  // ACR-0012, demo: the targets of the demo incidents; an operator or approver "starts" one (the newest demo
  // incident stands for it), a viewer is refused as by the API.
  async listTargets() {
    record("/api/v1/targets");
    await wait(100);
    return [...new Set(demoList().map((i) => i.target))].sort().map((t) => ({ target: t, host: "demo", kind: "container", name: t }));
  },

  async startInvestigation({ target }) {
    calls.push({ method: "POST", path: "/api/v1/investigations", target });
    await wait(300);
    if (demoSession.role !== "operator" && demoSession.role !== "approver") throw httpError(403, "This role may not start investigations.");
    return { incident_id: demoList()[0].id, status: "queued", duplicate: false };
  },

  async askAgent(text, canStartInvestigation = false) {
    const investigation = parseInvestigationRequest(text);
    if (investigation) {
      if (!canStartInvestigation) return { text: "Your account cannot start investigations. You can still ask for a current host metric." };
      const { incident_id } = await mockArgusAdapter.startInvestigation({ target: investigation.target });
      return { text: `Investigation started for ${investigation.label}. Follow its result in the incident.`, incidentId: incident_id };
    }
    return { text: answerMetricQuestion(text, await mockArgusAdapter.getHostMetrics()) };
  },
  async decideApproval() {},
};
