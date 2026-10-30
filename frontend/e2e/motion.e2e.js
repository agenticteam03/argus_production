// T-0016: animations and micro-interactions, against the built app with the API faked from contracts/samples like every
// acceptance test (fixtures.js). The animations are theme tokens (src/motion.css): these tests check that each part of
// the UI uses the right one, that slow loads shimmer instead of flashing an empty state, and that
// prefers-reduced-motion: reduce leaves nothing moving.
import { DIAGNOSED_ID, expect, logIn, sample, test } from "./fixtures.js";

// The animation the CSS gives an element: its name stays after it ends, so the check does not race a 200 ms animation.
const anim = (locator, pseudo = null) => locator.evaluate((el, p) => {
  const s = getComputedStyle(el, p);
  return { name: s.animationName, delay: parseFloat(s.animationDelay) };
}, pseudo);
// The CSS animations running on the page right now (transitions are not counted).
const running = (page) => page.evaluate(() => document.getAnimations().filter((a) => a instanceof CSSAnimation).map((a) => a.animationName));
const card = (page, title) => page.locator("section").filter({ has: page.getByRole("heading", { name: new RegExp(`^${title}`) }) });
// A request held until the test lets it go, so the loading state can be looked at.
function hold() {
  let release;
  const held = new Promise((resolve) => { release = resolve; });
  return { held, release };
}

test.describe("loading skeletons", () => {
  test("a slow dashboard shimmers where its data will be, never shows an empty state first, then the data", async ({ page, api }) => {
    const { held, release } = hold();
    await api({ overrides: { "GET /api/v1/incidents": async (route) => { await held; await route.fulfill({ json: sample("incidents") }); } } });
    await logIn(page);
    const recent = card(page, "Recent incidents");
    const skeleton = recent.locator(".skeleton").first();
    await expect(skeleton).toBeVisible();
    expect((await anim(skeleton, "::after")).name).toBe("shimmer");
    await expect(recent.getByText("No recent activity")).toHaveCount(0);
    await expect(card(page, "Escalations").locator(".skeleton").first()).toBeVisible();
    release();
    await expect(recent.getByRole("link").filter({ hasText: sample("incidents")[0].target }).first()).toBeVisible();
    await expect(page.locator("main .skeleton")).toHaveCount(0);
  });

  test("the runbook library and the agent's runs shimmer while they load", async ({ page, api }) => {
    await api();
    await logIn(page);
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    const books = hold();
    await page.route("**/runbooks/index.json", async (route) => { await books.held; await route.fallback(); });
    await page.goto("/tools/runbooks");
    await expect(page.locator("[aria-busy=true] .skeleton").first()).toBeVisible();
    books.release();
    await expect(page.locator("main .skeleton")).toHaveCount(0);

    const runs = hold();
    await page.route("**/api/v1/incidents?*", async (route) => { await runs.held; await route.fallback(); });
    await page.getByRole("link", { name: "Agent", exact: true }).click();
    await expect(card(page, "Runs").locator(".skeleton").first()).toBeVisible();
    runs.release();
    await expect(card(page, "Runs").locator(".skeleton")).toHaveCount(0);
  });
});

test.describe("transitions and micro-interactions", () => {
  test("each new page fades in", async ({ page, api }) => {
    await api();
    await logIn(page);
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    const pageBox = () => page.locator("main > div").first();
    expect((await anim(pageBox())).name).toBe("page-in");
    await pageBox().evaluate((el) => { el.dataset.seen = "1"; });
    await page.getByRole("link", { name: "Incidents", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Incidents" }).first()).toBeVisible();
    await expect(pageBox()).not.toHaveAttribute("data-seen");             // a new element: its animation ran again
    expect((await anim(pageBox())).name).toBe("page-in");
  });

  test("menus and the themed select drop open, tabs fade between panels and the dialog rises in", async ({ page, api }) => {
    await api();
    await logIn(page);
    await page.getByText("Tools", { exact: true }).click();
    expect((await anim(page.locator("header details[open] > div"))).name).toBe("drop");
    await page.getByText("Tools", { exact: true }).click();                // closes it again

    await page.goto("/incidents");
    await page.getByRole("combobox", { name: "Filter by status" }).click();
    expect((await anim(page.getByRole("listbox"))).name).toBe("drop");
    await page.keyboard.press("Escape");

    await page.goto(`/incidents/${DIAGNOSED_ID}`);
    await page.getByRole("tab", { name: "Evidence" }).click();
    const panel = page.locator("#panel-evidence");                       // the new panel, not the one it replaces
    await expect(panel).toBeVisible();
    expect((await anim(panel)).name).toBe("fade-in");
    await page.getByRole("button", { name: "Raw output" }).click();
    const dialog = page.getByRole("dialog", { name: "Raw output" });
    await expect(dialog).toBeVisible();
    expect((await anim(dialog)).name).toBe("dialog-in");
    expect((await anim(dialog, "::backdrop")).name).toBe("fade-in");
  });

  test("the incident's More menu drops open with the details shown (#418)", async ({ page, api }) => {
    await api();
    await logIn(page);
    await page.goto(`/incidents/${DIAGNOSED_ID}`);
    await page.getByText("Details: trigger, principal, times").click();
    await page.getByText("More", { exact: true }).click();
    expect((await anim(page.locator("main details[open] > div").last())).name).toBe("drop");
  });

  test("list rows come in one after another", async ({ page, api }) => {
    await api();
    await logIn(page);
    await page.goto("/incidents");
    const rows = card(page, "Incidents").locator("li");
    await expect(rows.nth(1)).toBeVisible();
    const [first, second] = [await anim(rows.nth(0)), await anim(rows.nth(1))];
    expect(first.name).toBe("rise");
    expect(second.name).toBe("rise");
    expect(second.delay).toBeGreaterThan(first.delay);
  });

  test("the host bars grow and the map's boxes rise in as the dashboard loads", async ({ page, api }) => {
    await api();
    await logIn(page);
    const bar = card(page, "Host metrics").locator("li [aria-hidden=true] > span").first();
    await expect(bar).toBeAttached();
    expect((await anim(bar)).name).toBe("grow-x");
    const box = page.getByRole("region", { name: /^System map/ }).getByRole("button", { name: /Open details$/ }).first();
    await expect(box).toBeVisible();
    expect((await anim(box)).name).toBe("rise");
  });

  test("a wrong password nudges its message; a toast slides in and out", async ({ page, api }) => {
    await api();
    await logIn(page, { password: "wrong" });
    expect((await anim(page.getByRole("alert"))).name).toBe("shake");

    await logIn(page);
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    // The way out lasts 160 ms, shorter than a poll of expect(): the page itself records the toast's classes.
    await page.evaluate(() => {
      window.toastClasses = [];
      const seen = (n) => n instanceof Element && n.className.includes?.("toast-") && window.toastClasses.push(n.className);
      new MutationObserver((records) => records.forEach((r) => { seen(r.target); r.addedNodes.forEach(seen); }))
        .observe(document.body, { subtree: true, childList: true, attributes: true, attributeFilter: ["class"] });
    });
    await page.getByRole("button", { name: "Refresh now" }).click();
    const toast = page.getByRole("status").filter({ hasText: "Data refreshed" });
    await expect(toast).toBeVisible();
    expect((await anim(toast)).name).toBe("rise");
    await expect(toast).toHaveCount(0, { timeout: 6_000 });
    expect(await page.evaluate(() => window.toastClasses.some((c) => c.includes("toast-out")))).toBe(true);
  });
});

test.describe("prefers-reduced-motion: reduce", () => {
  test("nothing moves on the main pages, and every motion token is off", async ({ page, api }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await api();
    await logIn(page);
    await expect(page.getByRole("region", { name: /^System map/ }).getByRole("button", { name: /Open details$/ }).first()).toBeVisible();
    await page.getByText("Tools", { exact: true }).click();
    expect(await running(page)).toEqual([]);
    expect(await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue("--motion-count").trim())).toMatch(/^0m?s$/);

    for (const [path, ready] of [
      ["/incidents", () => page.getByRole("heading", { name: "Incidents" }).first()],
      [`/incidents/${DIAGNOSED_ID}`, () => page.getByText("Why Argus concluded this")],
      ["/tools/runbooks", () => page.getByRole("heading", { name: "Runbooks" }).first()],
      ["/agent", () => page.getByRole("heading", { name: "Investigation activity" })],
    ]) {
      await page.goto(path);
      await expect(ready()).toBeVisible();
      expect(await running(page), path).toEqual([]);
    }
  });
});
