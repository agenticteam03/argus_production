import { describe, expect, it } from "vitest";
import { mockAuthAdapter } from "./mockAuthAdapter.js";

describe("mockAuthAdapter", () => {
  it("signs in the demo approver with the /me-shaped user", async () => {
    const session = await mockAuthAdapter.signIn({ username: "approver", password: "argus-demo" });
    expect(session.user).toEqual({
      name: "approver",
      role: "approver",
      access: "read",
      actions: ["view_incidents", "view_timeline", "view_evidence"],
    });
  });

  it("maps operator and viewer demo accounts to their roles", async () => {
    const op = await mockAuthAdapter.signIn({ username: "operator", password: "argus-demo" });
    const vi = await mockAuthAdapter.signIn({ username: "viewer", password: "argus-demo" });
    expect(op.user.role).toBe("operator");
    expect(vi.user.role).toBe("viewer");
  });

  it("never grants a write action: a read session only reads", async () => {
    for (const username of ["viewer", "operator", "approver"]) {
      const { user } = await mockAuthAdapter.signIn({ username, password: "argus-demo" });
      expect(user.actions).not.toContain("start_investigation");
      expect(user.actions).not.toContain("approve");
    }
  });

  it("rejects a wrong password with a message that is safe to show", async () => {
    await expect(mockAuthAdapter.signIn({ username: "approver", password: "nope" })).rejects.toThrow(
      "Incorrect username or password. Please try again."
    );
  });

  it("rejects an unknown account", async () => {
    await expect(mockAuthAdapter.signIn({ username: "stranger", password: "argus-demo" })).rejects.toThrow();
  });

  it("signOut resolves without a session", async () => {
    await expect(mockAuthAdapter.signOut()).resolves.toBeUndefined();
  });
});
