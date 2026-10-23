import { clock, dateTime } from "../utils/format.js";
import { formatMs, modelCalls, shortName, stages } from "../utils/incidentView.js";
import { Card, LivePill } from "./ui.jsx";

const LABELS = {
  detect: "Detect", evidence_pack: "Evidence pack", recall: "Recall", investigate: "Investigate", act: "Act", propose_action: "Propose action",
  request_approval: "Request approval", await_approval: "Await approval", precheck_action: "Precheck action", execute_write: "Execute write",
  verify: "Verify", record: "Record",
};

function Reads({ reads, evidenceIds, onJump }) {
  if (!reads.length) return null;
  return (
    <span className="mt-1 flex flex-wrap gap-x-3 gap-y-1">
      {reads.map((r, i) => {
        const label = `${r.capability}${r.target ? ` ${shortName(r.target)}` : ""}${r.status && r.status !== "ok" ? ` · ${r.status}` : ""}`;
        return r.evidenceId && evidenceIds.has(r.evidenceId) ? (
          <button key={i} type="button" onClick={() => onJump(r.evidenceId)} className="cursor-pointer font-mono text-xs text-accent-hover hover:underline">{label}</button>
        ) : (
          <span key={i} className="font-mono text-xs text-muted">{label}</span>
        );
      })}
    </span>
  );
}

// One row per stage of the run (a stage is a run of consecutive events of the same node).
export default function RunTimeline({ incident, events, active, reconnecting, evidenceIds, onJump }) {
  const list = stages(events);
  const reads = list.reduce((n, s) => n + s.reads.length, 0);
  const calls = modelCalls(incident);
  const total = list.length ? list.at(-1).end - list[0].start : null;
  const finished = ["Finished", Number.isFinite(total) && formatMs(total), `${reads} ${reads === 1 ? "read" : "reads"}`, calls === 0 ? "no AI calls" : calls > 0 ? `${calls} AI ${calls === 1 ? "call" : "calls"}` : null].filter(Boolean).join(" · ");

  return (
    <Card title="Run timeline" right={active ? <LivePill live={!reconnecting} /> : <span className="text-xs text-muted">{finished}</span>}>
      {list.length === 0 ? (
        <p className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-muted">
          {active ? "Waiting for the first event…" : "No events were recorded."}
        </p>
      ) : (
        <ol className="ml-2 border-l border-line">
          {list.map((s, i) => {
            const running = active && !s.done;
            const end = !active && i === list.length - 1;
            return (
              <li key={`${s.name}-${i}`} className="relative grid gap-x-3 gap-y-0.5 py-2 pl-5 text-sm md:grid-cols-[8rem_4.5rem_minmax(0,1fr)]">
                <span className={`absolute -left-[5px] top-3.5 size-2.5 rounded-full border border-card ${running ? "animate-pulse bg-accent motion-reduce:animate-none" : end ? "bg-emerald-400" : "bg-sky-400"}`} />
                <span className="font-medium" title={dateTime(s.at)}>{LABELS[s.name] ?? s.name}</span>
                <span className="font-mono text-xs leading-5 text-muted"><time dateTime={s.at} title={clock(s.at)}>{running ? "running" : s.done ? formatMs(s.durationMs) : "—"}</time></span>
                <span className="min-w-0 text-body">
                  {s.summary}
                  <Reads reads={s.reads} evidenceIds={evidenceIds} onJump={onJump} />
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}
