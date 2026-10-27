// The real login: POST /api/v1/auth/token (form-encoded, scope=investigate; ACR-0012), then GET /api/v1/me.
// The token is never put in `localStorage`, cookies or the URL (T-0016 rule 4): it lives in memory (./session.js)
// and, so a reload does not log the user out, in this tab's `sessionStorage` (./sessionStore.js). Signing out ends
// the session on the server (POST /api/v1/auth/logout, ACR-0018), then forgets the token.
import { apiFetch, httpError } from "./http.js";
import { clearToken, getToken, setToken } from "./session.js";
import { clearSession, loadSession, saveSession } from "./sessionStore.js";

const BAD_CREDENTIALS = "Incorrect username or password. Please try again.";

// Build the user from /me: Argus decides permissions; the UI never does (ACR-0001).
const userFrom = (me) => ({ name: me.user, role: me.role, access: me.access, actions: me.actions ?? [],
  secondFactor: me.second_factor ?? undefined });

export const httpAuthAdapter = {
  async signIn({ username, password }) {
    const res = await fetch("/api/v1/auth/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      // ACR-0012: an investigate token reads like a read token and may start an investigation (the one POST);
      // /me lists start_investigation only for an operator or approver, so a viewer sees no button.
      body: new URLSearchParams({ username, password, scope: "investigate" }),
    });
    if (res.status === 401) throw httpError(401, BAD_CREDENTIALS);
    if (!res.ok) throw httpError(res.status, "Could not log in. Please try again.");

    const { access_token: token } = await res.json();
    setToken(token);
    try {
      const user = userFrom(await (await apiFetch("/api/v1/me")).json());
      saveSession({ user, token });
      return { user };
    } catch (err) {
      clearToken();
      clearSession();
      throw err.status === 401 ? httpError(401, BAD_CREDENTIALS) : err;
    }
  },

  // ACR-0032: the private login, only reachable on the private path. Its `ops` token replaces the public one in
  // memory and is never stored: the public session is ended on the server and its stored copy forgotten, so a reload
  // or the session's end (15 minutes idle, one hour at most) return to the public login.
  async signInPrivate({ username, password }) {
    const res = await fetch("/api/v1/ops/auth/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username, password }),
    });
    if (res.status === 401) throw httpError(401, BAD_CREDENTIALS);
    if (res.status === 404) throw httpError(404, "The private login is reachable only on the private path.");
    if (!res.ok) throw httpError(res.status, "Could not log in privately. Please try again.");
    const { access_token: token } = await res.json();
    if (getToken()) {
      try {
        await apiFetch("/api/v1/auth/logout", { method: "POST" });     // ACR-0018: the public token ends now
      } catch {
        // replaced below anyway
      }
    }
    clearSession();
    setToken(token);
    try {
      return { user: userFrom(await (await apiFetch("/api/v1/me")).json()) };
    } catch (err) {
      clearToken();
      throw err.status === 401 ? httpError(401, BAD_CREDENTIALS) : err;
    }
  },

  // Re-read /me (after the security key completes the session). A private session is never stored.
  async refresh() {
    const user = userFrom(await (await apiFetch("/api/v1/me")).json());
    if (user.access !== "ops") saveSession({ user, token: getToken() });
    return { user };
  },

  async signOut() {
    // ACR-0018: end the session on the server first, so the token is refused even if it was copied. Best effort:
    // the token is forgotten whatever the answer (an older API answers 404, an ended session 401, or no network).
    if (getToken()) {
      try {
        await apiFetch("/api/v1/auth/logout", { method: "POST" });
      } catch {
        // forgotten below anyway
      }
    }
    clearToken();
    clearSession();
  },

  // Bring the session (and the token) back after a page reload in the same tab. The token's own JWT `exp` bounds
  // it, and the next 401 still logs the user out, so a stale token cannot linger.
  restore() {
    const session = loadSession();
    if (!session?.token) return null;
    setToken(session.token);
    return { user: session.user };
  },
};
