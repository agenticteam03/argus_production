import { Card, Pill } from "./ui.jsx";
import { dateTime } from "../utils/format.js";

const RISKS = { green: ["Green risk", "green"], amber: ["Amber risk", "amber"], red: ["Red risk", "red"] };
const button = "rounded-lg px-4 py-2 text-sm font-medium transition enabled:cursor-pointer enabled:hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-45";

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
  const mayApprove = ready && approval.judge.verdict === "agree" && (!red || confirmation === input.target);
  const mayDeny = ready && reason.trim() !== "";

  return <Card title="Frozen action proposal" right={<Pill tone={tone}>{riskLabel}</Pill>}>
    <div className="space-y-4 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <strong className="font-mono text-base text-ink">{input.capability}</strong>
        <span className="break-all text-muted">{input.target}</span>
      </div>
      <p className="text-body">{input.rationale}</p>
      <dl className="grid gap-3 rounded-xl bg-field p-3 sm:grid-cols-2">
        <div><dt className="text-xs text-muted">Root cause</dt><dd>{input.root_cause}</dd></div>
        <div><dt className="text-xs text-muted">Basis</dt><dd>{proposal.basis}</dd></div>
        <div><dt className="text-xs text-muted">Grounds</dt><dd className="break-all">{input.grounds.join(", ")}</dd></div>
        <div><dt className="text-xs text-muted">Evidence IDs</dt><dd className="break-all font-mono text-xs">{input.evidence_refs.join(", ")}</dd></div>
        <div><dt className="text-xs text-muted">Target identity</dt><dd className="break-all font-mono text-xs">{identity.length ? identity.map(([k, v]) => `${k}: ${v}`).join(", ") : "—"}</dd></div>
        <div><dt className="text-xs text-muted">Arguments</dt><dd className="break-all font-mono text-xs">{args.length ? args.map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(", ") : "none"}</dd></div>
        <div><dt className="text-xs text-muted">Reversible</dt><dd>{approval.reversible ? "yes" : "no"}</dd></div>
      </dl>
      <div className="grid gap-3 sm:grid-cols-2">
        <div><h3 className="font-medium">Expected result</h3><p className="mt-1 text-muted">{input.prediction.signal} on {input.prediction.target}: {input.prediction.expected} within {input.prediction.within_seconds}s.</p></div>
        <div><h3 className="font-medium">Rollback</h3><p className="mt-1 text-muted">{input.rollback}</p></div>
      </div>
      <div><h3 className="font-medium">Before execution</h3><p className="mt-1 text-muted">{input.preview}</p></div>
      <div><h3 className="font-medium">Alternatives considered</h3><ul className="mt-1 list-disc pl-5 text-muted">{input.alternatives.map((a) => <li key={`${a.action}:${a.why_not}`}>{a.action}: {a.why_not}</li>)}</ul></div>
      <div className="rounded-xl border border-line p-3">
        <div className="flex items-center gap-2"><h3 className="font-medium">Independent judge</h3><Pill tone={approval.judge.verdict === "agree" ? "green" : "amber"}>{approval.judge.verdict}</Pill></div>
        <ul className="mt-2 list-disc pl-5 text-muted">{approval.judge.reasons.map((reason, i) => <li key={i}>{reason}</li>)}</ul>
      </div>
      <p className="text-xs text-muted">Approval {approval.id} · Expires {dateTime(approval.expires_at)} · Digest <span className="font-mono">{proposal.digest}</span></p>
      {red && <div>
        <label htmlFor="approval-target-confirmation" className="block text-sm font-medium">Type <span className="font-mono">{input.target}</span> to confirm this red-risk target</label>
        <input id="approval-target-confirmation" className="mt-2 w-full rounded-lg border border-line bg-field px-3 py-2" value={confirmation}
          onChange={(event) => onConfirmation(event.target.value)} autoComplete="off" />
      </div>}
      {ready && <div>
        <label htmlFor="approval-deny-reason" className="block text-sm font-medium">Reason (required to deny)</label>
        <input id="approval-deny-reason" className="mt-2 w-full rounded-lg border border-line bg-field px-3 py-2" value={reason}
          onChange={(event) => onReason?.(event.target.value)} maxLength={500} autoComplete="off" />
      </div>}
      {!canAnswer && <p className="rounded-lg border border-amber-400/30 bg-amber-400/10 p-3 text-amber-300">A full private session is required to answer this approval.</p>}
      {!pending && <p className="text-muted">This approval is no longer pending.</p>}
      <div className="flex flex-wrap gap-2 border-t border-line pt-4">
        <button type="button" className={`${button} bg-accent-solid text-white`} disabled={!mayApprove} onClick={() => onAnswer("approved")}>Approve</button>
        <button type="button" className={`${button} border border-line bg-field`} disabled={!mayDeny} onClick={() => onAnswer("denied")}>Deny</button>
      </div>
    </div>
  </Card>;
}
