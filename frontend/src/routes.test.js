import { describe, expect, it } from "vitest";
import { ROLES, canSee, flat, routes } from "./routes.js";

const viewer = { role: "viewer", actions: ["view_incidents", "view_timeline"] };
const nobody = { role: "viewer", actions: [] };

describe("routes", () => {
  it("uses only the Argus roles", () => {
    expect(Object.keys(ROLES)).toEqual(["viewer", "operator", "approver"]);
  });

  it("shows a route without an action to every user", () => {
    expect(canSee({ path: "/" }, nobody)).toBe(true);
  });

  it("shows a route only when /me lists its action (no role logic in the UI)", () => {
    expect(canSee({ path: "/incidents", action: "view_incidents" }, viewer)).toBe(true);
    expect(canSee({ path: "/incidents", action: "view_incidents" }, nobody)).toBe(false);
  });

  it("has no page that writes: approvals, agent chat, alert simulator, scheduler (ACR-0001)", () => {
    const paths = flat.map((r) => r.path);
    for (const p of ["/approvals", "/agent", "/tools/simulator", "/tools/scheduler"]) expect(paths).not.toContain(p);
  });

  it("gates routes only on actions a read token can get", () => {
    const readActions = ["view_incidents", "view_timeline", "view_evidence"];
    for (const r of flat) if (r.action) expect(readActions).toContain(r.action);
    expect(flat.some((r) => "roles" in r)).toBe(false);
  });

  it("flattens nested children so the router sees every leaf path", () => {
    const paths = flat.map((r) => r.path);
    expect(paths).toContain("/");
    expect(paths).toContain("/tools/runbooks");
    expect(new Set(paths).size).toBe(paths.length); // no duplicates
  });

  it("every route with children gives each child its own path", () => {
    for (const r of routes) {
      if (r.children) for (const c of r.children) expect(typeof c.path).toBe("string");
    }
  });
});
