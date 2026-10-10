import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { argus } from "../services/index.js";
import { usePoll } from "./usePoll.js";

export function useIncidentList() {
  const { logout } = useAuth();
  const [state, setState] = useState({ rows: null, error: null, live: true });

  const load = useCallback(async () => {
    try {
      setState({ rows: await argus.listIncidents({ limit: 30 }), error: null, live: true });
    } catch (err) {
      if (err.status === 401) return logout();
      // First load failed -> error state. A later poll failed -> keep the rows and show "Reconnecting…".
      setState((s) => (s.rows ? { ...s, live: false } : { rows: null, error: err, live: true }));
    }
  }, [logout]);

  useEffect(() => { load(); }, [load]);
  usePoll(load, 5000);
  return { ...state, retry: load };
}
