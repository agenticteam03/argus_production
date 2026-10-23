import { useEffect, useState } from "react";
import { argus } from "../services/index.js";

// ACR-0017: GET /api/v1/topology, or with `incidentId` the overlay that adds the incident's target and root cause
// from its stored evidence (the API allows the overlay to operators and approvers only). Returns null when the
// adapter has no such call, the route answers 404/empty, or it fails, so the Map tab and the mini map stay hidden.
// Expected shape: docs/API-FOR-UI.md item 12 (drawn by components/map/SystemMap.jsx).
export function useTopology(incidentId) {
  const [topology, setTopology] = useState(null);
  useEffect(() => {
    if (typeof argus.getTopology !== "function") return undefined;
    let alive = true;
    const keep = (t) => alive && setTopology(t?.nodes?.length ? t : null);
    argus.getTopology(incidentId)
      // The overlay is operator/approver only. If the session's role is stale the API answers 403, so fall back to
      // the plain map instead of losing it: the API decides permissions, never the UI (ACR-0001).
      .catch((err) => (incidentId && err?.status === 403 ? argus.getTopology() : null))
      .then(keep)
      .catch(() => keep(null));
    return () => { alive = false; };
  }, [incidentId]);
  return topology;
}
