import { Card, Check, Pill } from "./ui.jsx";
import { dateTime } from "../utils/format.js";

const VERDICT = { agree: ["Judge agreed", "green"], doubt: ["Judge doubted", "amber"], disagree: ["Judge disagreed", "red"] };
const APPROVAL = {
  pending: ["Waiting for approval", "blue"], approved: ["Approved", "green"], denied: ["Denied", "red"],
  expired: ["Expired", "amber"], cancelled: ["Cancelled", "neutral"],
};
const ACTION = {
  unstarted: ["Not started", "neutral"], attempting: ["Running", "blue"], confirmed: ["Done", "green"],
  failed: ["Failed", "red"], indeterminate: ["Result unknown", "amber"],
};
const OUTCOME = {
  recovered_verified: ["Recovery verified", "green"], action_failed: ["Not recovered", "red"],
  indeterminate_escalated: ["Not verified (escalated)", "amber"],
};
// The timeline's dot per tone (theme tokens, light and dark alike); a neutral step has not happened yet.
const DOT = {
  green: "border-emerald-400 bg-emerald-400 text-white", blue: "border-accent bg-accent text-white",
  amber: "border-amber-400 bg-amber-400 text-white", red: "border-red-400 bg-red-400 text-white",
  neutral: "border-line bg-card text-muted",
};

// One step of the timeline: a dot (checked when it went well), its title and state, and what is known about it.
const Step = ({ title, meta, last = false, children }) => {
  const [label, tone] = meta ?? ["None", "neutral"];
  return <li className="relative flex gap-3 pb-4 last:pb-0">
    {!last && <span aria-hidden="true" className="absolute left-[11px] top-6 bottom-0 w-px bg-line" />}
    <span aria-hidden="true" className={`relative z-[1] grid size-6 shrink-0 place-items-center rounded-full border-2 ${DOT[tone] ?? DOT.neutral}`}>
      {tone === "green" ? <Check width="12" height="12" /> : <span className="size-1.5 rounded-full bg-current" />}
    </span>
    <div className="min-w-0 flex-1 pt-0.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-medium text-ink">{title}</h3>
        <Pill tone={tone}>{label}</Pill>
      </div>
      {children && <div className="mt-1.5 text-[13px] text-body">{children}</div>}
    </div>
  </li>;
};

// The supervised action of this incident, read-only: proposal, judge, the operator's answer, execution and verification.
// Nothing here acts: a pending approval is decided below it (IncidentApproval) or on the Actions screen.
export default function ActionTrail({ action }) {
  if (!action) return null;
  const { judge, approval, outcome } = action;
  const run = action.action;
  // The header says where it stands now: the verification, else the execution, else the approval.
  const now = outcome ? OUTCOME[outcome.outcome] : run ? ACTION[run.state] : approval ? APPROVAL[approval.state] : null;
  return (
    <Card title="Action" right={now && <Pill tone={now[1]}>{now[0]}</Pill>}>
      <div className="mb-4 rounded-xl border border-line bg-ink/[0.03] p-3">
        <p className="font-mono text-sm font-semibold text-ink">{action.capability}</p>
        <p className="break-all font-mono text-xs text-muted">{action.target}</p>
        <p className="mt-1.5 text-[13px] text-body">{action.rationale}</p>
      </div>
      <ol className="stagger">
        <Step title="Proposal" meta={["Frozen", "neutral"]}>
          <p className="text-muted">Argus froze <span className="font-mono text-ink">{action.capability}</span> on <span className="break-all">{action.target}</span>.</p>
        </Step>
        <Step title="Independent judge" meta={judge ? VERDICT[judge.verdict] : ["Not reviewed", "neutral"]}>
          {judge?.reasons?.length > 0 && <ul className="list-disc space-y-0.5 pl-5 text-muted">{judge.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>}
        </Step>
        <Step title="Operator approval" meta={approval ? APPROVAL[approval.state] : ["Not requested", "neutral"]}>
          {approval?.answered_by && <p className="text-muted">Answered by <span className="font-medium text-ink">{approval.answered_by}</span>{approval.answered_at && <> at {dateTime(approval.answered_at)}</>}</p>}
        </Step>
        <Step title="Execution" meta={run ? ACTION[run.state] : ["Not run", "neutral"]}>
          {run?.result_at && <p className="text-muted">Finished at {dateTime(run.result_at)}</p>}
        </Step>
        <Step title="Verification" meta={outcome ? OUTCOME[outcome.outcome] : ["Not recorded", "neutral"]} last />
      </ol>
      <p className="mt-4 text-xs text-muted">The proposal Argus froze for this incident and what happened to it. An approver decides a waiting approval below or on the Actions screen.</p>
    </Card>
  );
}
