// Placeholder for the Argus API. Swap for an HTTP adapter with the same methods (services/index.js).
// Every incident call is a GET and is recorded in `calls`, so tests can assert paths such as limit=30.
import { PHASE19_PREVIEW_ID, demoEscalations, demoEvents, demoEvidence, demoIncident, demoList, demoMetrics, demoTargetMetrics, demoTopology } from "./demoIncidents.js";
import { demoSession } from "./demoSession.js";
import { DEMO_APPROVAL_ID, demoApproval } from "./demoApproval.js";
import { demoConsoleCommands, demoConsoleExecute, demoConsoleHistory } from "./demoConsole.js";
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

  // Phases 4 and 5 (demo): the system map and an incident's metrics window (ACR-0017; routes now in
  // contracts/ui-api.json). The demo map already carries the demo incident's target, so the overlay is the same body.
  async getTopology(incidentId) {
    record(incidentId ? `/api/v1/topology?incident_id=${incidentId}` : "/api/v1/topology");
    await wait(200);
    if (incidentId === PHASE19_PREVIEW_ID && import.meta.env.VITE_ARGUS_PHASE19_DEMO === "1") return null;
    return demoTopology();
  },

  async getIncidentMetrics(id, range = "30m") {
    record(`/api/v1/incidents/${id}/metrics?range=${range}`);
    await wait(200);
    const metrics = demoMetrics(id, range);
    if (!metrics) throw httpError(404, "Incident not found");
    return metrics;
  },

  async getTargetMetrics(target, range = "15m") {
    record(`/api/v1/target-metrics?target=${encodeURIComponent(target)}&range=${range}`);
    await wait(150);
    return demoTargetMetrics(target, range);
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

  async listApprovals() {
    record("/api/v1/ops/approvals");
    if (import.meta.env.VITE_ARGUS_PHASE19_DEMO !== "1") return [];
    const a = demoApproval();
    return [{ id: a.id, incident_id: a.proposal.input.incident_id, capability: a.proposal.input.capability,
      target: a.proposal.input.target, risk: a.judge.risk, verdict: a.judge.verdict, expires_at: a.expires_at }];
  },

  // ACR-0042: the bell's count; the local preview's one synthetic approval when its flag is on
  async countWaitingApprovals() {
    record("/api/v1/approvals/waiting");
    if (demoSession.role !== "approver") throw httpError(403, "Only an approver counts the waiting approvals.");
    return { waiting: import.meta.env.VITE_ARGUS_PHASE19_DEMO === "1" ? 1 : 0 };
  },

  async getApproval(id) {
    record(`/api/v1/ops/approvals/${id}`);
    if (import.meta.env.VITE_ARGUS_PHASE19_DEMO === "1" && id === DEMO_APPROVAL_ID) return demoApproval();
    throw httpError(404, "Approval not found in this demo.");
  },

  // ACR-0034, demo: one installed source and one staged bundle, in the API's shape; the preview never installs anything.
  async listCorpusSources() {
    record("/api/v1/ops/corpus/sources");
    return [
      { name: "nginx", source: "nginx", ref: "159f0a3", licence: "BSD-2-Clause", status: "installed", passages: 845,
        quarantined: 0, at: "2026-10-27T06:10:00Z", sha256: "a".repeat(64) },
      { name: "redis", source: "redis", ref: "7.2.5", licence: "BSD-3-Clause", status: "staged", passages: 1204,
        quarantined: 2, at: "2026-10-27T07:00:00Z", sha256: "b".repeat(64) },
    ];
  },

  async approveCorpusSource() {
    throw httpError(403, "The local preview cannot install a reference source.");
  },

  async rejectCorpusSource() {
    throw httpError(403, "The local preview cannot reject a reference source.");
  },

  async answerApproval() {
    throw httpError(403, "The local preview cannot answer an approval.");
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

  // ACR-0041, demo: the escalated demo incident is closed for this session only; a viewer is refused as by the API.
  async resolveIncident(incidentId, reason) {
    calls.push({ method: "POST", path: `/api/v1/incidents/${incidentId}/resolve` });
    await wait(200);
    if (demoSession.role !== "operator" && demoSession.role !== "approver") throw httpError(403, "This role may not resolve incidents.");
    const incident = demoList().find((i) => i.id === incidentId);
    if (!incident || incident.status !== "escalated") throw httpError(409, "only an escalated incident can be resolved");
    return { ...incident, status: "closed", resolution: { by: demoSession.role, at: new Date().toISOString(), reason } };
  },

  // CON-3 (ACR-0043), demo: the operator console's private routes, scoped to the incident. Only the demo has them
  // until CON-2 adds the real routes and the contract, so a real build keeps the Console tab hidden. A viewer is refused.
  async getConsoleCommands(incidentId) {
    record(`/api/v1/ops/console/incidents/${incidentId}/commands`);
    await wait(150);
    if (demoSession.role !== "operator" && demoSession.role !== "approver") throw httpError(403, "This role may not use the console.");
    return demoConsoleCommands();
  },

  async getConsoleHistory(incidentId) {
    record(`/api/v1/ops/console/incidents/${incidentId}/history`);
    await wait(100);
    if (demoSession.role !== "operator" && demoSession.role !== "approver") throw httpError(403, "This role may not use the console.");
    return demoConsoleHistory(incidentId);
  },

  async executeConsoleCommand(incidentId, { input, confirmation, suggestion_id } = {}) {
    calls.push({ method: "POST", path: `/api/v1/ops/console/incidents/${incidentId}/execute` });
    await wait(300);
    if (demoSession.role !== "operator" && demoSession.role !== "approver") throw httpError(403, "This role may not use the console.");
    return demoConsoleExecute(incidentId, { input, confirmation, suggestion_id }, demoSession.role);
  },

  async askAgent(text, canStartInvestigation = false) {
    const investigation = parseInvestigationRequest(text);
    if (investigation) {
      if (!canStartInvestigation) return { text: "Your account cannot start investigations. You can still ask for a current host metric." };
      const { incident_id } = await mockArgusAdapter.startInvestigation({ target: investigation.target });
      return { text: `Health check queued for ${investigation.label}. If Argus finds a problem it diagnoses it; follow the result in the incident.`, incidentId: incident_id };
    }
    return { text: answerMetricQuestion(text, await mockArgusAdapter.getHostMetrics()) };
  },
  async decideApproval() {},
};
