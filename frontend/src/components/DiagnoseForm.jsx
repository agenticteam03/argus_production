import { useEffect, useId, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { argus } from "../services/index.js";
import { Card, Segmented, Select, textareaClass } from "./ui.jsx";
import { investigationError } from "../utils/investigationError.js";

// ACR-0012: start an investigation from the UI. Shown only when /me lists `start_investigation` (an operator or
// approver with an investigate token): the UI never decides who may act. The target comes from the inventory's list
// (GET /api/v1/targets), never free text; the API applies its own quotas and checks. ACR-0044 (T-0059): a target the
// runtime says is not on its host (`absent`, e.g. a scenario container that is not deployed) is hidden unless asked.
export const REASON_MAX = 500;

const STATE_NOTE = { stopped: "stopped", absent: "not on its host" };

// The options the selector shows, and how many absent targets it hides.
export function targetOptions(rows, showAll) {
  const all = rows ?? [];
  const shown = all.filter((t) => showAll || t.state !== "absent");
  return {
    options: shown.map((t) => ({ value: t.target, label: STATE_NOTE[t.state] ? `${t.target} (${STATE_NOTE[t.state]})` : t.target })),
    hidden: all.length - shown.length,
  };
}

const KINDS = [{ value: "report", label: "Report", hint: "Something's wrong" }, { value: "check", label: "Check", hint: "Is it healthy?" }];

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
  const [showAll, setShowAll] = useState(false);
  const ids = { form: useId(), target: useId(), kind: useId(), reason: useId(), error: useId(), all: useId() };

  useEffect(() => {
    if (!allowed || fixedTarget) return;
    let alive = true;
    argus.listTargets().then((rows) => alive && setTargets(rows)).catch(() => alive && setTargets([]));
    return () => { alive = false; };
  }, [allowed, fixedTarget]);

  if (!allowed) return null;

  const { options, hidden } = targetOptions(targets, showAll);
  const toggleAll = (on) => {
    setShowAll(on);
    if (!on && targets?.find((t) => t.target === target)?.state === "absent") setTarget("");
  };

  const submit = async (e) => {
    e?.preventDefault();
    if (!target || busy) return;
    setBusy(true);
    setError("");
    try {
      const { incident_id } = await argus.startInvestigation({ target, requestKind: kind, reason: reason.trim() });
      navigate(`/incidents/${incident_id}`);
    } catch (err) {
      setError(investigationError(err));
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
        {error && <p role="alert" className="animate-rise text-[13px] text-danger">{error}</p>}
      </div>
    );
  }

  return (
    <Card title="Start an investigation">
      <form aria-labelledby={ids.form} onSubmit={submit} className="grid gap-5 md:grid-cols-[minmax(0,15rem)_minmax(0,1fr)]" aria-describedby={error ? ids.error : undefined}>
        <h3 id={ids.form} className="sr-only">Start an investigation</h3>

        <div className="space-y-4">
          <div className="space-y-1.5">
            <span id={ids.target} className="block text-[13px] font-medium">Target</span>
            <Select aria-labelledby={ids.target} value={target} onChange={(e) => setTarget(e.target.value)} required>
              <option value="">{targets === null ? "Loading targets…" : "Choose a target"}</option>
              {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </Select>
            {(hidden > 0 || showAll) && (
              <label htmlFor={ids.all} className="flex items-center gap-2 text-xs text-muted">
                <input id={ids.all} type="checkbox" checked={showAll} onChange={(e) => toggleAll(e.target.checked)} />
                {showAll ? "Showing targets not on their host" : `Show ${hidden} target${hidden === 1 ? "" : "s"} not on their host`}
              </label>
            )}
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
            placeholder="What did you see? (optional)" className={`${textareaClass} min-h-24 flex-1`} />
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 md:col-span-2">
          <button type="submit" disabled={!target || busy}
            className="inline-flex h-11 cursor-pointer items-center rounded-[10px] bg-accent-solid px-5 text-sm font-medium text-white transition enabled:hover:bg-accent-solid-hover disabled:cursor-not-allowed disabled:bg-disabled disabled:text-faint motion-reduce:transition-none">
            {busy ? "Starting…" : "Start investigation"}
          </button>
          <p className="text-xs text-muted">Argus only reads: it never changes the target. Investigations are limited per account.</p>
          {error && <p id={ids.error} role="alert" className="animate-rise basis-full text-[13px] text-danger">{error}</p>}
        </div>
      </form>
    </Card>
  );
}
