import { useCallback, useEffect, useState } from "react";
import { argus } from "../services/index.js";
import { nextHistory } from "../utils/consoleSession.js";
import { usePoll } from "./usePoll.js";

// CON-3 (ACR-0043): the operator console of one incident. Returns null when the adapter has no console calls, the
// route is refused (a viewer, the flag off) or answers no commands, so the Console tab stays hidden; the API decides
// who may use it, never the UI. While `active` (the tab is open) the history is read every 3 s and after each command.
// CON-9: a failed read keeps the last history and sets `historyUnavailable` until a later read succeeds; `recheck` is
// there only when the adapter can re-check an analysis (the demo, for now).
export function useConsole(incidentId, active) {
  const [state, setState] = useState({ id: null, commands: null });
  const [history, setHistory] = useState({ id: null, entries: [], unavailable: false });

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
      .then((d) => setHistory((prev) => nextHistory(prev, incidentId, d)))
      .catch((err) => setHistory((prev) => nextHistory(prev, incidentId, null, err)));   // the next poll retries
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

  const recheck = useCallback(async (commandId) => {
    try {
      return await argus.recheckConsoleAnalysis(incidentId, commandId);
    } finally {
      refresh();
    }
  }, [incidentId, refresh]);

  if (!available) return null;
  const current = history.id === incidentId;
  return { commands: state.commands, history: current ? history.entries : [], historyUnavailable: current && history.unavailable,
    run, recheck: typeof argus.recheckConsoleAnalysis === "function" ? recheck : undefined };
}
