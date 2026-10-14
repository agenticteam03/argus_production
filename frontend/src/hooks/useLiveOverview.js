import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { argus } from "../services/index.js";
import { POLL_MS } from "../utils/polling.js";
import { usePoll } from "./usePoll.js";

// Polling every 30 s, paused while the tab is hidden (usePoll). When the SSE endpoint exists, subscribe here instead
// and keep the same return shape.
export function useLiveOverview(intervalMs = POLL_MS.overview) {
  const { logout } = useAuth();
  const [data, setData] = useState({ incidents: [], approvals: [], escalations: [], hostMetrics: [] });
  const [live, setLive] = useState(true);
  const [updatedAt, setUpdatedAt] = useState(null);

  const refresh = useCallback(async () => {
    try {
      setData(await argus.getOverview());
      setLive(true);
      setUpdatedAt(Date.now());
    } catch (err) {
      if (err.status === 401) return logout(); // token expired: drop the session instead of just "Reconnecting…"
      setLive(false);
    }
  }, [logout]);

  useEffect(() => { refresh(); }, [refresh]);
  usePoll(refresh, intervalMs);

  return { ...data, live, updatedAt, refresh };
}
