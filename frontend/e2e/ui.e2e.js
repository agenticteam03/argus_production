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

  test("a login asks for a read-only token and opens the dashboard", async ({ page, api }) => {
    await api();
    const login = page.waitForRequest((r) => r.url().endsWith("/api/v1/auth/token"));
    await logIn(page);
    const form = new URLSearchParams((await login).postData() ?? "");
    expect(form.get("scope")).toBe("read");                         // ACR-0001: never a full token
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  });
});

test.describe("dashboard (guideline 2)", () => {
  test("shows the recent incidents and the escalations from the API", async ({ page, api }) => {
    await api();
    await logIn(page);
    const firstTarget = sample("incidents")[0].target;
    await expect(page.getByText(firstTarget).first()).toBeVisible();
    const esc = sample("escalations")[0].payload;
    await expect(page.getByText(esc.route).first()).toBeVisible();
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
    await expect(page.getByText(/detect/i).first()).toBeVisible();      // the timeline's first node
  });

  test("an operator sees the evidence; a viewer sees that it is restricted", async ({ page, api }) => {
    await api({ role: "operator" });
    await logIn(page);
    await page.goto(`/incidents/${DIAGNOSED_ID}`);
    await expect(page.getByText(`via ${readCapability()}`).first()).toBeVisible();   // an evidence row

    await page.unrouteAll({ behavior: "ignoreErrors" });
    await api({ role: "viewer" });
    await page.reload();
    await expect(page.getByText(`via ${readCapability()}`)).toHaveCount(0);
    await expect(page.getByText("Evidence is visible to operators and approvers.")).toBeVisible();
  });

  test("an unknown incident shows 'Incident not found'", async ({ page, api }) => {
    await api();
    await logIn(page);
    await page.goto("/incidents/inc_doesnotexist");
    await expect(page.getByRole("heading", { name: "Incident not found" })).toBeVisible();
  });
});

test.describe("session", () => {
  test("log out returns to the login page, and a reload keeps it there", async ({ page, api }) => {
    await api();
    await logIn(page);
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await page.getByLabel("Account menu").click();
    await page.getByRole("button", { name: "Log out" }).click();
    await expect(page.getByRole("button", { name: "Log in" })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("button", { name: "Log in" })).toBeVisible();
  });

  test("a 401 from the API (token expired) returns to the login page", async ({ page, api }) => {
    let expired = false;
    await api({ overrides: { "GET /api/v1/incidents": (route) => (expired
      ? route.fulfill({ status: 401, contentType: "application/json", body: '{"detail":"expired"}' })
      : route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(sample("incidents")) })) } });
    await logIn(page);
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
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
  });
});
