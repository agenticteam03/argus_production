// ACR-0018 phase 16 step 3: enrol a security key or passkey, complete this login with it, and take a step-up for
// one object. Each ceremony is the API's options, then the browser's authenticator, then the API's verify; the API
// decides (D4: the first key needs a code from another administrator; a further one a step-up of an enrolled key).
// `keys` is `navigator.credentials` (a parameter so the tests can pass a fake authenticator).
import { addDemoKey, demoKeysOf, demoSecondFactor, demoSession } from "./demoSession.js";
import { apiFetch } from "./http.js";
import { credentialToJSON, toCreationOptions, toRequestOptions } from "./webauthn.js";

const BASE = "/api/v1/auth/webauthn";
const browserKeys = () => globalThis.navigator?.credentials;
const post = async (path, body) =>
  (await apiFetch(`${BASE}/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  })).json();

export const registerObject = (user) => `webauthn.register:${user}`;

async function assert(kind, body, keys) {
  const { challenge_id: challengeId, options } = await post(`${kind}/options`, body);
  const cred = await keys.get({ publicKey: toRequestOptions(options) });
  return post(`${kind}/verify`, { challenge_id: challengeId, credential: credentialToJSON(cred) });
}

export const httpSecondFactorAdapter = {
  // `{enrolled, verified}`, or null when the API has no second factor configured
  async status() {
    return (await (await apiFetch("/api/v1/me")).json()).second_factor ?? null;
  },

  async credentials() {
    return (await apiFetch(`${BASE}/credentials`)).json();
  },

  async enrol({ ticket, stepUpToken, label = "" }, keys = browserKeys()) {
    const { challenge_id: challengeId, options } = await post("register/options", {
      ...(ticket ? { ticket } : {}), ...(stepUpToken ? { step_up_token: stepUpToken } : {}),
    });
    const cred = await keys.create({ publicKey: toCreationOptions(options) });
    return post("register/verify", { challenge_id: challengeId, credential: credentialToJSON(cred), label });
  },

  async confirmLogin(keys = browserKeys()) {
    return assert("login", undefined, keys);
  },

  // A single-use token for `object` (kind:reference), valid 5 minutes in this session; the privileged call takes it.
  async stepUp(object, keys = browserKeys()) {
    const { step_up_token: token, expires_at: expiresAt } = await assert("step-up", { object }, keys);
    return { token, expiresAt };
  },
};

// T-0016: the offline demo's security keys (demoSession.js), so the demo shows the Security keys page like the real UI:
// a first key needs a one-time code from an administrator (any code of 6+ characters here), a further one a step-up.
const demoWait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
export const mockSecondFactorAdapter = {
  status: async () => (demoSession.role ? demoSecondFactor(demoSession.role) : null),
  credentials: async () => (demoSession.role ? demoKeysOf(demoSession.role) : []),
  async enrol({ ticket, stepUpToken, label = "" } = {}) {
    await demoWait(400);
    const first = demoKeysOf(demoSession.role).length === 0;
    if (first && String(ticket ?? "").trim().length < 6) throw new Error("A first key needs the one-time code from your administrator.");
    if (!first && stepUpToken !== "demo-step-up") throw new Error("Confirm with a registered key first.");
    addDemoKey(demoSession.role, label || "Demo key");
    return { registered: true };
  },
  async stepUp() {
    await demoWait(300);
    if (!demoKeysOf(demoSession.role).length) throw new Error("No security key is registered yet.");
    return { token: "demo-step-up", expiresAt: new Date(Date.now() + 5 * 60_000).toISOString() };
  },
  // T-0016, demo: the simulated key confirms the private session (mockAuthAdapter.refresh reads it)
  confirmLogin: async () => {
    await new Promise((resolve) => setTimeout(resolve, 400));
    demoSession.keyConfirmed = true;
    return { verified: true };
  },
};
