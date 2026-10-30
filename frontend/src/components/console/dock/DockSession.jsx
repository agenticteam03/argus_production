import { useEffect, useState } from "react";
import { useConsole } from "../../../hooks/useConsole.js";
import { useIncident } from "../../../hooks/useIncident.js";
import ConsolePanel from "../ConsolePanel.jsx";
import ConsoleTerminal from "../ConsoleTerminal.jsx";
import { PanelIcon } from "./icons.jsx";

// T-0016: one tab of the side panel: the team's operator console (ACR-0043) for one incident, unchanged: its terminal
// fills the panel and its Argus panel (diagnosis, history, analysis) opens below it. Nothing here runs a command.
export default function DockSession({ incidentId, active }) {
  const { incident } = useIncident(incidentId);
  const con = useConsole(incidentId, active);
  const [argusOpen, setArgusOpen] = useState(true);
  const [waited, setWaited] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  // useConsole answers null while it asks and when the API refuses: after a few seconds, say why it may be closed.
  useEffect(() => {
    const t = setTimeout(() => setWaited(true), 4000);
    return () => clearTimeout(t);
  }, []);

  // The Argus panel's analysis countdown needs a second's tick only while an analysis waits for the metrics.
  const waiting = (con?.history ?? []).some((e) => e.analysis?.status === "waiting");
  useEffect(() => {
    if (!waiting) return undefined;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [waiting]);

  if (!con) {
    return (
      <div className="grid h-full place-items-center p-6 text-center">
        <p role="status" className="max-w-sm text-sm text-muted">
          {waited
            ? "The console does not answer for this incident: it may be off on this Argus, or your private session ended. Disconnect and open it again."
            : "Connecting to the console…"}
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-2 p-3">
      <div className="min-h-0 flex-1">
        <ConsoleTerminal key={incidentId} incidentId={incidentId} history={con.history} run={con.run} />
      </div>
      <div className="shrink-0">
        <button type="button" onClick={() => setArgusOpen((o) => !o)} aria-expanded={argusOpen}
          className="flex w-full cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-left text-xs font-medium uppercase tracking-wide text-muted hover:bg-ink/5 hover:text-ink">
          <PanelIcon width="14" height="14" /> Argus {argusOpen ? "· hide" : "· show"}
        </button>
        {argusOpen && incident && (
          <div className="mt-1 max-h-[38dvh] overflow-y-auto">
            <ConsolePanel incident={incident} history={con.history} now={now} />
          </div>
        )}
      </div>
    </div>
  );
}
