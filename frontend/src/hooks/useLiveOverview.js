import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { argus } from "../services/index.js";

// Short polling today. When the SSE endpoint exists, subscribe here instead and keep the same return shape.
export function useLiveOverview(intervalMs = 5000) {
  const { logout } = useAuth();
  const [data, setData] = useState({ incidents: [], approvals: [], health: null });
  const [live, setLive] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setData(await argus.getOverview());
      setLive(true);
    } catch (err) {
      if (err.status === 401) return logout(); // token expired: drop the session instead of just "Reconnecting…"
      setLive(false);
    }
  }, [logout]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, intervalMs);
    return () => clearInterval(id);
  }, [refresh, intervalMs]);

  return { ...data, live, refresh };
}
