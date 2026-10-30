// OP-014 step 12: accessibility checks (axe-core, WCAG 2 A and AA) on the main pages, against the built app with the
// API faked from contracts/samples like every acceptance test (fixtures.js). Any violation fails the test, colour
// contrast included (its two causes were fixed on 2026-10-22: `text-muted/60` and white on `bg-accent`).
// T-0016: in both themes, while a page loads (skeletons) and with a menu open. Content fades in (src/motion.css), and
// axe judges contrast on the page as it rests, so every animation that ends is let end first; endless ones (a
// skeleton's shimmer) are left running.
import AxeBuilder from "@axe-core/playwright";
import { DIAGNOSED_ID, expect, logIn, sample, test } from "./fixtures.js";

const settle = (page) => page.evaluate(() => Promise.all(document.getAnimations()
  .filter((a) => a.effect?.getComputedTiming().iterations !== Infinity)
  .map((a) => a.finished.catch(() => null))));
const scan = async (page) => { await settle(page); return new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze(); };
const found = (r) => r.violations.map((v) => `${v.impact} ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);

const PAGES = [
  ["login", null, (page) => expect(page.getByRole("button", { name: "Log in" })).toBeVisible()],
  ["dashboard", "/", (page) => expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible()],
  ["incidents", "/incidents", (page) => expect(page.getByRole("heading", { name: "Incidents" }).first()).toBeVisible()],
  ["incident", `/incidents/${DIAGNOSED_ID}`, (page) => expect(page.getByText("Why Argus concluded this")).toBeVisible()],
  ["runbooks", "/tools/runbooks", (page) => expect(page.getByRole("heading", { name: "Runbooks" })).toBeVisible()],
  ["agent", "/agent", (page) => expect(page.getByRole("heading", { name: "Investigation activity" })).toBeVisible()],
];

test.describe("accessibility (OP-014 step 12)", () => {
  for (const theme of ["dark", "light"]) {
    for (const [name, path, ready] of PAGES) {
      test(`the ${name} page has no WCAG 2 A/AA violation (${theme} theme)`, async ({ page, api }) => {
        await page.addInitScript((t) => localStorage.setItem("argus-theme", t), theme);
        await api();
        if (path === null) await page.goto("/login");
        else { await logIn(page); await page.goto(path); }
        await ready(page);
        expect(found(await scan(page))).toEqual([]);
      });
    }
  }

  test("the loading skeletons and an open menu have no violation (T-0016)", async ({ page, api }) => {
    let release;
    const held = new Promise((resolve) => { release = resolve; });
    await api({ overrides: { "GET /api/v1/incidents": async (route) => { await held; await route.fulfill({ json: sample("incidents") }); } } });
    await logIn(page);
    await expect(page.locator("main .skeleton").first()).toBeVisible();
    expect(found(await scan(page))).toEqual([]);
    release();
    await page.getByText("Tools", { exact: true }).click();
    await expect(page.getByRole("link", { name: /Runbooks/ })).toBeVisible();
    expect(found(await scan(page))).toEqual([]);
  });
});
