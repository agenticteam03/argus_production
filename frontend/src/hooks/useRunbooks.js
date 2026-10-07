import { useEffect, useMemo, useState } from "react";
import { runbooks } from "../services/index.js";
import { parseRunbook } from "../utils/parseRunbook.js";

// Polls the server and re-parses only when the Markdown actually changed,
// so cards and the open drawer update on their own when a .md is edited.
export function useRunbooks(intervalMs = 10000) {
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
    const id = setInterval(load, intervalMs);
    return () => { active = false; clearInterval(id); };
  }, [intervalMs]);

  const items = useMemo(() => (raw ?? []).map(parseRunbook).sort((a, b) => a.id.localeCompare(b.id)), [raw]);
  return { items, loading: raw === null, live };
}
