import { describe, expect, it } from "vitest";
import { ROLES, canSee, flat, routes } from "./routes.js";

describe("routes", () => {
  it("uses the Argus roles viewer, operator and approver (no admin)", () => {
    expect(Object.keys(ROLES).sort()).toEqual(["approver", "operator", "viewer"]);
  });

  it("shows unrestricted routes to every role", () => {
    for (const role of Object.keys(ROLES)) {
      expect(canSee({ path: "/" }, role)).toBe(true);
    }
  });

  it("hides a route from roles that are not listed", () => {
    expect(canSee({ path: "/x", roles: ["approver"] }, "approver")).toBe(true);
    expect(canSee({ path: "/x", roles: ["approver"] }, "operator")).toBe(false);
    expect(canSee({ path: "/x", roles: ["approver"] }, "viewer")).toBe(false);
  });

  it("has no write screens in a read-only UI (approvals, simulator, scheduler)", () => {
    const paths = flat.map((r) => r.path);
    expect(paths).not.toContain("/approvals");
    expect(paths).not.toContain("/tools/simulator");
    expect(paths).not.toContain("/tools/scheduler");
  });

  it("flattens nested children so the router sees every leaf path", () => {
    const paths = flat.map((r) => r.path);
    expect(paths).toContain("/");
    expect(paths).toContain("/incidents");
    expect(paths).toContain("/tools/runbooks");
    expect(new Set(paths).size).toBe(paths.length); // no duplicates
  });

  it("every route with children gives each child its own path", () => {
    for (const r of routes) {
      if (r.children) for (const c of r.children) expect(typeof c.path).toBe("string");
    }
  });
});
