// Acceptance tests of the read-only UI (T-0016, frontend/GUIDELINES.md), against the built app in real mode with
// the API faked from contracts/samples. Every test also runs the read-only network guard (fixtures.js).
import { DIAGNOSED_ID, expect, logIn, sample, test, violations } from "./fixtures.js";

// The first evidence record that came from a read (the reported symptom has no capability).
const readCapability = () => sample("incident").evidence.find((e) => e.capability).capability;

test.describe("login (guideline 1)", () => {
  test("a wrong password shows the error and stays on the login page", async ({ page, api }) => {
    await api();
    await logIn(page, { password: "wrong" });
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.getByRole("button", { name: "Log in" })).toBeVisible();
  });

  test("a login asks for an investigate token (never a full one) and opens the dashboard", async ({ page, api }) => {
    await api();
    const login = page.waitForRequest((r) => r.url().endsWith("/api/v1/auth/token"));
    await logIn(page);
    const form = new URLSearchParams((await login).postData() ?? "");
    expect(form.get("scope")).toBe("investigate");                  // ACR-0012; never a full token (ACR-0001)
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  });
});

test.describe("dashboard (guideline 2)", () => {
  test("shows the recent incidents and the escalations from the API", async ({ page, api }) => {
    await api();
    await logIn(page);
    const firstTarget = sample("incidents")[0].target;
    await expect(page.getByRole("link").filter({ hasText: firstTarget }).first()).toBeVisible();   // a row, not the form's option
    const esc = sample("escalations")[0].payload;
    await expect(page.getByText(esc.route).first()).toBeVisible();
  });

  test("shows the live system map (ACR-0017)", async ({ page, api }) => {
    await api();
    await logIn(page);
    await expect(page.getByText("System map")).toBeVisible();
    await expect(page.locator('svg[aria-label^="System map"]')).toBeVisible();
  });

  test("shows current host metrics and answers a Host T memory question", async ({ page, api }) => {
    await api();
    await logIn(page);
    await expect(page.getByText("Host metrics")).toBeVisible();
    // The value carries its level as screen-reader text ("60.0% (Normal)"), so the colour is never the only signal.
    await expect(page.getByText("60.0% (Normal)").first()).toBeVisible();
    await page.getByLabel("Message for the agent").fill("Check Host T memory usage");
    await page.getByRole("button", { name: "Send" }).click();
    await expect(page.getByText(/Host T \(vm-166\) memory usage: 60.0%/)).toBeVisible();
  });

  test("a chat diagnosis starts an investigation and links to its incident", async ({ page, api }) => {
    await api({ role: "operator" });
    await logIn(page);
    await page.getByLabel("Message for the agent").fill("Investigate Host T");
    const sent = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith("/api/v1/investigations"));
    await page.getByRole("button", { name: "Send" }).click();
    expect(JSON.parse((await sent).postData())).toMatchObject({ target: "vm-166/host:vm-166", request_kind: "check" });
    await expect(page.getByRole("link", { name: "Open incident" })).toHaveAttribute("href", `/incidents/${DIAGNOSED_ID}`);
  });
});

test.describe("incidents", () => {
  test("the list opens an incident with its diagnosis and its run timeline", async ({ page, api }) => {
    await api();
    await logIn(page);
    await page.getByRole("link", { name: "Incidents" }).first().click();
    await expect(page.getByRole("heading", { name: "Incidents", level: 1 })).toBeVisible();
    await page.locator(`a[href="/incidents/${DIAGNOSED_ID}"]`).first().click();
    const inc = sample("incident");
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(inc.target);
    await expect(page.getByText(inc.diagnosis).first()).toBeVisible();
    await page.getByRole("tab", { name: "Runtime Timeline" }).click();   // the redesign moved the timeline into a tab
    await expect(page.getByText(/detect/i).first()).toBeVisible();      // the timeline's first node
  });

  test("an operator sees the evidence; a viewer sees that it is restricted", async ({ page, api }) => {
    await api({ role: "operator" });
    await logIn(page);
    await page.goto(`/incidents/${DIAGNOSED_ID}`);
    await page.getByRole("tab", { name: "Evidence" }).click();                      // the redesign moved evidence into a tab
    await expect(page.getByText(`via ${readCapability()}`).first()).toBeVisible();   // an evidence row

    await page.unrouteAll({ behavior: "ignoreErrors" });
    await api({ role: "viewer" });
    await page.reload();
    await page.getByRole("tab", { name: "Evidence" }).click();
    await expect(page.getByText(`via ${readCapability()}`)).toHaveCount(0);
    await expect(page.getByText("Evidence is visible to operators and approvers.")).toBeVisible();
  });

  test("the page groups its sections into tabs and shows Map/Metrics when their routes answer (ACR-0017)", async ({ page, api }) => {
    await api();
    await logIn(page);
    await page.goto(`/incidents/${DIAGNOSED_ID}`);
    await expect(page.getByRole("tab", { name: "Incident & Diagnosis" })).toHaveAttribute("aria-selected", "true");
    for (const name of ["Runtime Timeline", "Evidence", "Audit"]) {
      await expect(page.getByRole("tab", { name })).toBeVisible();
    }
    // VITE_ARGUS_INSIGHTS=1 and the faked API serve GET /api/v1/topology and .../metrics, so both tabs appear and
    // render the real shapes. "unknown" edges must show, never as "dependency ok".
    await page.getByRole("tab", { name: "Map", exact: true }).click();
    await expect(page.locator('svg[aria-label^="System map"]')).toBeVisible();
    await expect(page.getByText("unknown", { exact: true })).toBeVisible();          // the legend entry
    await page.getByRole("tab", { name: "Metrics", exact: true }).click();
    await expect(page.getByText(/missing sample is a gap/)).toBeVisible();
  });

  test("an operator's Map asks for the incident overlay (ACR-0017)", async ({ page, api }) => {
    await api({ role: "operator" });
    const overlay = page.waitForRequest((r) => r.url().includes("/api/v1/topology?incident_id="));
    await logIn(page);
    await page.goto(`/incidents/${DIAGNOSED_ID}`);
    await overlay;                                                     // the incident page asks for the overlay
    await page.getByRole("tab", { name: "Map", exact: true }).click();
    await expect(page.locator('svg[aria-label^="System map"]')).toBeVisible();
  });

  test("a viewer never asks for the overlay and still sees the plain map (ACR-0017)", async ({ page, api }) => {
    await api({ role: "viewer" });
    const seen = [];
    page.on("request", (r) => { if (r.url().includes("/api/v1/topology")) seen.push(r.url()); });
    await logIn(page);
    await page.goto(`/incidents/${DIAGNOSED_ID}`);
    await page.getByRole("tab", { name: "Map", exact: true }).click();
    await expect(page.locator('svg[aria-label^="System map"]')).toBeVisible();
    expect(seen.some((u) => u.includes("incident_id"))).toBe(false);   // a viewer gets the plain map only
  });

  test("a refused overlay (403) falls back to the plain map (ACR-0017)", async ({ page, api }) => {
    // The overlay is operator/approver only; if the API refuses it, the page must still show the plain system map
    // instead of losing it (the API decides permissions, never the UI).
    await api({ role: "operator", overrides: {
      "GET /api/v1/topology": (route, request) => {
        const overlay = new URL(request.url()).searchParams.get("incident_id");
        return route.fulfill({ status: overlay ? 403 : 200, contentType: "application/json",
          body: JSON.stringify(overlay ? { detail: "role may not read the incident overlay" } : sample("topology")) });
      },
    } });
    await logIn(page);
    await page.goto(`/incidents/${DIAGNOSED_ID}`);
    await page.getByRole("tab", { name: "Map", exact: true }).click();
    await expect(page.locator('svg[aria-label^="System map"]')).toBeVisible();
  });

  test("an unknown incident shows 'Incident not found'", async ({ page, api }) => {
    await api();
    await logIn(page);
    await page.goto("/incidents/inc_doesnotexist");
    await expect(page.getByRole("heading", { name: "Incident not found" })).toBeVisible();
  });
});

test.describe("runbooks (guideline 3)", () => {
  test("load after login, with the token, from the edge (not from the bundle)", async ({ page, api }) => {
    await api();
    const asked = page.waitForRequest((r) => r.url().endsWith("/runbooks/index.json"));
    await logIn(page);
    await page.goto("/tools/runbooks");
    expect((await asked).headers().authorization).toMatch(/^Bearer /);
    await expect(page.getByRole("heading", { name: "Runbooks" })).toBeVisible();
    await expect(page.getByText("RB-001").first()).toBeVisible();
  });
});

test.describe("session", () => {
  test("log out returns to the login page, and a reload keeps it there", async ({ page, api }) => {
    await api();
    await logIn(page);
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await page.getByLabel("Account menu").click();
    const loggedOut = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith("/api/v1/auth/logout"));
    await page.getByRole("button", { name: "Log out" }).click();
    await loggedOut;                                   // ACR-0018: the session is ended on the server, not only forgotten
    await expect(page.getByRole("button", { name: "Log in" })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("button", { name: "Log in" })).toBeVisible();
  });

  test("a 401 from the API (token expired) returns to the login page", async ({ page, api }) => {
    let expired = false;
    await api({ overrides: { "GET /api/v1/incidents": (route) => (expired
      ? route.fulfill({ status: 401, contentType: "application/json", body: '{"detail":"expired"}' })
      : route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(sample("incidents")) })) } });
    const firstList = page.waitForResponse((r) => r.url().includes("/api/v1/incidents?") && r.status() === 200);
    await logIn(page);
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await firstList;                                   // the dashboard's own first load done, so the 401 is the list's
    expired = true;
    await page.getByRole("link", { name: "Incidents" }).first().click();
    await expect(page.getByRole("button", { name: "Log in" })).toBeVisible();
  });
});

test.describe("read-only guard", () => {
  test("flags a write to the API and a request to another origin", async ({ baseURL }) => {
    const seen = [
      { method: "GET", url: `${baseURL}/api/v1/incidents?limit=30` },
      { method: "POST", url: `${baseURL}/api/v1/auth/token` },
      { method: "POST", url: `${baseURL}/api/v1/investigations` },
      { method: "DELETE", url: `${baseURL}/api/v1/incidents/x` },
      { method: "GET", url: "https://example.org/track.js" },
      { method: "GET", url: `${baseURL}/assets/app.js` },
    ];
    expect(violations(seen, baseURL).map((v) => `${v.method} ${new URL(v.url).pathname}`))
      .toEqual(["POST /api/v1/investigations", "DELETE /api/v1/incidents/x", "GET /track.js"]);
    // ACR-0012: the one POST is allowed when the session may start an investigation, and nothing else is
    expect(violations(seen, baseURL, { investigate: true }).map((v) => `${v.method} ${new URL(v.url).pathname}`))
      .toEqual(["DELETE /api/v1/incidents/x", "GET /track.js"]);
  });
});

test.describe("start an investigation (ACR-0012)", () => {
  const TARGET = sample("targets").find((t) => t.target.startsWith("vm-166/")).target;

  test("an operator starts one from the dashboard and lands on the new incident", async ({ page, api }) => {
    await api({ role: "operator" });
    await logIn(page);
    const form = page.getByRole("form", { name: "Start an investigation" });
    await form.getByLabel("Target").click();
    await form.getByRole("option", { name: TARGET, exact: true }).click();
    await form.getByRole("group", { name: "Kind" }).getByRole("button", { name: "Check" }).click();
    await form.getByLabel("Reason").fill("users report slowness");
    const sent = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith("/api/v1/investigations"));
    await form.getByRole("button", { name: "Start investigation" }).click();
    expect(JSON.parse((await sent).postData())).toEqual({ target: TARGET, request_kind: "check", reason: "users report slowness" });
    await expect(page).toHaveURL(new RegExp(`/incidents/${DIAGNOSED_ID}$`));
  });

  test("a viewer sees no way to start one, and sends nothing", async ({ page, api }) => {
    await api({ role: "viewer" });
    await logIn(page);
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await expect(page.getByRole("form", { name: "Start an investigation" })).toHaveCount(0);
    await page.goto(`/incidents/${DIAGNOSED_ID}`);
    await expect(page.getByRole("button", { name: "Investigate again" })).toHaveCount(0);
  });

  test("a quota answer says when to try again", async ({ page, api }) => {
    await api({ role: "operator", overrides: { "POST /api/v1/investigations": (route) => route.fulfill({
      status: 429, headers: { "Retry-After": "600" }, contentType: "application/json",
      body: '{"detail":"investigation quota reached (per_hour)"}' }) } });
    await logIn(page);
    const form = page.getByRole("form", { name: "Start an investigation" });
    await form.getByLabel("Target").click();
    await form.getByRole("option", { name: TARGET, exact: true }).click();
    await form.getByRole("button", { name: "Start investigation" }).click();
    await expect(form.getByRole("alert")).toContainText("10 min");
  });

  test("an incident's page starts a new investigation of the same target", async ({ page, api }) => {
    await api({ role: "operator" });
    await logIn(page);
    await page.goto(`/incidents/${DIAGNOSED_ID}`);
    const sent = page.waitForRequest((r) => r.method() === "POST" && r.url().endsWith("/api/v1/investigations"));
    await page.getByRole("button", { name: "Investigate again" }).click();
    expect(JSON.parse((await sent).postData()).target).toBe(sample("incident").target);
  });
});
