import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { argus } from "../services/index.js";
import { INCIDENTS_CAP } from "../utils/paging.js";
import { usePoll } from "./usePoll.js";

export function useIncidentList() {
  const { logout } = useAuth();
  const [state, setState] = useState({ rows: null, error: null, live: true, updatedAt: null, truncated: false });

  const load = useCallback(async () => {
    try {
      // The API has no `offset`, only `limit` (the latest N), so fetch up to the cap once and page in the browser
      // (`utils/paging.js`). `truncated` warns when we hit the cap and there may be more rows we cannot reach.
      const rows = await argus.listIncidents({ limit: INCIDENTS_CAP });
      setState({ rows, error: null, live: true, updatedAt: Date.now(), truncated: rows.length >= INCIDENTS_CAP });
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
