import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { demoSession, resetDemoKeys } from "./demoSession.js";
import { httpSecondFactorAdapter, mockSecondFactorAdapter, registerObject } from "./secondFactorAdapter.js";
import { clearToken, setToken } from "./session.js";

const response = (status, body) => ({ ok: status >= 200 && status < 300, status, json: async () => body });
const bytes = (...n) => new Uint8Array(n);
const sent = (i) => JSON.parse(fetch.mock.calls[i][1].body);

// A fake authenticator: what navigator.credentials returns, and what it was asked.
const fakeKeys = () => ({
  create: vi.fn(async () => ({ id: "Bwg", rawId: bytes(7, 8), type: "public-key",
    response: { clientDataJSON: bytes(1), attestationObject: bytes(2) } })),
  get: vi.fn(async () => ({ id: "Bwg", rawId: bytes(7, 8), type: "public-key",
    response: { clientDataJSON: bytes(1), authenticatorData: bytes(3), signature: bytes(4), userHandle: null } })),
});
const OPTIONS = { challenge_id: "wch_1", options: { challenge: "AQID", user: { id: "BAU", name: "alice" }, allowCredentials: [] } };

describe("httpSecondFactorAdapter", () => {
  beforeEach(() => { globalThis.fetch = vi.fn(); setToken("jwt-1"); });
  afterEach(() => { clearToken(); vi.restoreAllMocks(); });

  it("reads the status from /me, null when the API has no second factor", async () => {
    fetch.mockResolvedValueOnce(response(200, { user: "alice", second_factor: { enrolled: 1, verified: false } }))
      .mockResolvedValueOnce(response(200, { user: "alice", second_factor: null }));
    expect(await httpSecondFactorAdapter.status()).toEqual({ enrolled: 1, verified: false });
    expect(await httpSecondFactorAdapter.status()).toBeNull();
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/me");
  });

  it("enrols a first key with the code: options, the authenticator's create(), then verify with the label", async () => {
    const keys = fakeKeys();
    fetch.mockResolvedValueOnce(response(200, OPTIONS)).mockResolvedValueOnce(response(200, { credential: "Bwg", enrolled: 1 }));
    expect(await httpSecondFactorAdapter.enrol({ ticket: "code-1", label: "laptop" }, keys)).toEqual({ credential: "Bwg", enrolled: 1 });
    expect(fetch.mock.calls.map((c) => [c[1].method, c[0]])).toEqual([
      ["POST", "/api/v1/auth/webauthn/register/options"], ["POST", "/api/v1/auth/webauthn/register/verify"]]);
    expect(sent(0)).toEqual({ ticket: "code-1" });
    expect([...keys.create.mock.calls[0][0].publicKey.challenge]).toEqual([1, 2, 3]);
    expect(sent(1)).toMatchObject({ challenge_id: "wch_1", label: "laptop",
      credential: { id: "Bwg", rawId: "Bwg", response: { attestationObject: "Ag" } } });
    expect(fetch.mock.calls[1][1].headers).toMatchObject({ Authorization: "Bearer jwt-1", "Content-Type": "application/json" });
  });

  it("enrols a further key with a step-up token instead of a code", async () => {
    fetch.mockResolvedValueOnce(response(200, OPTIONS)).mockResolvedValueOnce(response(200, { enrolled: 2 }));
    await httpSecondFactorAdapter.enrol({ stepUpToken: "su-1" }, fakeKeys());
    expect(sent(0)).toEqual({ step_up_token: "su-1" });
  });

  it("confirms the login with an assertion", async () => {
    const keys = fakeKeys();
    fetch.mockResolvedValueOnce(response(200, OPTIONS)).mockResolvedValueOnce(response(200, { verified: true }));
    expect(await httpSecondFactorAdapter.confirmLogin(keys)).toEqual({ verified: true });
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/auth/webauthn/login/options");
    expect(fetch.mock.calls[0][1]).not.toHaveProperty("body");
    expect(sent(1).credential.response).toEqual({ clientDataJSON: "AQ", authenticatorData: "Aw", signature: "BA" });
  });

  it("takes a step-up for one object and returns its token", async () => {
    fetch.mockResolvedValueOnce(response(200, OPTIONS))
      .mockResolvedValueOnce(response(200, { step_up_token: "su-9", expires_at: "2026-10-22T16:05:00Z" }));
    const out = await httpSecondFactorAdapter.stepUp(registerObject("alice"), fakeKeys());
    expect(sent(0)).toEqual({ object: "webauthn.register:alice" });
    expect(out).toEqual({ token: "su-9", expiresAt: "2026-10-22T16:05:00Z" });
  });

  it("surfaces the API's reason when a ceremony is refused", async () => {
    fetch.mockResolvedValueOnce(response(403, { detail: "the first credential needs an enrolment ticket from another administrator" }));
    await expect(httpSecondFactorAdapter.enrol({ ticket: "" }, fakeKeys())).rejects.toMatchObject({
      status: 403, detail: "the first credential needs an enrolment ticket from another administrator" });
  });

  it("lists the caller's keys", async () => {
    fetch.mockResolvedValueOnce(response(200, [{ credential: "Bwg", label: "laptop" }]));
    expect(await httpSecondFactorAdapter.credentials()).toEqual([{ credential: "Bwg", label: "laptop" }]);
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/auth/webauthn/credentials");
  });
});

describe("mockSecondFactorAdapter", () => {
  it("gives the demo a security keys page: an approver's two keys, a viewer none (T-0016)", async () => {
    resetDemoKeys();
    demoSession.role = "approver";
    expect(await mockSecondFactorAdapter.status()).toEqual({ enrolled: 2, verified: false });
    expect((await mockSecondFactorAdapter.credentials()).map((k) => k.label)).toEqual(["Laptop passkey", "Phone passkey"]);
    demoSession.role = "viewer";
    expect(await mockSecondFactorAdapter.status()).toEqual({ enrolled: 0, verified: false });
    demoSession.role = null;
    expect(await mockSecondFactorAdapter.status()).toBeNull();
  });

  it("registers a first key with a code, a further one after a step-up, as the real ceremonies ask", async () => {
    resetDemoKeys();
    demoSession.role = "viewer";
    await expect(mockSecondFactorAdapter.enrol({ label: "Laptop" })).rejects.toThrow(/code/);
    await mockSecondFactorAdapter.enrol({ ticket: "DEMO-1234", label: "Laptop" });
    const { token } = await mockSecondFactorAdapter.stepUp("webauthn.register:viewer");
    await mockSecondFactorAdapter.enrol({ stepUpToken: token, label: "Phone" });
    expect(await mockSecondFactorAdapter.status()).toEqual({ enrolled: 2, verified: false });
    demoSession.role = null;
    resetDemoKeys();
  });

  it("simulates confirming the private session with a key, for the demo's console and Actions (T-0016)", async () => {
    demoSession.keyConfirmed = false;
    expect(await mockSecondFactorAdapter.confirmLogin()).toEqual({ verified: true });
    expect(demoSession.keyConfirmed).toBe(true);
    demoSession.keyConfirmed = false;
  });
});
