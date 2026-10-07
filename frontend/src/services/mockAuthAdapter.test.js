import { describe, expect, it } from "vitest";
import { mockAuthAdapter } from "./mockAuthAdapter.js";

// The session has the shape of GET /api/v1/me (contracts/samples/me.json) for a read token (ACR-0001).
describe("mockAuthAdapter", () => {
  it("signs in a demo operator by username and returns a read-only /me-shaped user", async () => {
    const session = await mockAuthAdapter.signIn({ username: "operator", password: "argus-demo" });
    expect(session.user).toEqual({
      name: "operator",
      role: "operator",
      access: "read",
      actions: ["view_incidents", "view_timeline", "view_evidence"],
    });
  });

  it("knows only the Argus roles: viewer, operator, approver (no admin)", async () => {
    const viewer = await mockAuthAdapter.signIn({ username: "viewer", password: "argus-demo" });
    const approver = await mockAuthAdapter.signIn({ username: "approver", password: "argus-demo" });
    expect(viewer.user.role).toBe("viewer");
    expect(approver.user.role).toBe("approver");
    await expect(mockAuthAdapter.signIn({ username: "admin", password: "argus-demo" })).rejects.toThrow();
  });

  it("gives a viewer no evidence, like the server", async () => {
    const { user } = await mockAuthAdapter.signIn({ username: "viewer", password: "argus-demo" });
    expect(user.actions).toEqual(["view_incidents", "view_timeline"]);
  });

  it("never grants a write action to a read token (ACR-0001)", async () => {
    for (const username of ["viewer", "operator", "approver"]) {
      const { user } = await mockAuthAdapter.signIn({ username, password: "argus-demo" });
      expect(user.access).toBe("read");
      expect(user.actions).not.toContain("start_investigation");
    }
  });

  it("rejects a wrong password with a message that is safe to show", async () => {
    await expect(mockAuthAdapter.signIn({ username: "operator", password: "nope" })).rejects.toThrow(
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
