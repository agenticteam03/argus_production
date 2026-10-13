import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearSession, loadSession, saveSession } from "./mockSessionStore.js";

const KEY = "argus.session";

// Node has no sessionStorage, so the store falls back to "never persist". These tests provide a tiny fake.
const stubStorage = () => {
  const mem = new Map();
  globalThis.sessionStorage = {
    getItem: (k) => (mem.has(k) ? mem.get(k) : null),
    setItem: (k, v) => mem.set(k, String(v)),
    removeItem: (k) => mem.delete(k),
  };
  return mem;
};

describe("mockSessionStore", () => {
  let mem;
  beforeEach(() => {
    mem = stubStorage();
  });
  afterEach(() => {
    delete globalThis.sessionStorage;
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("saves a session and loads it back inside its TTL", () => {
    saveSession({ name: "ana", role: "operator" });

    expect(loadSession()).toEqual({ name: "ana", role: "operator" });
    expect(mem.has(KEY)).toBe(true);
  });

  it("returns null (and clears) when the session is missing, corrupt or expired", () => {
    expect(loadSession()).toBeNull();

    mem.set(KEY, "not json");
    expect(loadSession()).toBeNull();

    mem.set(KEY, JSON.stringify({ user: { name: "ana" }, expiresAt: Date.now() - 1 }));
    expect(loadSession()).toBeNull();
    expect(mem.has(KEY)).toBe(false);
  });

  it("forgets the session on logout", () => {
    saveSession({ name: "ana", role: "viewer" });
    clearSession();

    expect(loadSession()).toBeNull();
    expect(mem.has(KEY)).toBe(false);
  });

  it("honours VITE_ARGUS_SESSION_TTL_MIN", async () => {
    vi.resetModules();
    vi.stubEnv("VITE_ARGUS_SESSION_TTL_MIN", "2");
    const store = await import("./mockSessionStore.js");

    store.saveSession({ name: "ana" });
    const { expiresAt } = JSON.parse(mem.get(KEY));

    expect(expiresAt).toBeGreaterThan(Date.now() + 60_000);
    expect(expiresAt).toBeLessThanOrEqual(Date.now() + 120_000);
  });

  it("never persists when there is no sessionStorage (SSR / Node)", () => {
    delete globalThis.sessionStorage;
    expect(() => saveSession({ name: "ana" })).not.toThrow();
    expect(loadSession()).toBeNull();
  });
});
