// Frontend-only stand-in for the real auth API (POST /api/v1/auth/login).
// Demo logins (password: argus-demo): admin@argus.dev, operator@argus.dev, viewer@argus.dev
const ROLES = { "admin@argus.dev": "admin", "operator@argus.dev": "operator", "viewer@argus.dev": "viewer" };

/** @type {import("./AuthPort.js").AuthPort} */
export const mockAuthAdapter = {
  async signIn({ email, password }) {
    await new Promise((resolve) => setTimeout(resolve, 700));
    const role = ROLES[email.toLowerCase()];
    if (role && password === "argus-demo") return { user: { email, role } };
    throw new Error("Incorrect email or password. Please try again.");
  },
  async signOut() {},
};
