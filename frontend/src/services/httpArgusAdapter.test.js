import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import escalations from "../../../contracts/samples/escalations.json";
import evidence from "../../../contracts/samples/evidence.json";
import events from "../../../contracts/samples/events.json";
import incident from "../../../contracts/samples/incident.json";
import incidents from "../../../contracts/samples/incidents.json";
import hostMetrics from "../../../contracts/samples/host-metrics.json";
import { httpArgusAdapter } from "./httpArgusAdapter.js";
import { clearToken, getToken, setToken } from "./session.js";
import { clearSession, loadSession, saveSession } from "./sessionStore.js";

const response = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
});

// Node has no sessionStorage; a tiny fake lets the 401 path clear a persisted session for real.
const stubStorage = () => {
  const mem = new Map();
  globalThis.sessionStorage = {
    getItem: (k) => (mem.has(k) ? mem.get(k) : null),
    setItem: (k, v) => mem.set(k, String(v)),
    removeItem: (k) => mem.delete(k),
  };
};

describe("httpArgusAdapter", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn();
    setToken("jwt-123");
    stubStorage();
  });
  afterEach(() => {
    clearToken();
    clearSession();
    delete globalThis.sessionStorage;
    vi.restoreAllMocks();
  });

  it("lists incidents with the limit and the bearer token", async () => {
    fetch.mockResolvedValueOnce(response(200, incidents));

    const rows = await httpArgusAdapter.listIncidents({ limit: 30 });

    expect(fetch.mock.calls[0][0]).toBe("/api/v1/incidents?limit=30");
    expect(fetch.mock.calls[0][1].headers.Authorization).toBe("Bearer jwt-123");
    expect(rows).toEqual(incidents);
  });

  it("reads one incident (contract sample) and its events with the after cursor", async () => {
    fetch.mockResolvedValueOnce(response(200, incident)).mockResolvedValueOnce(response(200, events));

    const one = await httpArgusAdapter.getIncident("inc_7e49840f50fa");
    const batch = await httpArgusAdapter.getIncidentEvents("inc_7e49840f50fa", { after: 5 });

    expect(fetch.mock.calls[0][0]).toBe("/api/v1/incidents/inc_7e49840f50fa");
    expect(fetch.mock.calls[1][0]).toBe("/api/v1/incidents/inc_7e49840f50fa/events?after=5");
    expect(one.incident_class).toBe("container_restart_loop");
    expect(Array.isArray(batch)).toBe(true);
  });

  it("reads one evidence record and lists escalations", async () => {
    fetch.mockResolvedValueOnce(response(200, evidence)).mockResolvedValueOnce(response(200, escalations));

    const one = await httpArgusAdapter.getEvidence("ev_f5de798421654c48");
    const raised = await httpArgusAdapter.listEscalations();

    expect(fetch.mock.calls[0][0]).toBe("/api/v1/evidence/ev_f5de798421654c48");
    expect(fetch.mock.calls[1][0]).toBe("/api/v1/escalations");
    expect(one.evidence_id).toBe("ev_f5de798421654c48");
    expect(raised).toEqual(escalations);
  });

  it("builds the dashboard overview with live host metrics", async () => {
    fetch.mockResolvedValueOnce(response(200, incidents)).mockResolvedValueOnce(response(200, escalations))
      .mockResolvedValueOnce(response(200, hostMetrics));

    const overview = await httpArgusAdapter.getOverview();

    expect(fetch.mock.calls[0][0]).toBe("/api/v1/incidents?limit=5");
    expect(fetch.mock.calls[1][0]).toBe("/api/v1/escalations");
    expect(fetch.mock.calls[2][0]).toBe("/api/v1/host-metrics");
    expect(overview.incidents).toEqual(incidents);
    expect(overview.escalations).toEqual(escalations);
    expect(overview.approvals).toEqual([]);
    expect(overview.hostMetrics).toEqual(hostMetrics);
  });

  it("keeps incidents and escalations when the host metrics read fails", async () => {
    fetch.mockResolvedValueOnce(response(200, incidents)).mockResolvedValueOnce(response(200, escalations))
      .mockResolvedValueOnce(response(504, {}));

    const overview = await httpArgusAdapter.getOverview();

    expect(overview.incidents).toEqual(incidents);
    expect(overview.escalations).toEqual(escalations);
    expect(overview.hostMetrics).toEqual([]);
  });

  it("still fails the overview when incidents cannot be read", async () => {
    fetch.mockResolvedValueOnce(response(500, {})).mockResolvedValueOnce(response(200, escalations))
      .mockResolvedValueOnce(response(200, hostMetrics));

    await expect(httpArgusAdapter.getOverview()).rejects.toMatchObject({ status: 500 });
  });

  it("answers a supported metric question from live readings", async () => {
    fetch.mockResolvedValueOnce(response(200, hostMetrics));
    const answer = await httpArgusAdapter.askAgent("Check Host T memory usage");
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/host-metrics");
    expect(answer.text).toContain("memory usage");
  });

  it("starts a bounded host investigation only for an authorized chat session", async () => {
    expect((await httpArgusAdapter.askAgent("Investigate Host T", false)).incidentId).toBeUndefined();
    expect(fetch).not.toHaveBeenCalled();
    fetch.mockResolvedValueOnce(response(202, { incident_id: "inc_123" }));
    const reply = await httpArgusAdapter.askAgent("Investigate Host T", true);
    expect(reply.incidentId).toBe("inc_123");
    expect(reply.text).toMatch(/^Health check queued for Host T/);
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/investigations");
    expect(JSON.parse(fetch.mock.calls[0][1].body)).toMatchObject({ target: "vm-166/host:vm-166", request_kind: "check" });
  });

  it("on 401 it forgets the token and the persisted session", async () => {
    saveSession({ user: { name: "ana", role: "operator" }, token: "jwt-123" });
    fetch.mockResolvedValueOnce(response(401, {}));

    await expect(httpArgusAdapter.listIncidents()).rejects.toMatchObject({ status: 401 });
    expect(getToken()).toBeNull();
    expect(loadSession()).toBeNull();
  });

  it("turns a 404 into a not-found error", async () => {
    fetch.mockResolvedValueOnce(response(404, {}));

    await expect(httpArgusAdapter.getIncident("nope")).rejects.toMatchObject({ status: 404 });
  });

  it("rejects the placeholder write call: this release is read-only", async () => {
    await expect(httpArgusAdapter.decideApproval("a1", "approve")).rejects.toMatchObject({ status: 403 });
  });
});
