// The real login: POST /api/v1/auth/token (form-encoded, scope=investigate; ACR-0012), then GET /api/v1/me.
// The token is never put in `localStorage`, cookies or the URL (T-0016 rule 4): it lives in memory (./session.js)
// and, so a reload does not log the user out, in this tab's `sessionStorage` (./sessionStore.js). There is no
// logout route, so signing out is forgetting it.
import { apiFetch, httpError } from "./http.js";
import { clearToken, setToken } from "./session.js";
import { clearSession, loadSession, saveSession } from "./sessionStore.js";

const BAD_CREDENTIALS = "Incorrect username or password. Please try again.";

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
      // Build the user from /me: Argus decides permissions; the UI never does (ACR-0001).
      const me = await (await apiFetch("/api/v1/me")).json();
      const user = { name: me.user, role: me.role, access: me.access, actions: me.actions ?? [] };
      saveSession({ user, token });
      return { user };
    } catch (err) {
      clearToken();
      clearSession();
      throw err.status === 401 ? httpError(401, BAD_CREDENTIALS) : err;
    }
  },

  async signOut() {
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
