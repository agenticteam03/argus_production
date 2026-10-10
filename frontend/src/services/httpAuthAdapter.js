// The real login: POST /api/v1/auth/token (form-encoded, scope=read), then GET /api/v1/me.
// The token stays in memory only (./session.js); there is no logout route, so signing out is forgetting it.
import { apiFetch, httpError } from "./http.js";
import { clearToken, setToken } from "./session.js";

const BAD_CREDENTIALS = "Incorrect username or password. Please try again.";

export const httpAuthAdapter = {
  async signIn({ username, password }) {
    const res = await fetch("/api/v1/auth/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ username, password, scope: "read" }),
    });
    if (res.status === 401) throw httpError(401, BAD_CREDENTIALS);
    if (!res.ok) throw httpError(res.status, "Could not log in. Please try again.");

    const { access_token: token } = await res.json();
    setToken(token);
    try {
      // Build the user from /me: Argus decides permissions; the UI never does (ACR-0001).
      const me = await (await apiFetch("/api/v1/me")).json();
      return { user: { name: me.user, role: me.role, access: me.access, actions: me.actions ?? [] } };
    } catch (err) {
      clearToken();
      throw err.status === 401 ? httpError(401, BAD_CREDENTIALS) : err;
    }
  },

  async signOut() {
    clearToken();
  },
};
