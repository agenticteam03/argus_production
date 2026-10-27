import { test, expect, logIn, sample, DIAGNOSED_ID } from "./fixtures.js";

test("an incident shows grounded action cards as suggestions only", async ({ page, api }) => {
  const incident = { ...sample("incident"), next_actions: [{
    action: "container.start",
    target: "vm-166/container:argus-lab-cache",
    text: "Candidate remediation: start the stopped cache dependency",
    basis: "runbook",
    grounds: ["RB-003"],
    evidence_refs: ["ev_cache_status"],
    risk_color: "green",
    is_executable: false,
  }] };
  await api({ overrides: {
    [`GET /api/v1/incidents/${DIAGNOSED_ID}`]: (route) => route.fulfill({
      status: 200, contentType: "application/json", body: JSON.stringify(incident),
    }),
  } });
  await logIn(page);
  await page.goto(`/incidents/${DIAGNOSED_ID}`);
  const section = page.getByRole("heading", { name: "Suggested actions" }).locator("..").locator("..");
  await expect(section).toContainText("container.start");
  await expect(section).toContainText("Green risk");
  await expect(section).toContainText("RB-003");
  await expect(section).toContainText("ev_cache_status");
  await expect(section.getByRole("button")).toHaveCount(0);
  if (process.env.ARGUS_UI_SCREENSHOT) {
    await page.screenshot({ path: process.env.ARGUS_UI_SCREENSHOT, fullPage: true });
  }
});
