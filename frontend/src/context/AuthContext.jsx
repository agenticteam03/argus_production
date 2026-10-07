import { createContext, useContext, useMemo, useState } from "react";
import { auth } from "../services/index.js";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [session, setSession] = useState(null);
  const value = useMemo(
    () => ({
      user: session?.user ?? null, // { email, role: "viewer" | "operator" | "admin" }
      login: async (credentials) => setSession(await auth.signIn(credentials)),
      logout: async () => { await auth.signOut(); setSession(null); },
    }),
    [session]
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
