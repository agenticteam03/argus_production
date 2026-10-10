import { useState } from "react";
import { clock, dateTime } from "../utils/format.js";
import { Card, LivePill } from "./ui.jsx";

const LABELS = {
  detect: "Detect", evidence_pack: "Evidence pack", recall: "Recall", investigate: "Investigate", act: "Act", propose_action: "Propose action",
  request_approval: "Request approval", await_approval: "Await approval", precheck_action: "Precheck action", execute_write: "Execute write",
  verify: "Verify", record: "Record",
};
const STAGES = [
  { label: "DETECT", nodes: ["detect"] },
  { label: "RECALL", nodes: ["recall"] },
  { label: "INVESTIGATE ⇄ ACT", nodes: ["investigate", "act"] },
  { label: "RECORD", nodes: ["record"] },
];
const STAGE_TONE = {
  done: "border-emerald-400/20 bg-emerald-400/10 text-emerald-300",
  active: "border-accent/30 bg-accent/10 text-accent-hover",
  pending: "border-line text-muted",
};
const PHASE_TONE = { enter: "bg-sky-400/10 text-sky-300", step: "bg-white/5 text-muted", exit: "bg-emerald-400/10 text-emerald-300" };

// Reached = any of its nodes has an event. The last reached stage is active while the run is live.
function stageStates(events, active) {
  const reached = STAGES.map((s) => events.some((e) => s.nodes.includes(e.node)));
  const last = reached.lastIndexOf(true);
  return STAGES.map((_, i) => (!reached[i] ? "pending" : active && i === last ? "active" : "done"));
}

export default function RunTimeline({ events, active, reconnecting }) {
  const [open, setOpen] = useState(() => new Set());
  const states = stageStates(events, active);
  const toggle = (seq) => setOpen((prev) => { const next = new Set(prev); next.has(seq) ? next.delete(seq) : next.add(seq); return next; });

  return (
    <Card title="Run timeline" right={active ? <LivePill live={!reconnecting} /> : <span className="text-xs text-muted">Finished</span>}>
      <ol className="mb-4 flex flex-wrap items-center gap-2" aria-label="Run stages">
        {STAGES.map((s, i) => (
          <li key={s.label} className="flex items-center gap-2">
            {i > 0 && <span className="text-muted" aria-hidden="true">→</span>}
            <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium ${STAGE_TONE[states[i]]}`}>
              {states[i] === "active" && <span className="size-1.5 animate-pulse rounded-full bg-current motion-reduce:animate-none" />}
              {s.label}
              <span className="sr-only"> ({states[i]})</span>
            </span>
          </li>
        ))}
      </ol>

      {events.length === 0 ? (
        <p className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-muted">
          {active ? "Waiting for the first event…" : "No events were recorded."}
        </p>
      ) : (
        <ol className="ml-2 border-l border-line">
          {events.map((e) => {
            const hasData = e.data && Object.keys(e.data).length > 0;
            const panel = `event-data-${e.seq}`;
            return (
              <li key={e.seq} className="relative pb-3 pl-5 last:pb-0">
                <span className={`absolute -left-[5px] top-1.5 size-2.5 rounded-full border border-card ${e.phase === "exit" ? "bg-emerald-400" : e.phase === "enter" ? "bg-sky-400" : "bg-zinc-500"}`} />
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <time dateTime={e.at} title={dateTime(e.at)} className="font-mono text-xs text-muted">{clock(e.at)}</time>
                  <span className="font-medium">{LABELS[e.node] ?? e.node}</span>
                  <span className={`rounded-md px-1.5 py-0.5 text-[11px] ${PHASE_TONE[e.phase] ?? "bg-white/5 text-muted"}`}>{e.phase}</span>
                  {hasData && (
                    <button aria-expanded={open.has(e.seq)} aria-controls={panel} onClick={() => toggle(e.seq)} className="cursor-pointer text-xs text-accent-hover hover:underline">
                      Details
                    </button>
                  )}
                </div>
                {hasData && (
                  <pre id={panel} hidden={!open.has(e.seq)} className="mt-2 overflow-x-auto rounded-lg bg-field p-3 text-xs text-[#d6dbe6]">{JSON.stringify(e.data, null, 2)}</pre>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}
