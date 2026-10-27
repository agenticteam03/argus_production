import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { httpAuthAdapter } from "./httpAuthAdapter.js";
import { httpArgusAdapter } from "./httpArgusAdapter.js";
import { clearToken, getToken, setToken } from "./session.js";
import { clearSession, loadSession, saveSession } from "./sessionStore.js";
import { actionsStep } from "./actionsStep.js";

const response = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
const stubStorage = () => {
  const mem = new Map();
  globalThis.sessionStorage = {
    getItem: (k) => (mem.has(k) ? mem.get(k) : null),
    setItem: (k, v) => mem.set(k, String(v)),
    removeItem: (k) => mem.delete(k),
  };
};
const ME_OPS = { user: "alice", role: "approver", access: "ops", actions: ["view_incidents"],
  second_factor: { enrolled: 2, verified: false } };

describe("ACR-0032 private login in the UI", () => {
  beforeEach(() => { globalThis.fetch = vi.fn(); clearToken(); stubStorage(); });
  afterEach(() => { clearToken(); clearSession(); delete globalThis.sessionStorage; vi.restoreAllMocks(); });

  it("ends the public session, keeps the ops token in memory only and forgets the stored session", async () => {
    setToken("public-jwt");
    saveSession({ user: { name: "alice" }, token: "public-jwt" });
    fetch
      .mockResolvedValueOnce(response(200, { access_token: "ops-jwt", access: "ops" }))       // private login
      .mockResolvedValueOnce(response(200, { ended: true }))                                  // then the public logout
      .mockResolvedValueOnce(response(200, ME_OPS));                                          // /me

    const session = await httpAuthAdapter.signInPrivate({ username: "alice", password: "s3cret" });

    const [logoutUrl, logoutInit] = fetch.mock.calls[1];
    expect(logoutUrl).toBe("/api/v1/auth/logout");
    expect(logoutInit.headers.Authorization).toBe("Bearer public-jwt");                       // the replaced token
    const [loginUrl, loginInit] = fetch.mock.calls[0];
    expect(loginUrl).toBe("/api/v1/ops/auth/token");
    expect(String(loginInit.body)).toBe("username=alice&password=s3cret");                   // no scope: full
    expect(fetch.mock.calls[2][1].headers.Authorization).toBe("Bearer ops-jwt");
    expect(getToken()).toBe("ops-jwt");
    expect(loadSession()).toBeNull();                       // a reload returns to the public login
    expect(session.user).toMatchObject({ name: "alice", access: "ops", secondFactor: { verified: false } });
    expect(globalThis.sessionStorage.getItem("argus.session")).toBeNull();
  });

  it("keeps the public session when the private login is refused", async () => {
    setToken("public-jwt");
    fetch.mockResolvedValueOnce(response(401, {}));
    await expect(httpAuthAdapter.signInPrivate({ username: "alice", password: "no" })).rejects.toMatchObject({
      status: 401 });
    expect(getToken()).toBe("public-jwt");
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/ops/auth/token");                          // nothing ended first
  });

  it("re-reads /me after the security key, without storing an ops session", async () => {
    setToken("ops-jwt");
    fetch.mockResolvedValueOnce(response(200, { ...ME_OPS, actions: ["approve_action"],
      second_factor: { enrolled: 2, verified: true } }));
    const session = await httpAuthAdapter.refresh();
    expect(session.user.actions).toContain("approve_action");
    expect(loadSession()).toBeNull();
  });

  it("lists the pending approvals", async () => {
    setToken("ops-jwt");
    fetch.mockResolvedValueOnce(response(200, [{ id: "appr_1" }]));
    expect(await httpArgusAdapter.listApprovals()).toEqual([{ id: "appr_1" }]);
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/ops/approvals");
  });
});

describe("actionsStep", () => {
  it("leads an approver from the private login to the key to the decisions", () => {
    expect(actionsStep({ role: "approver", access: "investigate", actions: [] })).toBe("private-login");
    expect(actionsStep({ role: "approver", access: "ops", actions: [], secondFactor: { verified: false } }))
      .toBe("second-factor");
    expect(actionsStep({ role: "approver", access: "ops", actions: ["approve_action"],
      secondFactor: { verified: true } })).toBe("ready");
    expect(actionsStep({ role: "approver", access: "ops", actions: [], secondFactor: { verified: true } }))
      .toBe("not-granted");                                 // the key is confirmed but the server grants nothing
    expect(actionsStep({ role: "operator", access: "investigate", actions: [] })).toBe("not-granted");
  });
});
