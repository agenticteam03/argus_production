// Small shared HTTP helper for the real API adapters.
// It attaches the in-memory bearer token and turns any 401 into a logout: the caller sees a 401 error
// and the token is already forgotten, so the next call cannot succeed either (`docs/API-FOR-UI.md`).
import { clearToken, getToken } from "./session.js";
import { clearSession } from "./sessionStore.js";

export const httpError = (status, message) => Object.assign(new Error(message), { status });

export async function apiFetch(path, options = {}) {
  const headers = { ...(options.headers ?? {}) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(path, { ...options, headers });
  if (res.status === 401) {
    clearToken();
    clearSession();
    throw httpError(401, "Your session expired. Please log in again.");
  }
  if (!res.ok) {
    // ACR-0012: a quota answer (429) says when to try again
    const err = httpError(res.status, `Request failed (${res.status}).`);
    const wait = Number(res.headers?.get?.("Retry-After"));
    if (Number.isFinite(wait) && wait > 0) err.retryAfter = wait;
    // The API's own reason, when it gives a short text one (e.g. a refused second-factor ceremony, ACR-0018)
    try {
      const detail = (await res.json())?.detail;
      if (typeof detail === "string" && detail.length <= 300) err.detail = detail;
    } catch {
      // no JSON body: the generic message stands
    }
    throw err;
  }
  return res;
}
