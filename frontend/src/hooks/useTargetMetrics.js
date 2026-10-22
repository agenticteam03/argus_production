import { useEffect, useState } from "react";
import { argus } from "../services/index.js";

// ACR-0021: GET /api/v1/target-metrics for the system map's node drawer. `undefined` while loading, `null` when the
// adapter has no such call or the route fails (the drawer then says "No current samples"), else the window:
// { target, range, from, to, step_s, series: [{ key, title, unit, max, thresholds, points }] }.
export function useTargetMetrics(target, range = "15m") {
  const [state, setState] = useState({ key: null, data: undefined });
  const key = target ? `${target}|${range}` : null;
  useEffect(() => {
    if (!target) return undefined;
    if (typeof argus.getTargetMetrics !== "function") { setState({ key: `${target}|${range}`, data: null }); return undefined; }
    let alive = true;
    argus.getTargetMetrics(target, range)
      .then((d) => alive && setState({ key: `${target}|${range}`, data: d?.series?.length ? d : null }))
      .catch(() => alive && setState({ key: `${target}|${range}`, data: null }));
    return () => { alive = false; };
  }, [target, range]);
  return state.key === key ? state.data : undefined;
}
