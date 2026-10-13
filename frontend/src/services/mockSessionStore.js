// The mock session survives a page reload in this tab: it is kept in `sessionStorage` — never `localStorage`,
// cookies or the URL. It holds no token (mock logins are local), so T-0016 rule 4 ("token in memory only") is
// untouched; the real API token is still only in ./session.js.
// It ends on logout, when the tab closes, or when its TTL (`VITE_ARGUS_SESSION_TTL_MIN`, default 8 h) elapses.
const KEY = "argus.session";
const DEFAULT_TTL_MIN = 480;

const ttlMs = () => {
  const min = Number(import.meta.env.VITE_ARGUS_SESSION_TTL_MIN);
  return (Number.isFinite(min) && min > 0 ? min : DEFAULT_TTL_MIN) * 60_000;
};

// Node (the unit tests) has no sessionStorage; callers then simply never persist.
const storage = () => (typeof sessionStorage === "undefined" ? null : sessionStorage);

export const saveSession = (user) => {
  const store = storage();
  if (!store) return;
  try {
    store.setItem(KEY, JSON.stringify({ user, expiresAt: Date.now() + ttlMs() }));
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
    const { user, expiresAt } = JSON.parse(raw);
    if (!user || typeof expiresAt !== "number" || expiresAt <= Date.now()) {
      store.removeItem(KEY);
      return null;
    }
    return user;
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
