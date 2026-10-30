import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { demoSession } from "./demoSession.js";
import { mockAuthAdapter } from "./mockAuthAdapter.js";
import { mockSecondFactorAdapter } from "./secondFactorAdapter.js";

// Node has no sessionStorage, so the store would never persist. These tests provide a tiny fake.
const mem = new Map();
const stubStorage = () => {
  globalThis.sessionStorage = {
    getItem: (k) => (mem.has(k) ? mem.get(k) : null),
    setItem: (k, v) => mem.set(k, String(v)),
    removeItem: (k) => mem.delete(k),
  };
};

beforeEach(() => {
  demoSession.role = null;
  mem.clear();
  stubStorage();
});
afterEach(() => {
  delete globalThis.sessionStorage;
  vi.unstubAllEnvs();
  vi.resetModules();
});

describe("mockAuthAdapter", () => {
  it("signs in the demo approver with the /me-shaped user", async () => {
    const session = await mockAuthAdapter.signIn({ username: "approver", password: "argus-demo" });
    expect(session.user).toEqual({
      name: "approver",
      role: "approver",
      access: "read",
      actions: ["view_incidents", "view_timeline", "view_evidence"],
      secondFactor: { enrolled: 2, verified: false },
    });
  });

  it("maps operator and viewer demo accounts to their roles", async () => {
    const op = await mockAuthAdapter.signIn({ username: "operator", password: "argus-demo" });
    const viewer = await mockAuthAdapter.signIn({ username: "viewer", password: "argus-demo" });
    expect(op.user.role).toBe("operator");
    expect(viewer.user.role).toBe("viewer");
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

  it("keeps the session across a reload and forgets it on logout", async () => {
    await mockAuthAdapter.signIn({ username: "operator", password: "argus-demo" });

    // `restore` is what a fresh page load runs: it brings the session back from the tab's sessionStorage.
    expect(mockAuthAdapter.restore()).toEqual({
      user: { name: "operator", role: "operator", access: "read", actions: ["view_incidents", "view_timeline", "view_evidence"],
        secondFactor: { enrolled: 2, verified: false } },
    });

    await mockAuthAdapter.signOut();
    expect(mockAuthAdapter.restore()).toBeNull();
  });

  it("takes the accounts from VITE_ARGUS_USERS so a login needs no database", async () => {
    vi.resetModules();
    vi.stubEnv("VITE_ARGUS_USERS", JSON.stringify({ ana: { password: "s3cret-pass", role: "operator" } }));
    const { mockAuthAdapter: adapter } = await import("./mockAuthAdapter.js");

    const { user } = await adapter.signIn({ username: "Ana", password: "s3cret-pass" });
    expect(user).toEqual({
      name: "ana",
      role: "operator",
      access: "read",
      actions: ["view_incidents", "view_timeline", "view_evidence"],
      secondFactor: { enrolled: 2, verified: false },
    });
    // The demo defaults are gone once the environment defines the accounts.
    await expect(adapter.signIn({ username: "viewer", password: "argus-demo" })).rejects.toThrow();
  });

  it("ignores a broken VITE_ARGUS_USERS and keeps the demo accounts", async () => {
    vi.resetModules();
    vi.stubEnv("VITE_ARGUS_USERS", "{not json");
    const { mockAuthAdapter: adapter } = await import("./mockAuthAdapter.js");

    await expect(adapter.signIn({ username: "viewer", password: "argus-demo" })).resolves.toBeDefined();
  });
});

describe("mockAuthAdapter, demo of the private login and the security key (ACR-0032, T-0016)", () => {
  beforeEach(() => { stubStorage(); mem.clear(); demoSession.keyConfirmed = false; });
  afterEach(async () => { await mockAuthAdapter.signOut(); delete globalThis.sessionStorage; });

  it("a viewer has no key, so the console's access dialog shows case 2", async () => {
    const { user } = await mockAuthAdapter.signIn({ username: "viewer", password: "argus-demo" });
    expect(user.secondFactor).toEqual({ enrolled: 0, verified: false });
  });

  it("opens a private session for the demo approver, then the simulated key confirms it", async () => {
    await mockAuthAdapter.signIn({ username: "approver", password: "argus-demo" });
    const { user } = await mockAuthAdapter.signInPrivate({ username: "approver", password: "argus-demo" });
    expect(user).toMatchObject({ access: "ops", secondFactor: { enrolled: 2, verified: false } });
    await mockSecondFactorAdapter.confirmLogin();
    const after = await mockAuthAdapter.refresh();
    expect(after.user).toMatchObject({ access: "ops", secondFactor: { enrolled: 2, verified: true } });
    expect(after.user.actions).toContain("approve_action");
  });

  it("refuses a private login to anyone but an approver, and to a wrong password", async () => {
    await expect(mockAuthAdapter.signInPrivate({ username: "operator", password: "argus-demo" })).rejects.toThrow();
    await expect(mockAuthAdapter.signInPrivate({ username: "approver", password: "nope" })).rejects.toThrow();
  });

  it("keeps the private session in memory only: a reload returns to the ordinary one", async () => {
    await mockAuthAdapter.signIn({ username: "approver", password: "argus-demo" });
    await mockAuthAdapter.signInPrivate({ username: "approver", password: "argus-demo" });
    expect(mockAuthAdapter.restore().user.access).toBe("read");
  });
});
