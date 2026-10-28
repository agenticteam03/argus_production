import { Card, Pill } from "./ui.jsx";
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

const Step = ({ title, meta, children }) => {
  const [label, tone] = meta ?? ["None", "neutral"];
  return <li className="rounded-xl border border-line bg-field p-3.5">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h3 className="text-sm font-medium text-ink">{title}</h3>
      <Pill tone={tone}>{label}</Pill>
    </div>
    {children && <div className="mt-2 text-[13px] text-body">{children}</div>}
  </li>;
};

// The supervised action of this incident, read-only: proposal, judge, the operator's answer, execution and verification.
// Approving stays on the Actions screen of the private path; nothing here acts.
export default function ActionTrail({ action }) {
  if (!action) return null;
  const { judge, approval, outcome } = action;
  const run = action.action;
  return (
    <Card title="Action">
      <p className="mb-3 text-[13px] text-muted">The proposal Argus froze for this incident and what happened to it. Approvals are answered on the Actions screen.</p>
      <ol className="space-y-3">
        <Step title="Proposal" meta={["Frozen", "neutral"]}>
          <p><span className="font-mono">{action.capability}</span> on <span className="break-all">{action.target}</span></p>
          <p className="mt-1 text-muted">{action.rationale}</p>
        </Step>
        <Step title="Independent judge" meta={judge ? VERDICT[judge.verdict] : ["Not reviewed", "neutral"]}>
          {judge?.reasons?.length > 0 && <ul className="list-disc space-y-0.5 pl-5 text-muted">{judge.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>}
        </Step>
        <Step title="Operator approval" meta={approval ? APPROVAL[approval.state] : ["Not requested", "neutral"]}>
          {approval?.answered_by && <p>Answered by <span className="font-medium">{approval.answered_by}</span>{approval.answered_at && <> at {dateTime(approval.answered_at)}</>}</p>}
        </Step>
        <Step title="Execution" meta={run ? ACTION[run.state] : ["Not run", "neutral"]}>
          {run?.result_at && <p>Finished at {dateTime(run.result_at)}</p>}
        </Step>
        <Step title="Verification" meta={outcome ? OUTCOME[outcome.outcome] : ["Not recorded", "neutral"]} />
      </ol>
    </Card>
  );
}
