import { useCallback, useEffect, useState } from "react";
import ApprovalCard from "../components/ApprovalCard.jsx";
import PendingApprovals from "../components/PendingApprovals.jsx";
import PrivateAccess from "../components/PrivateAccess.jsx";
import { Card, ErrorCard, Skeleton } from "../components/ui.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { argus, secondFactor } from "../services/index.js";
import { actionsStep } from "../services/actionsStep.js";
import { answerFrozenApproval } from "../services/approvalDecision.js";
import { DEMO_APPROVAL_ID } from "../services/demoApproval.js";

const preview = import.meta.env.VITE_ARGUS_PHASE19_DEMO === "1";
const message = (error) => error?.detail ?? (error?.name === "NotAllowedError" ? "The security key was cancelled or timed out." : error?.message) ?? "The request failed.";

// ACR-0032: an approver signs in privately (a full token that works only on the private path, 15 minutes idle), confirms
// that session with a security key, then decides the approvals waiting in their scope. Argus grants every step.
export default function Actions() {
  const { user, loginPrivate, refresh } = useAuth();
  const step = preview ? "ready" : actionsStep(user);
  const [pending, setPending] = useState(null);
  const [id, setId] = useState(preview ? DEMO_APPROVAL_ID : "");
  const [approval, setApproval] = useState(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const canAnswer = ["full", "ops"].includes(user?.access) && user.actions?.includes("approve_action");

  const listPending = useCallback(async () => {
    try {
      setPending(await argus.listApprovals());
    } catch (err) {
      setError(message(err));
    }
  }, []);

  const load = useCallback(async (approvalId) => {
    setLoading(true); setError(null); setNotice(null); setApproval(null); setConfirmation(""); setReason("");
    try {
      setApproval(await argus.getApproval(approvalId));
    } catch (err) {
      setError(message(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { if (step === "ready") listPending(); }, [step, listPending]);
  useEffect(() => { if (preview) load(DEMO_APPROVAL_ID); }, [load]);

  const run = async (fn) => {
    if (busy) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      await fn();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  };

  const answer = (decision) => run(async () => {
    if (!canAnswer || !approval) return;
    await answerFrozenApproval({ approval, decision, confirmation, reason, secondFactor, argus });
    setApproval(await argus.getApproval(approval.id));
    setNotice(`Decision recorded: ${decision}.`);
    await listPending();
  });

  return <div className="space-y-5">
    <div>
      <h1 className="text-[28px] font-semibold tracking-[-0.03em]">Actions</h1>
      <p className="mt-1 text-sm text-muted">Review the frozen proposal and independent judge before deciding. A decision never executes this card directly.</p>
    </div>
    {preview && <p className="rounded-xl border border-amber-400/30 bg-amber-400/10 p-3 text-sm text-amber-300">Local demonstration: this approval is synthetic and cannot be submitted.</p>}
    {error && <ErrorCard title="Could not complete this request" text={error} />}
    {notice && <p role="status" className="rounded-xl border border-emerald-400/30 bg-emerald-400/10 p-3 text-sm text-emerald-300">{notice}</p>}

    <PrivateAccess step={step} busy={busy} run={run} loginPrivate={loginPrivate} secondFactor={secondFactor} refresh={refresh} />

    {step === "not-granted" && <Card title="No decisions for this account">
      <p className="text-sm text-muted">Argus grants decisions to approvers with two security keys, on the private path.</p>
    </Card>}

    {step === "ready" && <>
      {pending === null ? <Skeleton className="h-24" /> : <PendingApprovals items={pending} onOpen={load} />}
      <Card title="Open an approval by ID">
        <form className="flex flex-wrap gap-2" onSubmit={(event) => { event.preventDefault(); if (id.trim()) load(id.trim()); }}>
          <label htmlFor="approval-id" className="sr-only">Approval ID</label>
          <input id="approval-id" value={id} onChange={(event) => setId(event.target.value)} placeholder="Approval ID"
            className="min-w-0 flex-1 rounded-lg border border-line bg-field px-3 py-2 text-sm" />
          <button type="submit" disabled={!id.trim() || loading} className="cursor-pointer rounded-lg bg-accent-solid px-4 py-2 text-sm text-white disabled:opacity-50">Open</button>
        </form>
      </Card>
      {loading && <Skeleton className="h-64" />}
      {approval && <ApprovalCard approval={approval} canAnswer={canAnswer} busy={busy} confirmation={confirmation}
        onConfirmation={setConfirmation} reason={reason} onReason={setReason} onAnswer={answer} />}
    </>}
  </div>;
}
