import { useEffect, useState } from "react";
import { argus } from "../services/index.js";

// Phase 4: GET /api/v1/topology. Returns null when the adapter has no such call, the route answers 404/empty, or it fails,
// so the Map tab and the mini map simply stay hidden. Expected shape: see components/SystemMap.jsx.
export function useTopology() {
  const [topology, setTopology] = useState(null);
  useEffect(() => {
    if (typeof argus.getTopology !== "function") return undefined;
    let alive = true;
    argus.getTopology()
      .then((t) => alive && setTopology(t?.nodes?.length ? t : null))
      .catch(() => alive && setTopology(null));
    return () => { alive = false; };
  }, []);
  return topology;
}
