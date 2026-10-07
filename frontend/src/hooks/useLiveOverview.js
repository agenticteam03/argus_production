import { useCallback, useEffect, useState } from "react";
import { argus } from "../services/index.js";

// Short polling today. When the SSE endpoint exists, subscribe here instead and keep the same return shape.
export function useLiveOverview(intervalMs = 5000) {
  const [data, setData] = useState({ incidents: [] });
  const [live, setLive] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setData(await argus.getOverview());
      setLive(true);
    } catch {
      setLive(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, intervalMs);
    return () => clearInterval(id);
  }, [refresh, intervalMs]);

  return { ...data, live, refresh };
}
