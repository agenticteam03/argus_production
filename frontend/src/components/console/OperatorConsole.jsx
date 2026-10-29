import { useEffect, useState } from "react";
import ConsolePanel from "./ConsolePanel.jsx";
import ConsoleTerminal from "./ConsoleTerminal.jsx";

// CON-3 (ACR-0043): the operator console on the incident page, a terminal and the Argus panel side by side (about
// 55/45 on desktop, stacked below lg). `console` comes from hooks/useConsole.js. Commands run through Argus's own
// tools in the API; nothing here runs anything. Layout: brain/tasks/current/argus-console-mockup-spec.md §2.
export default function OperatorConsole({ incident, console: con }) {
  const [now, setNow] = useState(() => Date.now());
  // A second's tick only while an analysis waits for the metrics, for its countdown.
  const waiting = (con.history ?? []).some((e) => e.analysis?.status === "waiting");
  useEffect(() => {
    if (!waiting) return undefined;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [waiting]);

  return (
    <section aria-labelledby="console-title" className="rounded-2xl border border-line bg-card/80 p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="console-title" className="text-[15px] font-medium">Operator console</h2>
        <p className="text-xs text-muted">Commands run through Argus&apos;s own tools. No shell. Writes need an approval.</p>
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)] gap-3 lg:grid-cols-[minmax(0,55fr)_minmax(0,45fr)]">
        <div className="h-[22rem] min-h-0 lg:h-[28rem]">
          <ConsoleTerminal key={incident.id} incidentId={incident.id} history={con.history} run={con.run} />
        </div>
        <div className="min-h-0 lg:h-[28rem]">
          <ConsolePanel incident={incident} history={con.history} now={now} />
        </div>
      </div>
    </section>
  );
}
