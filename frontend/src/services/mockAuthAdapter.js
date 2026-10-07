// Frontend-only stand-in for the real login (POST /api/v1/auth/token with scope=read, then GET /api/v1/me).
// Demo logins (password: argus-demo): viewer, operator, approver — Argus users are handles, not emails.
// The user has the shape of /me for a read token (contracts/samples/me.json): never a write action.
const ROLES = { viewer: "viewer", operator: "operator", approver: "approver" };
const actionsFor = (role) => ["view_incidents", "view_timeline", ...(role === "viewer" ? [] : ["view_evidence"])];

/** @type {import("./AuthPort.js").AuthPort} */
export const mockAuthAdapter = {
  async signIn({ username, password }) {
    await new Promise((resolve) => setTimeout(resolve, 700));
    const role = ROLES[username.toLowerCase()];
    if (role && password === "argus-demo") return { user: { name: username, role, access: "read", actions: actionsFor(role) } };
    throw new Error("Incorrect username or password. Please try again.");
  },
  async signOut() {},
};
