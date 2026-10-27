import { useCallback, useEffect, useState } from "react";
import ApprovalCard from "../components/ApprovalCard.jsx";
import { Card, ErrorCard, Skeleton } from "../components/ui.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { argus, secondFactor } from "../services/index.js";
import { answerFrozenApproval } from "../services/approvalDecision.js";
import { DEMO_APPROVAL_ID } from "../services/demoApproval.js";

const preview = import.meta.env.VITE_ARGUS_PHASE19_DEMO === "1";
const message = (error) => error?.detail ?? (error?.name === "NotAllowedError" ? "The security key was cancelled or timed out." : error?.message) ?? "The request failed.";

export default function Actions() {
  const { user } = useAuth();
  const [id, setId] = useState(preview ? DEMO_APPROVAL_ID : "");
  const [approval, setApproval] = useState(null);
  const [loading, setLoading] = useState(preview);
  const [busy, setBusy] = useState(false);
  const [confirmation, setConfirmation] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const canAnswer = user?.access === "full" && user.actions?.includes("approve_action");

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

  useEffect(() => { if (preview) load(DEMO_APPROVAL_ID); }, [load]);

  const answer = async (decision) => {
    if (!canAnswer || !approval || busy) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      await answerFrozenApproval({ approval, decision, confirmation, reason, secondFactor, argus });
      setApproval(await argus.getApproval(approval.id));
      setNotice(`Decision recorded: ${decision}.`);
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  };

  return <div className="space-y-5">
    <div>
      <h1 className="text-[28px] font-semibold tracking-[-0.03em]">Actions</h1>
      <p className="mt-1 text-sm text-muted">Review the frozen proposal and independent judge before deciding. A decision never executes this card directly.</p>
    </div>
    {preview && <p className="rounded-xl border border-amber-400/30 bg-amber-400/10 p-3 text-sm text-amber-300">Local demonstration: this approval is synthetic and cannot be submitted.</p>}
    <Card title="Open an approval">
      <form className="flex flex-wrap gap-2" onSubmit={(event) => { event.preventDefault(); if (id.trim()) load(id.trim()); }}>
        <label htmlFor="approval-id" className="sr-only">Approval ID</label>
        <input id="approval-id" value={id} onChange={(event) => setId(event.target.value)} placeholder="Approval ID"
          className="min-w-0 flex-1 rounded-lg border border-line bg-field px-3 py-2 text-sm" />
        <button type="submit" disabled={!id.trim() || loading} className="cursor-pointer rounded-lg bg-accent-solid px-4 py-2 text-sm text-white disabled:opacity-50">Open</button>
      </form>
    </Card>
    {loading && <Skeleton className="h-64" />}
    {error && <ErrorCard title="Could not complete this approval request" text={error} />}
    {notice && <p role="status" className="rounded-xl border border-emerald-400/30 bg-emerald-400/10 p-3 text-sm text-emerald-300">{notice}</p>}
    {approval && <ApprovalCard approval={approval} canAnswer={canAnswer} busy={busy} confirmation={confirmation}
      onConfirmation={setConfirmation} reason={reason} onReason={setReason} onAnswer={answer} />}
  </div>;
}
