import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { httpAuthAdapter } from "./httpAuthAdapter.js";
import { clearToken, getToken } from "./session.js";
import { clearSession } from "./sessionStore.js";

// Minimal stand-in for the parts of a fetch Response the adapters use.
const response = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
});

// Node has no sessionStorage, so the store would never persist; a tiny fake makes restore/signOut testable.
const stubStorage = () => {
  const mem = new Map();
  globalThis.sessionStorage = {
    getItem: (k) => (mem.has(k) ? mem.get(k) : null),
    setItem: (k, v) => mem.set(k, String(v)),
    removeItem: (k) => mem.delete(k),
  };
};

// A successful sign-in needs two calls: the token, then /me.
const signInOk = () =>
  fetch
    .mockResolvedValueOnce(response(200, { access: "read", access_token: "jwt-123", token_type: "bearer" }))
    .mockResolvedValueOnce(response(200, { access: "read", actions: ["view_incidents"], role: "operator", user: "alice" }));

describe("httpAuthAdapter", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn();
    clearToken();
    stubStorage();
  });
  afterEach(() => {
    clearToken();
    clearSession();
    delete globalThis.sessionStorage;
    vi.restoreAllMocks();
  });

  it("logs in with a form-encoded read token, then reads the user from /me", async () => {
    signInOk();

    const session = await httpAuthAdapter.signIn({ username: "alice", password: "s3cret" });

    const [loginUrl, loginInit] = fetch.mock.calls[0];
    expect(loginUrl).toBe("/api/v1/auth/token");
    expect(loginInit.method).toBe("POST");
    expect(loginInit.headers["Content-Type"]).toBe("application/x-www-form-urlencoded");
    expect(String(loginInit.body)).toBe("username=alice&password=s3cret&scope=investigate");   // ACR-0012

    const [meUrl, meInit] = fetch.mock.calls[1];
    expect(meUrl).toBe("/api/v1/me");
    expect(meInit.headers.Authorization).toBe("Bearer jwt-123");

    expect(session).toEqual({ user: { name: "alice", role: "operator", access: "read", actions: ["view_incidents"] } });
    expect(getToken()).toBe("jwt-123");
  });

  it("rejects bad credentials on 401 and keeps no token", async () => {
    fetch.mockResolvedValueOnce(response(401, {}));

    await expect(httpAuthAdapter.signIn({ username: "alice", password: "no" })).rejects.toMatchObject({
      status: 401,
      message: "Incorrect username or password. Please try again.",
    });
    expect(getToken()).toBeNull();
  });

  it("forgets the token when /me rejects it", async () => {
    fetch.mockResolvedValueOnce(response(200, { access_token: "jwt-123" })).mockResolvedValueOnce(response(401, {}));

    await expect(httpAuthAdapter.signIn({ username: "alice", password: "x" })).rejects.toMatchObject({ status: 401 });
    expect(getToken()).toBeNull();
  });

  it("restores the session and the token after a page reload", async () => {
    signInOk();
    await httpAuthAdapter.signIn({ username: "alice", password: "x" });

    clearToken(); // a reload forgets the in-memory token, but the tab still remembers the session
    const session = httpAuthAdapter.restore();

    expect(session).toEqual({ user: { name: "alice", role: "operator", access: "read", actions: ["view_incidents"] } });
    expect(getToken()).toBe("jwt-123");
  });

  it("restores nothing when there is no session", () => {
    expect(httpAuthAdapter.restore()).toBeNull();
  });

  it("signOut forgets the in-memory token and the restored session", async () => {
    signInOk();
    await httpAuthAdapter.signIn({ username: "alice", password: "x" });

    await httpAuthAdapter.signOut();

    expect(getToken()).toBeNull();
    expect(httpAuthAdapter.restore()).toBeNull();
  });
});
