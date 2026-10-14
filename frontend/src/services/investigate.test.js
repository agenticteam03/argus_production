import { afterEach, describe, expect, it, vi } from "vitest";
import { demoSession } from "./demoSession.js";
import { httpArgusAdapter } from "./httpArgusAdapter.js";
import { mockArgusAdapter } from "./mockArgusAdapter.js";
import { clearToken, setToken } from "./session.js";

// ACR-0012: the UI may start an investigation. The real adapter lists the targets and posts one investigation with
// the session's investigate token; a quota answer (429) carries how long to wait.
const json = (status, body, headers = {}) => ({
  ok: status < 400, status, json: async () => body,
  headers: { get: (k) => headers[k.toLowerCase()] ?? null },
});

describe("httpArgusAdapter: investigations (ACR-0012)", () => {
  afterEach(() => { vi.unstubAllGlobals(); clearToken(); });

  it("lists the targets", async () => {
    setToken("tok");
    const fetch = vi.fn(async () => json(200, [{ target: "vm-166/container:argus-lab-api", host: "vm-166", kind: "container", name: "argus-lab-api" }]));
    vi.stubGlobal("fetch", fetch);
    const rows = await httpArgusAdapter.listTargets();
    expect(rows[0].target).toBe("vm-166/container:argus-lab-api");
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/targets");
  });

  it("posts one investigation as JSON with the token and returns the new incident", async () => {
    setToken("tok");
    const fetch = vi.fn(async () => json(202, { incident_id: "inc_new", status: "queued", duplicate: false }));
    vi.stubGlobal("fetch", fetch);
    const r = await httpArgusAdapter.startInvestigation({ target: "vm-166/container:argus-lab-api", requestKind: "check", reason: "slow" });
    expect(r.incident_id).toBe("inc_new");
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("/api/v1/investigations");
    expect(init.method).toBe("POST");
    expect(init.headers.Authorization).toBe("Bearer tok");
    expect(init.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(init.body)).toEqual({ target: "vm-166/container:argus-lab-api", request_kind: "check", reason: "slow" });
  });

  it("a quota answer says how long to wait", async () => {
    setToken("tok");
    vi.stubGlobal("fetch", vi.fn(async () => json(429, { detail: "investigation quota reached (per_hour)" }, { "retry-after": "120" })));
    await expect(httpArgusAdapter.startInvestigation({ target: "t", requestKind: "report", reason: "" }))
      .rejects.toMatchObject({ status: 429, retryAfter: 120 });
  });
});

describe("mockArgusAdapter: investigations (demo)", () => {
  afterEach(() => { demoSession.role = null; });

  it("lists demo targets and starts a demo investigation for an operator", async () => {
    demoSession.role = "operator";
    const targets = await mockArgusAdapter.listTargets();
    expect(targets.length).toBeGreaterThan(0);
    const r = await mockArgusAdapter.startInvestigation({ target: targets[0].target, requestKind: "check", reason: "" });
    expect(typeof r.incident_id).toBe("string");
    expect(r.incident_id.length).toBeGreaterThan(0);
  });

  it("refuses a viewer, as the API would", async () => {
    demoSession.role = "viewer";
    await expect(mockArgusAdapter.startInvestigation({ target: "t", requestKind: "check", reason: "" }))
      .rejects.toMatchObject({ status: 403 });
  });
});
