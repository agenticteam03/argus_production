import { analysisView, printable, STATUS_VIEW } from "../../utils/consoleSession.js";
import { clock } from "../../utils/format.js";
import { shortName } from "../../utils/incidentView.js";
import { Pill, STATUS_META } from "../ui.jsx";

// CON-3: the Argus panel next to the terminal. The diagnosis is the incident's own state (the page's polling), never
// console-local state; the activity is the stored command history, with Argus's analysis when the API sends one (CON-4).
export default function ConsolePanel({ incident: inc, history = [], now = Date.now() }) {
  const ruledOut = Array.isArray(inc.ruled_out) ? inc.ruled_out : [];
  const [statusLabel, statusTone] = STATUS_META[inc.status] ?? [inc.status, "neutral"];
  const items = [...history].reverse();
  return (
    <div className="flex h-full min-h-0 flex-col gap-3">
      <section aria-labelledby="console-diagnosis" className="rounded-xl border border-line bg-field p-3.5">
        <div className="flex items-center justify-between gap-2">
          <h3 id="console-diagnosis" className="text-sm font-medium text-ink">Current diagnosis</h3>
          {inc.status && <Pill tone={statusTone}>{statusLabel}</Pill>}
        </div>
        <dl className="mt-2 grid grid-cols-[6.5rem_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-[13px]">
          <dt className="text-muted">Root cause</dt>
          <dd className="break-all font-mono text-body">{inc.root_cause_target ? shortName(inc.root_cause_target) : "Not concluded"}</dd>
          <dt className="text-muted">Confidence</dt>
          <dd className="text-body">{Number.isFinite(inc.confidence) ? `${Math.round(inc.confidence * 100)}%` : "—"}</dd>
          {ruledOut.length > 0 && <>
            <dt className="text-muted">Ruled out</dt>
            <dd className="break-all font-mono text-body">{ruledOut.map(shortName).join(", ")}</dd>
          </>}
        </dl>
      </section>

      <section aria-labelledby="console-activity" className="flex min-h-0 flex-1 flex-col rounded-xl border border-line bg-field p-3.5">
        <h3 id="console-activity" className="text-sm font-medium text-ink">Activity</h3>
        {items.length === 0 ? (
          <p className="mt-2 text-[13px] text-muted">No commands yet. Argus comments here after each command.</p>
        ) : (
          <ol className="mt-2 max-h-80 min-h-0 flex-1 space-y-2 overflow-y-auto pr-1 lg:max-h-none">
            {items.map((e) => {
              const [label, tone] = STATUS_VIEW[e.status] ?? [e.status, "neutral"];
              const analysis = analysisView(e.analysis, now);
              return (
                <li key={e.command_id} className="rounded-lg border border-line bg-card/60 p-2.5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <code className="min-w-0 break-all font-mono text-[13px] text-ink">{printable(e.input)}</code>
                    <Pill tone={tone}>{label}</Pill>
                  </div>
                  <p className="mt-1 text-xs text-muted">{[e.by, e.started_at ? clock(e.started_at) : null].filter(Boolean).join(" · ")}</p>
                  {analysis && (
                    <p className="mt-2 flex gap-2 border-t border-line pt-2 text-[13px] text-body">
                      <span className="shrink-0 font-medium text-accent-hover">Argus</span>
                      <span className="min-w-0">{analysis.text}</span>
                    </p>
                  )}
                </li>
              );
            })}
          </ol>
        )}
      </section>
    </div>
  );
}
