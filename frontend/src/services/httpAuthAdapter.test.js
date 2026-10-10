import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { httpAuthAdapter } from "./httpAuthAdapter.js";
import { clearToken, getToken } from "./session.js";

// Minimal stand-in for the parts of a fetch Response the adapters use.
const response = (status, body) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => body,
});

describe("httpAuthAdapter", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn();
    clearToken();
  });
  afterEach(() => {
    clearToken();
    vi.restoreAllMocks();
  });

  it("logs in with a form-encoded read token, then reads the user from /me", async () => {
    fetch
      .mockResolvedValueOnce(response(200, { access: "read", access_token: "jwt-123", token_type: "bearer" }))
      .mockResolvedValueOnce(response(200, { access: "read", actions: ["view_incidents"], role: "operator", user: "alice" }));

    const session = await httpAuthAdapter.signIn({ username: "alice", password: "s3cret" });

    const [loginUrl, loginInit] = fetch.mock.calls[0];
    expect(loginUrl).toBe("/api/v1/auth/token");
    expect(loginInit.method).toBe("POST");
    expect(loginInit.headers["Content-Type"]).toBe("application/x-www-form-urlencoded");
    expect(String(loginInit.body)).toBe("username=alice&password=s3cret&scope=read");

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

  it("signOut forgets the in-memory token", async () => {
    fetch
      .mockResolvedValueOnce(response(200, { access_token: "jwt-123" }))
      .mockResolvedValueOnce(response(200, { access: "read", actions: [], role: "viewer", user: "alice" }));

    await httpAuthAdapter.signIn({ username: "alice", password: "x" });
    await httpAuthAdapter.signOut();
    expect(getToken()).toBeNull();
  });
});
