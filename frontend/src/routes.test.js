import { describe, expect, it, vi } from "vitest";
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

  it("shows Actions to an approver only (it leads to the private login), in the local demo too", () => {
    const actions = routes.find((r) => r.path === "/actions");
    expect(actions).toBeDefined();
    expect(canSee(actions, "approver", [])).toBe(true);
    expect(canSee(actions, "operator", [])).toBe(false);
    expect(canSee(actions, "viewer", ["approve_action"])).toBe(false);
    // T-0016: the demo flag fills the screen with a synthetic approval; it never opens it to another role
    vi.stubEnv("VITE_ARGUS_PHASE19_DEMO", "1");
    expect(canSee(actions, "operator", [])).toBe(false);
    expect(canSee(actions, "viewer", [])).toBe(false);
    vi.unstubAllEnvs();
  });

  it("shows Reference sources to approvers and administrators before the private login (ACR-0034, ACR-0040)", () => {
    const sources = flat.find((r) => r.path === "/tools/reference-sources");
    expect(sources).toBeDefined();
    expect(canSee(sources, "approver", [])).toBe(true);     // the screen then leads through the private login
    expect(canSee(sources, "admin", [])).toBe(true);
    expect(canSee(sources, "operator", [])).toBe(false);
    expect(canSee(sources, "viewer", ["manage_corpus"])).toBe(false);
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
