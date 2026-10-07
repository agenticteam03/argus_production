import { describe, expect, it } from "vitest";
import { canSee, flat, routes } from "./routes.js";

describe("routes", () => {
  it("shows unrestricted routes to every role", () => {
    for (const role of ["viewer", "operator", "admin"]) {
      expect(canSee({ path: "/" }, role)).toBe(true);
    }
  });

  it("hides a route from roles that are not listed", () => {
    expect(canSee({ path: "/approvals", roles: ["admin"] }, "admin")).toBe(true);
    expect(canSee({ path: "/approvals", roles: ["admin"] }, "operator")).toBe(false);
    expect(canSee({ path: "/approvals", roles: ["admin"] }, "viewer")).toBe(false);
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
