import { useCallback, useEffect, useState } from "react";
import ApprovalCard from "./ApprovalCard.jsx";
import PrivateAccess from "./PrivateAccess.jsx";
import { CircleCheck, ErrorCard, Lock, Skeleton } from "./ui.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { argus, secondFactor } from "../services/index.js";
import { actionsStep } from "../services/actionsStep.js";
import { answerFrozenApproval } from "../services/approvalDecision.js";

const message = (error) => error?.detail ?? (error?.name === "NotAllowedError" ? "The security key was cancelled or timed out." : error?.message) ?? "The request failed.";

// The incident's own approval, decided where the incident is read: the same steps and the same frozen card as the
// Actions screen (ACR-0032), shown only while the approval waits and only to an approver. Argus grants every step.
export default function IncidentApproval({ action, onAnswered }) {
  const { user, loginPrivate, refresh } = useAuth();
  const approvalId = action?.approval?.state === "pending" ? action.approval.id : null;
  const step = actionsStep(user);
  const [approval, setApproval] = useState(null);
  const [busy, setBusy] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const canAnswer = ["full", "ops"].includes(user?.access) && !!user?.actions?.includes("approve_action");

  const load = useCallback(async () => {
    try {
      setApproval(await argus.getApproval(approvalId));
    } catch (err) {
      setError(message(err));
    }
  }, [approvalId]);
  useEffect(() => { if (approvalId && step === "ready") load(); }, [approvalId, step, load]);

  if (!approvalId && !notice) return null;
  if (step === "not-granted" && !notice) return null;

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
    onAnswered?.();
  });

  return <section aria-label="Decide this approval" className="space-y-3">
    {step !== "ready" && <p className="flex items-center gap-2 rounded-xl border border-accent/30 bg-accent/10 p-3 text-sm text-ink">
      <Lock width="16" height="16" className="shrink-0 text-accent-hover" />
      This incident's action waits for an approver. Sign in privately to decide it here.</p>}
    {error && <ErrorCard title="Could not complete this request" text={error} />}
    {notice && <p role="status" className="flex items-center gap-2 rounded-xl border border-emerald-400/30 bg-emerald-400/10 p-3 text-sm text-emerald-300">
      <CircleCheck width="16" height="16" className="shrink-0" /> {notice}</p>}
    <PrivateAccess step={step} busy={busy} run={run} loginPrivate={loginPrivate} secondFactor={secondFactor} refresh={refresh} />
    {step === "ready" && (approval
      ? <ApprovalCard approval={approval} canAnswer={canAnswer} busy={busy} confirmation={confirmation}
          onConfirmation={setConfirmation} reason={reason} onReason={setReason} onAnswer={answer} />
      : !error && <Skeleton className="h-64" />)}
  </section>;
}
