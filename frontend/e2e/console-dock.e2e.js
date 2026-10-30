// T-0016: the operator console (ACR-0043) in its side panel, against a build with VITE_ARGUS_CONSOLE=1 (the "console"
// project of playwright.config.js) and the API faked from contracts/samples. The access dialog follows /me: two keys,
// and the private session (ACR-0032) confirmed with one. Only an approver sees the console.
import AxeBuilder from "@axe-core/playwright";
import { DIAGNOSED_ID, expect, logIn, sample, test } from "./fixtures.js";

const meWith = (secondFactor, access = "investigate") => ({
  "GET /api/v1/me": (route) => route.fulfill({ status: 200, contentType: "application/json",
    body: JSON.stringify({ ...sample("me"), role: "approver", access, actions: [...sample("me").actions, "start_investigation"],
      second_factor: secondFactor }) }),
});
const scan = async (page) => (await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze()).violations
  .map((v) => `${v.impact} ${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
const dialog = (page) => page.getByRole("dialog", { name: "Open the operator console" });
const panel = (page) => page.getByRole("complementary", { name: "Operator console" });

async function openFromTools(page) {
  await page.getByText("Tools", { exact: true }).click();
  await page.getByRole("button", { name: /Console/ }).click();
  return dialog(page);
}

test.describe("operator console side panel", () => {
  test("case 2, no key: it says to ask the administrator and offers no way in", async ({ page, api }) => {
    await api({ role: "approver", console: true, overrides: meWith({ enrolled: 0, verified: false }) });
    await logIn(page);
    const d = await openFromTools(page);
    await expect(d.getByText("No security key yet")).toBeVisible();
    await expect(d.getByText(/Ask your Argus administrator/)).toBeVisible();
    await expect(d.getByRole("button", { name: "Enter the console" })).toHaveCount(0);
  });

  test("case 1, one key: a button takes the person to register the second", async ({ page, api }) => {
    await api({ role: "approver", console: true, overrides: meWith({ enrolled: 1, verified: true }) });
    await logIn(page);
    const d = await openFromTools(page);
    await d.getByRole("link", { name: "Register your second key" }).click();
    await expect(page).toHaveURL(/\/account\/security$/);
  });

  test("case 3, two keys on the ordinary session: the private sign-in comes first", async ({ page, api }) => {
    await api({ role: "approver", console: true, overrides: meWith({ enrolled: 2, verified: false }) });
    await logIn(page);
    const d = await openFromTools(page);
    await expect(d.getByText("Confirm it is you")).toBeVisible();
    await expect(d.getByRole("button", { name: "Sign in privately" })).toBeVisible();
    await expect(d.getByLabel(/Reason for access/)).toHaveCount(0);
    expect(await scan(page)).toEqual([]);
  });

  test("case 4: the reason, the panel, a command, full screen, minimize and Disconnect", async ({ page, api }) => {
    await api({ role: "approver", console: true, overrides: meWith({ enrolled: 2, verified: true }, "ops") });
    await logIn(page);
    await page.goto(`/incidents/${DIAGNOSED_ID}`);
    await page.getByRole("button", { name: "Open console on vm-166" }).click();
    const d = dialog(page);
    await expect(d.getByLabel(/Reason for access/)).toHaveValue(`Investigate ${DIAGNOSED_ID} on vm-166`);
    await d.getByRole("button", { name: "Enter the console" }).click();

    const p = panel(page);
    await expect(p.getByRole("tab", { name: /vm-166/ })).toHaveAttribute("aria-selected", "true");
    await expect(p.getByRole("timer")).toHaveText(/^(30:00|29:\d\d)$/);
    await expect(p.getByText(`Reason: Investigate ${DIAGNOSED_ID} on vm-166`)).toBeVisible();
    await p.getByLabel("Console command").fill("help");
    await p.getByRole("button", { name: "Run" }).click();
    await expect(p.getByRole("log", { name: "Console output" })).toContainText("List the commands");
    expect(await scan(page)).toEqual([]);

    const width = (await p.boundingBox()).width;
    await p.getByRole("separator", { name: "Resize the console" }).press("ArrowLeft");
    expect((await p.boundingBox()).width).toBeGreaterThan(width);
    const wider = (await p.boundingBox()).width;
    await p.getByRole("button", { name: "Full screen" }).click();
    expect((await p.boundingBox()).width).toBeGreaterThan(1200);
    await p.getByRole("button", { name: "Exit full screen" }).click();
    expect((await p.boundingBox()).width).toBe(wider);
    await p.getByRole("button", { name: "Minimize the console" }).click();
    await expect(p).toBeHidden();
    await page.getByRole("button", { name: /Restore the console/ }).click();
    await expect(p).toBeVisible();

    await p.getByRole("button", { name: /Disconnect/ }).click();
    await expect(p).toHaveCount(0);
    await expect(page.getByText("Disconnected from the console on vm-166.")).toBeVisible();
  });

  test("two consoles: each tab closes with its x, the last one only with Disconnect; the + menu closes outside", async ({ page, api }) => {
    await api({ role: "approver", console: true, overrides: meWith({ enrolled: 2, verified: true }, "ops") });
    await logIn(page);
    await page.goto(`/incidents/${DIAGNOSED_ID}`);
    await page.getByRole("button", { name: "Open console on vm-166" }).click();
    await dialog(page).getByRole("button", { name: "Enter the console" }).click();

    const p = panel(page);
    await expect(p.getByRole("button", { name: /^Close the console/ })).toHaveCount(0);      // one session: no x
    const plus = p.getByLabel("Open the console on a host");
    await plus.click();
    await expect(p.getByRole("button", { name: "vm-095" })).toBeVisible();
    await page.getByRole("heading", { level: 1 }).click();                                  // a click outside
    await expect(p.getByRole("button", { name: "vm-095" })).toBeHidden();

    await plus.click();
    await p.getByRole("button", { name: "vm-095" }).click();
    const d = dialog(page);
    await d.getByLabel(/Reason for access/).fill("Check the worker on vm-095");
    await d.getByRole("button", { name: "Enter the console" }).click();
    await expect(p.getByRole("tab")).toHaveCount(2);
    await expect(p.getByRole("button", { name: /^Close the console/ })).toHaveCount(2);
    await p.getByRole("button", { name: /^Close the console on vm-095/ }).click();
    await expect(p.getByRole("tab")).toHaveCount(1);
    await expect(p.getByRole("button", { name: /^Close the console/ })).toHaveCount(0);
    await expect(p.getByRole("button", { name: /Disconnect/ })).toBeVisible();
  });

  test("an operator sees no console: it is the approver's", async ({ page, api }) => {
    await api({ role: "operator", console: true });
    await logIn(page);
    await page.getByText("Tools", { exact: true }).click();
    await expect(page.getByRole("button", { name: /Console/ })).toHaveCount(0);
    await page.goto(`/incidents/${DIAGNOSED_ID}`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.getByRole("button", { name: /Open console/ })).toHaveCount(0);
  });
});
