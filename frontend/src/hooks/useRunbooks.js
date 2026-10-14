import { useEffect, useMemo, useState } from "react";
import { runbooks } from "../services/index.js";
import { parseRunbook } from "../utils/parseRunbook.js";

// Loads the library; re-parses only when the Markdown actually changed. The adapter says whether to poll: the demo
// library every 10 s (an edited .md shows up), the edge's never (it changes with a deployment; ACR-0011).
export function useRunbooks(intervalMs = runbooks.pollMs) {
  const [raw, setRaw] = useState(null);
  const [live, setLive] = useState(true);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const next = await runbooks.listRunbooks();
        if (!active) return;
        setRaw((prev) => (JSON.stringify(prev) === JSON.stringify(next) ? prev : next));
        setLive(true);
      } catch {
        if (active) setLive(false);
      }
    };
    load();
    const id = intervalMs > 0 ? setInterval(load, intervalMs) : null;
    return () => { active = false; if (id) clearInterval(id); };
  }, [intervalMs]);

  const items = useMemo(() => (raw ?? []).map(parseRunbook).sort((a, b) => a.id.localeCompare(b.id)), [raw]);
  return { items, loading: raw === null, live };
}
