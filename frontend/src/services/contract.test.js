import { readFileSync } from "node:fs";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { httpArgusAdapter } from "./httpArgusAdapter.js";
import { httpAuthAdapter } from "./httpAuthAdapter.js";
import { httpSecondFactorAdapter } from "./secondFactorAdapter.js";
import { clearToken } from "./session.js";

// T-0016 "Contract": every call the real adapters make is a route, method and query parameter that
// contracts/ui-api.json declares. A UI change that calls something Argus does not promise fails here, and a core
// change that removes a route the UI uses fails the API's own contract test (tests/test_ui_contract.py).
const contract = JSON.parse(readFileSync(new URL("../../../contracts/ui-api.json", import.meta.url), "utf8"));

function undeclared(calls) {
  const ops = Object.entries(contract.paths).flatMap(([path, methods]) =>
    Object.entries(methods).map(([method, op]) => ({
      re: new RegExp(`^${path.replace(/\{[^}]+\}/g, "[^/]+")}$`), method: method.toUpperCase(), path,
      query: new Set((op.parameters ?? []).filter((p) => p.in === "query").map((p) => p.name)),
    })));
  return calls.flatMap(({ method, url }) => {
    const u = new URL(url, "http://ui.local");
    const op = ops.find((o) => o.method === method && o.re.test(u.pathname));
    if (!op) return [`${method} ${u.pathname}`];
    return [...u.searchParams.keys()].filter((k) => !op.query.has(k)).map((k) => `${method} ${op.path} ?${k}`);
  });
}

describe("the real adapters against contracts/ui-api.json", () => {
  let calls;
  beforeEach(() => {
    calls = [];
    vi.stubEnv("VITE_ARGUS_INSIGHTS", "1");    // ACR-0017: the map and metrics calls are read only behind this flag
    vi.stubGlobal("fetch", vi.fn(async (url, init = {}) => {
      calls.push({ method: (init.method ?? "GET").toUpperCase(), url });
      const body = String(url).endsWith("/auth/token") ? { access: "read", access_token: "a.b.c", token_type: "bearer" }
        : String(url).endsWith("/me") ? { user: "alice", role: "operator", access: "read", actions: [] }
        : String(url).endsWith("/options") ? { challenge_id: "wch_1", options: { challenge: "AQ", user: { id: "AQ" } } } : [];
      return { ok: true, status: 200, json: async () => body };
    }));
  });
  afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); clearToken(); });

  it("call only declared routes, methods and query parameters", async () => {
    await httpAuthAdapter.signIn({ username: "alice", password: "x" });
    await httpArgusAdapter.listIncidents({ limit: 30 });
    await httpArgusAdapter.getIncident("inc_1");
    await httpArgusAdapter.getIncidentEvents("inc_1", { after: 3 });
    await httpArgusAdapter.getEvidence("ev_1");
    await httpArgusAdapter.listEscalations();
    await httpArgusAdapter.getOverview();
    await httpArgusAdapter.listTargets();                                            // ACR-0012
    await httpArgusAdapter.startInvestigation({ target: "vm-166/container:x", requestKind: "check", reason: "r" });
    await httpArgusAdapter.resolveIncident("inc_1", "fixed by hand");                // ACR-0041
    await httpArgusAdapter.countWaitingApprovals();                                  // ACR-0042: the bell
    await httpArgusAdapter.getTopology();                                            // ACR-0017: the system map
    await httpArgusAdapter.getTopology("inc_1");                                     // the incident overlay
    await httpArgusAdapter.getIncidentMetrics("inc_1", "15m");                       // the incident's metric window
    await httpArgusAdapter.getTargetMetrics("vm-166/container:argus-lab-api", "15m"); // ACR-0021: the map drawer's signals
    const key = { id: "AQ", rawId: new Uint8Array([1]), type: "public-key",                // ACR-0018 step 3
      response: { clientDataJSON: new Uint8Array([1]), attestationObject: new Uint8Array([2]),
        authenticatorData: new Uint8Array([3]), signature: new Uint8Array([4]) } };
    const keys = { create: async () => key, get: async () => key };
    await httpSecondFactorAdapter.status();
    await httpSecondFactorAdapter.credentials();
    await httpSecondFactorAdapter.enrol({ ticket: "code" }, keys);
    await httpSecondFactorAdapter.confirmLogin(keys);
    await httpSecondFactorAdapter.stepUp("test:x", keys);
    await httpAuthAdapter.signOut();                                                 // ACR-0018: ends the session
    expect(calls.length).toBeGreaterThanOrEqual(25);
    expect(undeclared(calls)).toEqual([]);
  });

  it("flags a route, a method or a query parameter the contract does not declare", () => {
    expect(undeclared([
      { method: "POST", url: "/api/v1/approvals" },
      { method: "DELETE", url: "/api/v1/incidents/inc_1" },
      { method: "GET", url: "/api/v1/incidents?offset=30" },
      { method: "GET", url: "/api/v1/incidents?limit=30" },
    ])).toEqual(["POST /api/v1/approvals", "DELETE /api/v1/incidents/inc_1", "GET /api/v1/incidents ?offset"]);
  });
});
