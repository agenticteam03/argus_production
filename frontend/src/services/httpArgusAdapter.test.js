import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import events from "../../../contracts/samples/events.json";
import incident from "../../../contracts/samples/incident.json";
import incidents from "../../../contracts/samples/incidents.json";
import { httpArgusAdapter } from "./httpArgusAdapter.js";
import { clearToken, getToken, setToken } from "./session.js";

const response = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
});

describe("httpArgusAdapter", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn();
    setToken("jwt-123");
  });
  afterEach(() => {
    clearToken();
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

  it("builds the dashboard overview from the incident list; approvals and health have no route", async () => {
    fetch.mockResolvedValueOnce(response(200, incidents));

    const overview = await httpArgusAdapter.getOverview();

    expect(fetch.mock.calls[0][0]).toBe("/api/v1/incidents?limit=5");
    expect(overview.incidents).toEqual(incidents);
    expect(overview.approvals).toEqual([]);
    expect(overview.health).toBeNull();
  });

  it("on 401 it forgets the token and rejects", async () => {
    fetch.mockResolvedValueOnce(response(401, {}));

    await expect(httpArgusAdapter.listIncidents()).rejects.toMatchObject({ status: 401 });
    expect(getToken()).toBeNull();
  });

  it("turns a 404 into a not-found error", async () => {
    fetch.mockResolvedValueOnce(response(404, {}));

    await expect(httpArgusAdapter.getIncident("nope")).rejects.toMatchObject({ status: 404 });
  });

  it("rejects the placeholder write call: this release is read-only", async () => {
    await expect(httpArgusAdapter.decideApproval("a1", "approve")).rejects.toMatchObject({ status: 403 });
  });
});
