// OP-014 step 12: accessibility checks (axe-core, WCAG 2 A and AA) on the main pages, against the built app with the
// API faked from contracts/samples like every acceptance test (fixtures.js). Any violation fails the test.
// Known and left to the frontend lane (OP-014 step 12): `color-contrast`, two causes on 2026-10-21: `text-muted/60`
// (2.93:1) and white on `bg-accent` (3.67:1); AA asks 4.5:1. Remove it from KNOWN once they are fixed.
import AxeBuilder from "@axe-core/playwright";
import { DIAGNOSED_ID, expect, logIn, test } from "./fixtures.js";

const KNOWN = ["color-contrast"];
const scan = (page, disabled = KNOWN) => new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).disableRules(disabled).analyze();
const found = (r) => r.violations.map((v) => `${v.impact} ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);

const PAGES = [
  ["login", null, (page) => expect(page.getByRole("button", { name: "Log in" })).toBeVisible()],
  ["dashboard", "/", (page) => expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible()],
  ["incidents", "/incidents", (page) => expect(page.getByRole("heading", { name: "Incidents" }).first()).toBeVisible()],
  ["incident", `/incidents/${DIAGNOSED_ID}`, (page) => expect(page.getByText("Why Argus concluded this")).toBeVisible()],
  ["runbooks", "/runbooks", (page) => expect(page.getByRole("heading").first()).toBeVisible()],
];

test.describe("accessibility (OP-014 step 12)", () => {
  for (const [name, path, ready] of PAGES) {
    test(`the ${name} page has no WCAG 2 A/AA violation`, async ({ page, api }) => {
      await api();
      if (path === null) await page.goto("/login");
      else { await logIn(page); await page.goto(path); }
      await ready(page);
      expect(found(await scan(page))).toEqual([]);
    });
  }
});
