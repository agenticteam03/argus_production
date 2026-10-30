import { Card, CircleAlert, fieldClass, Pill } from "./ui.jsx";
import { dateTime } from "../utils/format.js";

const RISKS = { green: ["Green risk", "green"], amber: ["Amber risk", "amber"], red: ["Red risk", "red"] };
const VERDICTS = { agree: ["agree", "green"], doubt: ["doubt", "amber"], disagree: ["disagree", "red"] };
// The judge's box takes its verdict's tint (theme tokens, light and dark alike).
const JUDGE_TINT = { green: "border-emerald-400/30 bg-emerald-400/[0.06]", amber: "border-amber-400/30 bg-amber-400/[0.06]",
  red: "border-red-400/30 bg-red-400/[0.06]", neutral: "border-line bg-ink/[0.03]" };
// ACR-0039: a doubt reaches the approver; only a disagreement cannot be approved (the server refuses it too).
const APPROVABLE = new Set(["agree", "doubt"]);
const button = "h-10 rounded-lg px-4 text-sm font-medium transition enabled:cursor-pointer disabled:cursor-not-allowed disabled:opacity-45";
const label = "text-[11px] font-medium uppercase tracking-wide text-muted";

const Fact = ({ name, mono = false, children }) => (
  <div className="min-w-0">
    <dt className={label}>{name}</dt>
    <dd className={`mt-0.5 break-words text-ink ${mono ? "font-mono text-xs" : "text-sm"}`}>{children}</dd>
  </div>
);
const Step = ({ title, children }) => (
  <div className="rounded-xl border border-line bg-ink/[0.03] p-3">
    <h3 className={label}>{title}</h3>
    <p className="mt-1 text-sm text-body">{children}</p>
  </div>
);

// The server owns authorization and the frozen digest. This view never creates or edits a proposal.
export default function ApprovalCard({ approval, canAnswer, busy, confirmation, onConfirmation, reason = "", onReason, onAnswer }) {
  const proposal = approval.proposal;
  const input = proposal.input;
  const red = approval.judge.risk === "red";
  const identity = Object.entries(input.target_identity ?? {});
  const args = Object.entries(input.arguments ?? {});
  const [riskLabel, tone] = RISKS[approval.judge.risk] ?? ["Risk unavailable", "neutral"];
  const pending = approval.state === "pending" && Date.parse(approval.expires_at) > Date.now();
  const ready = canAnswer && pending && !busy;
  // The host-qualified target: the same container name exists on both hosts.
  const doubted = approval.judge.verdict === "doubt";
  const [verdictLabel, verdictTone] = VERDICTS[approval.judge.verdict] ?? [approval.judge.verdict, "neutral"];
  const mayApprove = ready && APPROVABLE.has(approval.judge.verdict) && (!red || confirmation === input.target);
  const mayDeny = ready && reason.trim() !== "";

  return <Card title="Frozen action proposal" right={<Pill tone={tone}>{riskLabel}</Pill>}>
    <div className="space-y-5 text-sm">
      {doubted && <div role="alert" className="flex gap-3 rounded-xl border border-amber-400/30 bg-amber-400/10 p-3 text-amber-300">
        <CircleAlert width="18" height="18" className="mt-0.5 shrink-0" />
        <div>
          <p className="font-medium">The independent judge doubted this action.</p>
          <p className="mt-1">It was not stopped: you decide. Read the judge's reasons and the {riskLabel.toLowerCase()} below
            (the doubt raised it one level) before approving; approving records that you overrode the doubt.</p>
        </div>
      </div>}

      <div>
        <p className="font-mono text-lg font-semibold text-ink">{input.capability}</p>
        <p className="break-all font-mono text-xs text-muted">{input.target}</p>
        <p className="mt-2 text-body">{input.rationale}</p>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <dl className="grid gap-3 rounded-xl border border-line p-3">
          <Fact name="Root cause">{input.root_cause}</Fact>
          <div className="grid grid-cols-2 gap-3">
            <Fact name="Basis">{proposal.basis}</Fact>
            <Fact name="Reversible">{approval.reversible ? "yes" : "no"}</Fact>
          </div>
          <Fact name="Grounds">{input.grounds.join(", ")}</Fact>
        </dl>
        <dl className="grid gap-3 rounded-xl border border-line p-3">
          <Fact name="Evidence IDs" mono>{input.evidence_refs.join(", ")}</Fact>
          <Fact name="Target identity" mono>{identity.length ? identity.map(([k, v]) => `${k}: ${v}`).join(", ") : "—"}</Fact>
          <Fact name="Arguments" mono>{args.length ? args.map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(", ") : "none"}</Fact>
        </dl>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        <Step title="Before execution">{input.preview}</Step>
        <Step title="Expected result">{input.prediction.signal} on {input.prediction.target}: {input.prediction.expected} within {input.prediction.within_seconds}s.</Step>
        <Step title="Rollback">{input.rollback}</Step>
      </div>

      <div>
        <h3 className={label}>Alternatives considered</h3>
        <ul className="mt-1.5 space-y-1">{input.alternatives.map((a) => <li key={`${a.action}:${a.why_not}`} className="text-body">
          <span className="font-medium text-ink">{a.action}</span>: <span className="text-muted">{a.why_not}</span></li>)}</ul>
      </div>

      <div className={`rounded-xl border p-3 ${JUDGE_TINT[verdictTone] ?? JUDGE_TINT.neutral}`}>
        <div className="flex items-center gap-2"><h3 className="text-sm font-medium text-ink">Independent judge</h3><Pill tone={verdictTone}>{verdictLabel}</Pill></div>
        <ul className="mt-2 list-disc space-y-0.5 pl-5 text-body">{approval.judge.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
      </div>

      <div className="space-y-3 rounded-xl border border-line bg-ink/[0.02] p-4">
        <h3 className="text-sm font-medium text-ink">Your decision</h3>
        {red && <div>
          <label htmlFor="approval-target-confirmation" className="block text-sm text-body">Type <span className="font-mono text-ink">{input.target}</span> to confirm this red-risk target</label>
          <input id="approval-target-confirmation" className={`mt-1.5 w-full ${fieldClass}`} value={confirmation}
            onChange={(event) => onConfirmation(event.target.value)} autoComplete="off" />
        </div>}
        {ready && <div>
          <label htmlFor="approval-deny-reason" className="block text-sm text-body">Reason (required to deny)</label>
          <input id="approval-deny-reason" className={`mt-1.5 w-full ${fieldClass}`} value={reason}
            onChange={(event) => onReason?.(event.target.value)} maxLength={500} autoComplete="off" />
        </div>}
        {!canAnswer && <p className="rounded-lg border border-amber-400/30 bg-amber-400/10 p-3 text-amber-300">A full private session is required to answer this approval.</p>}
        {!pending && <p className="text-muted">This approval is no longer pending.</p>}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={`${button} border border-line bg-field text-ink enabled:hover:bg-ink/5`} disabled={!mayDeny} onClick={() => onAnswer("denied")}>Deny</button>
          <button type="button" className={`${button} bg-accent-solid text-white enabled:hover:bg-accent-solid-hover`} disabled={!mayApprove} onClick={() => onAnswer("approved")}>Approve</button>
        </div>
      </div>

      <p className="break-all text-xs text-muted">Approval {approval.id} · Expires {dateTime(approval.expires_at)} · Digest <span className="font-mono">{proposal.digest}</span></p>
    </div>
  </Card>;
}
