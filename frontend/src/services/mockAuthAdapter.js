// Frontend-only stand-in for the real auth API (POST /api/v1/auth/token + GET /api/v1/me).
// Demo logins (password: argus-demo): approver, operator, viewer — the three Argus roles, never an admin.
import { demoSession } from "./demoSession.js";

// Same shape GET /api/v1/me returns: the server lists the actions a read token may use.
const ACCOUNTS = {
  viewer: { role: "viewer", actions: ["view_incidents", "view_timeline"] },
  operator: { role: "operator", actions: ["view_incidents", "view_timeline", "view_evidence"] },
  approver: { role: "approver", actions: ["view_incidents", "view_timeline", "view_evidence"] },
};

/** @type {import("./AuthPort.js").AuthPort} */
export const mockAuthAdapter = {
  async signIn({ username, password }) {
    await new Promise((resolve) => setTimeout(resolve, 700));
    const account = ACCOUNTS[username?.toLowerCase()];
    if (account && password === "argus-demo") {
      demoSession.role = account.role;
      return { user: { name: username, access: "read", ...account } };
    }
    throw new Error("Incorrect username or password. Please try again.");
  },
  async signOut() {
    demoSession.role = null;
  },
};
