import { useCallback, useEffect, useState } from "react";
import { argus } from "../services/index.js";
import { usePoll } from "./usePoll.js";

// CON-3 (ACR-0043): the operator console of one incident. Returns null when the adapter has no console calls, the
// route is refused (a viewer, the flag off) or answers no commands, so the Console tab stays hidden; the API decides
// who may use it, never the UI. While `active` (the tab is open) the history is read every 3 s and after each command.
export function useConsole(incidentId, active) {
  const [state, setState] = useState({ id: null, commands: null });
  const [history, setHistory] = useState({ id: null, entries: [] });

  useEffect(() => {
    if (!incidentId || typeof argus.getConsoleCommands !== "function") return undefined;
    let alive = true;
    argus.getConsoleCommands(incidentId)
      .then((d) => alive && setState({ id: incidentId, commands: d?.commands?.length ? d.commands : null }))
      .catch(() => alive && setState({ id: incidentId, commands: null }));
    return () => { alive = false; };
  }, [incidentId]);

  const available = state.id === incidentId && Boolean(state.commands);

  const refresh = useCallback(() => {
    argus.getConsoleHistory(incidentId)
      .then((d) => setHistory({ id: incidentId, entries: Array.isArray(d?.entries) ? d.entries : [] }))
      .catch(() => {});      // a failed poll keeps the last history; the next one retries
  }, [incidentId]);

  useEffect(() => { if (available) refresh(); }, [available, refresh]);
  usePoll(refresh, 3000, available && active);

  const run = useCallback(async (body) => {
    try {
      return await argus.executeConsoleCommand(incidentId, body);
    } finally {
      refresh();
    }
  }, [incidentId, refresh]);

  if (!available) return null;
  return { commands: state.commands, history: history.id === incidentId ? history.entries : [], run };
}
