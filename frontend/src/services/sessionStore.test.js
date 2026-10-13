import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearSession, loadSession, saveSession, tokenExpiry } from "./sessionStore.js";

const KEY = "argus.session";

// A JWT-shaped string whose payload carries `exp` (seconds since epoch); the signature is irrelevant here.
const jwt = (exp) => {
  const b64 = (o) => btoa(JSON.stringify(o)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  return `${b64({ alg: "HS256", typ: "JWT" })}.${b64({ exp })}.sig`;
};
const inSeconds = (ms) => Math.floor(ms / 1000);

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

describe("sessionStore", () => {
  let mem;
  beforeEach(() => {
    mem = stubStorage();
  });
  afterEach(() => {
    delete globalThis.sessionStorage;
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("saves a mock session (no token) and loads it back inside its TTL", () => {
    saveSession({ user: { name: "ana", role: "operator" } });

    expect(loadSession()).toEqual({ user: { name: "ana", role: "operator" }, token: null });
    expect(mem.has(KEY)).toBe(true);
  });

  it("round-trips the real API token so a reload does not log the user out", () => {
    const token = jwt(inSeconds(Date.now()) + 600);
    saveSession({ user: { name: "ana", role: "operator" }, token });

    expect(loadSession()).toEqual({ user: { name: "ana", role: "operator" }, token });
  });

  it("drops a token whose own JWT exp has passed, even when our TTL has not", () => {
    saveSession({ user: { name: "ana" }, token: jwt(inSeconds(Date.now()) - 1) });

    expect(loadSession()).toBeNull();
    expect(mem.has(KEY)).toBe(false);
  });

  it("reads a token's own exp, and returns null for a malformed token", () => {
    expect(tokenExpiry(jwt(1_700_000_000))).toBe(1_700_000_000_000);
    expect(tokenExpiry("not-a-jwt")).toBeNull();
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
    saveSession({ user: { name: "ana", role: "viewer" } });
    clearSession();

    expect(loadSession()).toBeNull();
    expect(mem.has(KEY)).toBe(false);
  });

  it("honours VITE_ARGUS_SESSION_TTL_MIN", async () => {
    vi.resetModules();
    vi.stubEnv("VITE_ARGUS_SESSION_TTL_MIN", "2");
    const store = await import("./sessionStore.js");

    store.saveSession({ user: { name: "ana" } });
    const { expiresAt } = JSON.parse(mem.get(KEY));

    expect(expiresAt).toBeGreaterThan(Date.now() + 60_000);
    expect(expiresAt).toBeLessThanOrEqual(Date.now() + 120_000);
  });

  it("never persists when there is no sessionStorage (SSR / Node)", () => {
    delete globalThis.sessionStorage;
    expect(() => saveSession({ user: { name: "ana" } })).not.toThrow();
    expect(loadSession()).toBeNull();
  });
});
