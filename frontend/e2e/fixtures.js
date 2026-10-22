// The fake Argus API and the read-only network guard shared by every acceptance test (T-0016).
//
// Fake API: answers in the browser (page.route) from contracts/samples/*.json, the real responses recorded by the
// contract test, so a UI test and the API's contract test read the same bodies.
//
// Read-only guard: records every request the page makes. A test fails if the app sends anything to the API except a
// GET or the login POST, or talks to any other origin. ACR-0001: a read-only UI never starts, approves or changes
// anything.
import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test as base, expect } from "@playwright/test";

const SAMPLES = fileURLToPath(new URL("../../contracts/samples/", import.meta.url));
const RUNBOOKS = fileURLToPath(new URL("../../argus/runbooks/", import.meta.url));
const RUNBOOK_FILES = readdirSync(RUNBOOKS).filter((f) => /^RB-\d+.*\.md$/.test(f)).sort();
export const sample = (name) => JSON.parse(readFileSync(`${SAMPLES}${name}.json`, "utf8"));

export const PASSWORD = "right-password";
export const DIAGNOSED_ID = sample("incident").id;          // the sample's diagnosed incident

// A token whose payload has an `exp` one hour ahead, so the session store keeps it (sessionStore.tokenExpiry).
const b64 = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
const TOKEN = `${b64({ alg: "HS256" })}.${b64({ sub: "alice", access: "investigate", exp: Math.floor(Date.now() / 1000) + 3600 })}.sig`;

// What the UI may send to the API: any GET and the login; plus (ACR-0012) the one POST that starts an investigation,
// but only for a session whose /me lists start_investigation.
const allowed = (method, path, { investigate = false } = {}) => method === "GET"
  || (method === "POST" && path === "/api/v1/auth/token")
  || (investigate && method === "POST" && path === "/api/v1/investigations");
const CAN_INVESTIGATE = new Set(["operator", "approver"]);
// ACR-0017: the topology overlay (?incident_id=) uses the incident's evidence, so only operators and approvers.
const CAN_OVERLAY = new Set(["operator", "approver"]);

// role: "operator" (sees evidence and audit) or "viewer" (the API leaves them out of the incident view).
// overrides: { "<METHOD> <path>": (route, request) => … } to change one answer in a test.
async function fakeApi(page, { role = "operator", overrides = {} } = {}, state = {}) {
  state.investigate = CAN_INVESTIGATE.has(role);
  const me = { ...sample("me"), role, access: "investigate",
    actions: role === "viewer" ? ["view_incidents", "view_timeline"] : [...sample("me").actions, "start_investigation"] };
  const incident = sample("incident");
  if (role === "viewer") { delete incident.evidence; delete incident.audit; }
  const json = (route, body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

  // ACR-0011: the edge serves /runbooks/ only to a request with a valid bearer token (auth_request to /api/v1/me).
  await page.route("**/runbooks/**", async (route, request) => {
    if (!(request.headers().authorization ?? "").startsWith("Bearer ")) return json(route, { detail: "unauthorized" }, 401);
    const name = new URL(request.url()).pathname.split("/").pop();
    if (name === "index.json") return json(route, RUNBOOK_FILES);
    if (!RUNBOOK_FILES.includes(name)) return json(route, { detail: "not found" }, 404);
    return route.fulfill({ status: 200, contentType: "text/markdown", body: readFileSync(`${RUNBOOKS}${name}`, "utf8") });
  });

  await page.route("**/api/**", async (route, request) => {
    const url = new URL(request.url());
    const key = `${request.method()} ${url.pathname}`;
    if (overrides[key]) return overrides[key](route, request);
    if (!allowed(request.method(), url.pathname, state)) return json(route, { detail: "not allowed" }, 405);
    if (key === "POST /api/v1/auth/token") {
      const form = new URLSearchParams(request.postData() ?? "");
      if (form.get("password") !== PASSWORD) return json(route, { detail: "bad credentials" }, 401);
      return json(route, { ...sample("login"), access_token: TOKEN });
    }
    if (key === "GET /api/v1/me") return json(route, me);
    if (key === "GET /api/v1/incidents") return json(route, sample("incidents"));
    if (key === "GET /api/v1/escalations") return json(route, sample("escalations"));
    if (key === "GET /api/v1/targets") return json(route, sample("targets"));
    if (key === "GET /api/v1/host-metrics") return json(route, sample("host-metrics"));
    if (key === "GET /api/v1/topology") {                                    // ACR-0017
      const overlay = url.searchParams.get("incident_id");
      if (!overlay) return json(route, sample("topology"));
      return CAN_OVERLAY.has(role)
        ? json(route, sample("topology-incident"))
        : json(route, { detail: "role may not read the incident overlay" }, 403);
    }
    if (key === `GET /api/v1/incidents/${DIAGNOSED_ID}/metrics`) return json(route, sample("incident-metrics"));
    if (key === "GET /api/v1/target-metrics") return json(route, sample("target-metrics"));     // ACR-0021: the map drawer
    if (key === "POST /api/v1/investigations") return json(route, { ...sample("investigation"), incident_id: DIAGNOSED_ID }, 202);
    if (key === `GET /api/v1/incidents/${DIAGNOSED_ID}`) return json(route, incident);
    if (key === `GET /api/v1/incidents/${DIAGNOSED_ID}/events`) return json(route, sample("events"));
    if (url.pathname.startsWith("/api/v1/evidence/")) {
      return role === "viewer" ? json(route, { detail: "role viewer may not do this" }, 403) : json(route, sample("evidence"));
    }
    return json(route, { detail: "not found" }, 404);
  });
}

export const test = base.extend({
  // Every request of the page, for the guard; filled for the whole test, checked after it.
  // What the session may do, set by `api` (ACR-0012: may this role start an investigation?).
  // eslint-disable-next-line no-empty-pattern -- Playwright reads a fixture's dependencies from this pattern
  session: async ({}, use) => { await use({ investigate: false }); },
  requests: async ({ page, baseURL, session }, use) => {
    const seen = [];
    page.on("request", (r) => seen.push({ method: r.method(), url: r.url() }));
    await use(seen);
    expect(violations(seen, baseURL, session), "read-only guard: the app sent a forbidden request").toEqual([]);
  },
  api: async ({ page, session, requests: _guard }, use) => {     // depending on `requests` turns the guard on
    await use((options) => fakeApi(page, options, session));
  },
});

// The requests a read-only UI must never make (exported so the guard itself is tested).
export function violations(seen, baseURL, session = {}) {
  const origin = new URL(baseURL).origin;
  return seen.filter(({ method, url }) => {
    const u = new URL(url);
    if (u.protocol === "data:" || u.protocol === "blob:") return false;
    if (u.origin !== origin) return true;                              // nothing leaves the app's own origin
    return u.pathname.startsWith("/api/") && !allowed(method, u.pathname, session);
  });
}

export async function logIn(page, { username = "alice", password = PASSWORD } = {}) {
  await page.goto("/");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Log in" }).click();
}

export { expect };
