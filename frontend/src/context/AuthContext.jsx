import { createContext, useContext, useMemo, useState } from "react";
import { auth } from "../services/index.js";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  // Restore a persisted session before the first paint, so a reload does not flash the login screen. Both
  // adapters restore from the tab's `sessionStorage` (./services/sessionStore.js); the HTTP one also puts the
  // bearer token back in memory.
  const [session, setSession] = useState(() => auth.restore?.() ?? null);
  const value = useMemo(
    () => ({
      user: session?.user ?? null, // { name, role: "viewer" | "operator" | "approver", access, actions }
      login: async (credentials) => setSession(await auth.signIn(credentials)),
      logout: async () => { await auth.signOut(); setSession(null); },
    }),
    [session]
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
