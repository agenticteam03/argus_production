// CON-3 (ACR-0043): until CON-2 adds the console routes and their contract entry, a real build has no console calls,
// so the incident page shows no Console tab and never asks for a console route, even when the URL names the tab.
import { DIAGNOSED_ID, expect, logIn, test } from "./fixtures.js";

test("a real build shows no Console tab and calls no console route before CON-2", async ({ page, api }) => {
  await api();
  const consoleCalls = [];
  page.on("request", (r) => { if (r.url().includes("/api/v1/ops/console/")) consoleCalls.push(r.url()); });
  await logIn(page);
  await page.goto(`/incidents/${DIAGNOSED_ID}?tab=console`);
  await expect(page.getByRole("tab", { name: "Incident & Diagnosis" })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tab", { name: "Console" })).toHaveCount(0);
  expect(consoleCalls).toEqual([]);
});
