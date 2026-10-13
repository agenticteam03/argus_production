// Frontend-only stand-in for the real auth API (POST /api/v1/auth/token + GET /api/v1/me), with no database:
// the accounts live in code (the demo defaults) or in `.env` (`VITE_ARGUS_USERS`), so the offline demo needs no
// server at all. The session survives a page reload in the same tab (./sessionStore.js); a mock login issues no
// token, so nothing secret is ever persisted.
import { demoSession } from "./demoSession.js";
import { clearSession, loadSession, saveSession } from "./sessionStore.js";

// Same shape GET /api/v1/me returns: the server lists the actions a read token may use.
const ROLE_ACTIONS = {
  viewer: ["view_incidents", "view_timeline"],
  operator: ["view_incidents", "view_timeline", "view_evidence"],
  approver: ["view_incidents", "view_timeline", "view_evidence"],
};

// Demo logins (password: argus-demo): approver, operator, viewer — the three Argus roles, never an admin.
const DEFAULT_USERS = {
  viewer: { password: "argus-demo", role: "viewer" },
  operator: { password: "argus-demo", role: "operator" },
  approver: { password: "argus-demo", role: "approver" },
};

// Optional no-database accounts from `.env`: a JSON map of username -> { password, role }.
// A bad value, a missing password or an unknown role is ignored, so the demo never breaks on a typo.
const parseUsers = (raw) => {
  if (!raw) return null;
  try {
    const rows = Object.entries(JSON.parse(raw)).filter(([, u]) => u && typeof u.password === "string" && ROLE_ACTIONS[u.role]);
    return rows.length ? Object.fromEntries(rows) : null;
  } catch {
    return null;
  }
};

// Usernames are matched case-insensitively; the configured spelling is the name the UI shows.
const USERS = Object.fromEntries(
  Object.entries(parseUsers(import.meta.env.VITE_ARGUS_USERS) ?? DEFAULT_USERS)
    .map(([name, u]) => [name.toLowerCase(), { name, role: u.role, password: u.password }])
);

const toUser = ({ name, role }) => ({ name, role, access: "read", actions: ROLE_ACTIONS[role] });

/** @type {import("./AuthPort.js").AuthPort} */
export const mockAuthAdapter = {
  async signIn({ username, password }) {
    await new Promise((resolve) => setTimeout(resolve, 700));
    const account = USERS[username?.toLowerCase()];
    if (!account || password !== account.password) throw new Error("Incorrect username or password. Please try again.");
    demoSession.role = account.role;
    const user = toUser(account);
    saveSession({ user });
    return { user };
  },

  // Restores the session after a page reload in the same tab (no token involved; see ./sessionStore.js).
  restore() {
    const session = loadSession();
    if (!session) return null;
    demoSession.role = session.user.role;
    return { user: session.user };
  },

  async signOut() {
    demoSession.role = null;
    clearSession();
  },
};
