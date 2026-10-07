import { describe, expect, it } from "vitest";
import { mockAuthAdapter } from "./mockAuthAdapter.js";

describe("mockAuthAdapter", () => {
  it("signs in a demo admin", async () => {
    const session = await mockAuthAdapter.signIn({ email: "admin@argus.dev", password: "argus-demo" });
    expect(session.user).toEqual({ email: "admin@argus.dev", role: "admin" });
  });

  it("maps operator and viewer demo accounts to their roles", async () => {
    const op = await mockAuthAdapter.signIn({ email: "operator@argus.dev", password: "argus-demo" });
    const vi = await mockAuthAdapter.signIn({ email: "viewer@argus.dev", password: "argus-demo" });
    expect(op.user.role).toBe("operator");
    expect(vi.user.role).toBe("viewer");
  });

  it("rejects a wrong password with a message that is safe to show", async () => {
    await expect(mockAuthAdapter.signIn({ email: "admin@argus.dev", password: "nope" })).rejects.toThrow(
      "Incorrect email or password. Please try again."
    );
  });

  it("rejects an unknown account", async () => {
    await expect(mockAuthAdapter.signIn({ email: "stranger@argus.dev", password: "argus-demo" })).rejects.toThrow();
  });

  it("signOut resolves without a session", async () => {
    await expect(mockAuthAdapter.signOut()).resolves.toBeUndefined();
  });
});
