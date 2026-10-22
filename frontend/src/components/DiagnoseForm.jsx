import { useEffect, useId, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { argus } from "../services/index.js";
import { Card, Segmented, Select, textareaClass } from "./ui.jsx";

// ACR-0012: start an investigation from the UI. Shown only when /me lists `start_investigation` (an operator or
// approver with an investigate token): the UI never decides who may act. The target comes from the inventory's list
// (GET /api/v1/targets), never free text; the API applies its own quotas and checks.
export const REASON_MAX = 500;

const KINDS = [{ value: "report", label: "Report", hint: "Something is wrong" }, { value: "check", label: "Check", hint: "Is it healthy?" }];

const errorText = (err) => {
  if (err?.status === 429) {
    const min = err.retryAfter ? Math.max(1, Math.ceil(err.retryAfter / 60)) : null;
    return `Too many investigations right now${min ? `: try again in about ${min} min` : ""}.`;
  }
  if (err?.status === 403) return "Your account may not start investigations.";
  return "Could not start the investigation. Please try again.";
};

export default function DiagnoseForm({ fixedTarget = null, compact = false }) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const allowed = user?.actions?.includes("start_investigation") ?? false;
  const [targets, setTargets] = useState(fixedTarget ? [{ target: fixedTarget }] : null);
  const [target, setTarget] = useState(fixedTarget ?? "");
  const [kind, setKind] = useState("report");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ids = { form: useId(), target: useId(), kind: useId(), reason: useId(), error: useId() };

  useEffect(() => {
    if (!allowed || fixedTarget) return;
    let alive = true;
    argus.listTargets().then((rows) => alive && setTargets(rows)).catch(() => alive && setTargets([]));
    return () => { alive = false; };
  }, [allowed, fixedTarget]);

  if (!allowed) return null;

  const submit = async (e) => {
    e?.preventDefault();
    if (!target || busy) return;
    setBusy(true);
    setError("");
    try {
      const { incident_id } = await argus.startInvestigation({ target, requestKind: kind, reason: reason.trim() });
      navigate(`/incidents/${incident_id}`);
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(false);
    }
  };

  if (compact) {
    return (
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={submit} disabled={busy}
          className="cursor-pointer rounded-xl bg-accent-solid px-4 py-2 text-sm font-medium text-white hover:bg-accent-solid-hover disabled:opacity-60">
          {busy ? "Starting…" : "Investigate again"}
        </button>
        {error && <p role="alert" className="text-[13px] text-danger">{error}</p>}
      </div>
    );
  }

  return (
    <Card title="Start an investigation">
      <form aria-labelledby={ids.form} onSubmit={submit} className="grid gap-5 md:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]" aria-describedby={error ? ids.error : undefined}>
        <h3 id={ids.form} className="sr-only">Start an investigation</h3>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <span id={ids.target} className="block text-[13px] font-medium">Target</span>
            <Select aria-labelledby={ids.target} value={target} onChange={(e) => setTarget(e.target.value)} required>
              <option value="">{targets === null ? "Loading targets…" : "Choose a target"}</option>
              {(targets ?? []).map((t) => <option key={t.target} value={t.target}>{t.target}</option>)}
            </Select>
          </div>

          <div className="space-y-1.5">
            <span id={ids.kind} className="block text-[13px] font-medium">Kind</span>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <Segmented label="Kind" options={KINDS} value={kind} onChange={setKind} />
              <span className="text-xs text-muted">{KINDS.find((k) => k.value === kind)?.hint}</span>
            </div>
          </div>
        </div>

        <div className="flex flex-col space-y-1.5">
          <label htmlFor={ids.reason} className="block text-[13px] font-medium">Reason</label>
          <textarea id={ids.reason} value={reason} maxLength={REASON_MAX} rows={4} onChange={(e) => setReason(e.target.value)}
            placeholder="What did you see? (optional)" className={`${textareaClass} flex-1`} />
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 md:col-span-2">
          <button type="submit" disabled={!target || busy}
            className="inline-flex h-11 cursor-pointer items-center rounded-[10px] bg-accent-solid px-5 text-sm font-medium text-white transition enabled:hover:bg-accent-solid-hover disabled:cursor-not-allowed disabled:bg-[#10141b] disabled:text-[#4b5363] motion-reduce:transition-none">
            {busy ? "Starting…" : "Start investigation"}
          </button>
          <p className="text-xs text-muted">Argus only reads: it never changes the target. Investigations are limited per account.</p>
          {error && <p id={ids.error} role="alert" className="basis-full text-[13px] text-danger">{error}</p>}
        </div>
      </form>
    </Card>
  );
}
