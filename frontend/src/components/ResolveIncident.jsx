import { useId, useState } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { argus } from "../services/index.js";
import { textareaClass } from "./ui.jsx";
import { dateTime } from "../utils/format.js";

// ACR-0041: close an escalated incident that was fixed outside Argus, with a reason. Shown only on an escalated
// incident and only when /me lists `resolve_incident` (an operator or approver): the UI never decides who may act.
// The incident keeps its diagnosis; the API records who, when and why.
export const RESOLVE_REASON_MAX = 500;

export function Resolution({ resolution }) {
  if (!resolution) return null;
  return (
    <p className="rounded-xl border border-emerald-400/30 bg-emerald-400/10 p-3 text-sm text-emerald-300">
      Resolved by <strong>{resolution.by}</strong> on {dateTime(resolution.at)}: {resolution.reason}
    </p>
  );
}

const resolveError = (err) => err?.status === 409 ? "This incident is no longer escalated; reload it."
  : err?.status === 403 ? "Your account cannot resolve incidents."
  : err?.status === 422 ? "Write what fixed it (1 to 500 characters)."
  : "Could not resolve this incident. Please try again.";

export default function ResolveIncident({ incident, onResolved }) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ids = { reason: useId(), error: useId() };
  if (incident?.status !== "escalated" || !(user?.actions?.includes("resolve_incident") ?? false)) return null;

  const submit = async (e) => {
    e?.preventDefault();
    if (!reason.trim() || busy) return;
    setBusy(true);
    setError("");
    try {
      await argus.resolveIncident(incident.id, reason.trim());
      setOpen(false);
      setReason("");
      onResolved?.();
    } catch (err) {
      setError(resolveError(err));
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return <button type="button" onClick={() => setOpen(true)}
      className="cursor-pointer rounded-xl border border-line bg-field px-4 py-2 text-sm text-body hover:text-ink">Resolve</button>;
  }
  return (
    <form onSubmit={submit} className="w-full space-y-2 rounded-xl border border-line bg-field p-3" aria-label="Resolve this incident">
      <label htmlFor={ids.reason} className="block text-sm font-medium">What fixed it? (required)</label>
      <textarea id={ids.reason} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={RESOLVE_REASON_MAX}
        rows={2} required aria-describedby={error ? ids.error : undefined} className={textareaClass}
        placeholder="e.g. restarted the cache by hand" />
      <p className="text-xs text-muted">The incident closes and keeps its diagnosis; your name, the time and this reason are recorded.</p>
      {error && <p id={ids.error} role="alert" className="animate-rise text-[13px] text-danger">{error}</p>}
      <div className="flex gap-2">
        <button type="submit" disabled={busy || !reason.trim()}
          className="cursor-pointer rounded-xl bg-accent-solid px-4 py-2 text-sm font-medium text-white hover:bg-accent-solid-hover disabled:cursor-not-allowed disabled:opacity-60">
          {busy ? "Closing…" : "Close incident"}
        </button>
        <button type="button" onClick={() => { setOpen(false); setError(""); }} disabled={busy}
          className="cursor-pointer rounded-xl border border-line px-4 py-2 text-sm">Cancel</button>
      </div>
    </form>
  );
}
