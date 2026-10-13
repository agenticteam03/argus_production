// The signed-in session survives a page reload in this tab: it is kept in `sessionStorage` — never
// `localStorage`, cookies or the URL — and ends on logout, when the tab closes, or when it expires.
// A mock session carries no token; a real API session also carries the read-scoped bearer token, so a reload
// does not force a new login. The server-side JWT expiry still wins: once past it the token is dropped and the
// next 401 returns to login through the usual path.
const KEY = "argus.session";
const DEFAULT_TTL_MIN = 480;

const ttlMs = () => {
  const min = Number(import.meta.env.VITE_ARGUS_SESSION_TTL_MIN);
  return (Number.isFinite(min) && min > 0 ? min : DEFAULT_TTL_MIN) * 60_000;
};

// Node (the unit tests) has no sessionStorage; callers then simply never persist.
const storage = () => (typeof sessionStorage === "undefined" ? null : sessionStorage);

// A JWT's own `exp` (seconds since epoch) is the real end of a token's life. Decode it without a library so a
// restored token is never one the server will reject; any malformed token simply falls back to our TTL.
const tokenExpiry = (token) => {
  try {
    const part = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const pad = part.length % 4 ? "=".repeat(4 - (part.length % 4)) : "";
    const { exp } = JSON.parse(atob(part + pad));
    return typeof exp === "number" ? exp * 1000 : null;
  } catch {
    return null;
  }
};

// `user` is the `/me`-shaped user; `token` is set only for a real API session.
export const saveSession = ({ user, token = null }) => {
  const store = storage();
  if (!store) return;
  try {
    const ttl = Date.now() + ttlMs();
    const exp = token ? tokenExpiry(token) : null;
    store.setItem(KEY, JSON.stringify({ user, token, expiresAt: exp ? Math.min(ttl, exp) : ttl }));
  } catch {
    /* storage blocked or full: the session simply will not survive a reload */
  }
};

export const loadSession = () => {
  const store = storage();
  if (!store) return null;
  try {
    const raw = store.getItem(KEY);
    if (!raw) return null;
    const { user, token, expiresAt } = JSON.parse(raw);
    if (!user || typeof expiresAt !== "number" || expiresAt <= Date.now()) {
      store.removeItem(KEY);
      return null;
    }
    return { user, token: token ?? null };
  } catch {
    store.removeItem(KEY);
    return null;
  }
};

export const clearSession = () => {
  const store = storage();
  try {
    store?.removeItem(KEY);
  } catch {
    /* ignore */
  }
};
