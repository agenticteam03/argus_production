import { useEffect, useState } from "react";
import { argus } from "../services/index.js";

// Phase 5: the incident's metrics window. Returns null when the adapter has no such call, the route answers 404/empty,
// or it fails, so the Metrics tab and the mini charts stay hidden. Expected shape: see components/MetricChart.jsx.
// It re-reads when the range changes and when the incident changes status (e.g. when the run closes). ACR-0017.
export function useIncidentMetrics(id, range, status) {
  const [state, setState] = useState({ id: null, data: null });
  useEffect(() => {
    if (!id || typeof argus.getIncidentMetrics !== "function") return undefined;
    let alive = true;
    argus.getIncidentMetrics(id, range)
      .then((d) => alive && setState({ id, data: d?.series?.length ? d : null }))
      .catch(() => alive && setState({ id, data: null }));
    return () => { alive = false; };
  }, [id, range, status]);
  return state.id === id ? state.data : null;
}
