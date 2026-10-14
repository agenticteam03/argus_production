// The fake Argus API and the read-only network guard shared by every acceptance test (T-0016).
//
// Fake API: answers in the browser (page.route) from contracts/samples/*.json, the real responses recorded by the
// contract test, so a UI test and the API's contract test read the same bodies.
//
// Read-only guard: records every request the page makes. A test fails if the app sends anything to the API except a
// GET or the login POST, or talks to any other origin. ACR-0001: a read-only UI never starts, approves or changes
// anything.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { test as base, expect } from "@playwright/test";

const SAMPLES = fileURLToPath(new URL("../../contracts/samples/", import.meta.url));
export const sample = (name) => JSON.parse(readFileSync(`${SAMPLES}${name}.json`, "utf8"));

export const PASSWORD = "right-password";
export const DIAGNOSED_ID = sample("incident").id;          // the sample's diagnosed incident

// A token whose payload has an `exp` one hour ahead, so the session store keeps it (sessionStore.tokenExpiry).
const b64 = (o) => Buffer.from(JSON.stringify(o)).toString("base64url");
const TOKEN = `${b64({ alg: "HS256" })}.${b64({ sub: "alice", access: "read", exp: Math.floor(Date.now() / 1000) + 3600 })}.sig`;

const allowed = (method, path) => method === "GET" || (method === "POST" && path === "/api/v1/auth/token");

// role: "operator" (sees evidence and audit) or "viewer" (the API leaves them out of the incident view).
// overrides: { "<METHOD> <path>": (route, request) => … } to change one answer in a test.
async function fakeApi(page, { role = "operator", overrides = {} } = {}) {
  const me = { ...sample("me"), role,
    actions: role === "viewer" ? ["view_incidents", "view_timeline"] : sample("me").actions };
  const incident = sample("incident");
  if (role === "viewer") { delete incident.evidence; delete incident.audit; }
  const json = (route, body, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

  await page.route("**/api/**", async (route, request) => {
    const url = new URL(request.url());
    const key = `${request.method()} ${url.pathname}`;
    if (overrides[key]) return overrides[key](route, request);
    if (!allowed(request.method(), url.pathname)) return json(route, { detail: "not allowed" }, 405);
    if (key === "POST /api/v1/auth/token") {
      const form = new URLSearchParams(request.postData() ?? "");
      if (form.get("password") !== PASSWORD) return json(route, { detail: "bad credentials" }, 401);
      return json(route, { ...sample("login"), access_token: TOKEN });
    }
    if (key === "GET /api/v1/me") return json(route, me);
    if (key === "GET /api/v1/incidents") return json(route, sample("incidents"));
    if (key === "GET /api/v1/escalations") return json(route, sample("escalations"));
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
  requests: async ({ page, baseURL }, use) => {
    const seen = [];
    page.on("request", (r) => seen.push({ method: r.method(), url: r.url() }));
    await use(seen);
    expect(violations(seen, baseURL), "read-only guard: the app sent a forbidden request").toEqual([]);
  },
  api: async ({ page, requests: _guard }, use) => {     // depending on `requests` turns the guard on
    await use((options) => fakeApi(page, options));
  },
});

// The requests a read-only UI must never make (exported so the guard itself is tested).
export function violations(seen, baseURL) {
  const origin = new URL(baseURL).origin;
  return seen.filter(({ method, url }) => {
    const u = new URL(url);
    if (u.protocol === "data:" || u.protocol === "blob:") return false;
    if (u.origin !== origin) return true;                              // nothing leaves the app's own origin
    return u.pathname.startsWith("/api/") && !allowed(method, u.pathname);
  });
}

export async function logIn(page, { username = "alice", password = PASSWORD } = {}) {
  await page.goto("/");
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Log in" }).click();
}

export { expect };
