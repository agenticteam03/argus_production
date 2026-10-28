import { useCallback, useEffect, useState } from "react";
import { Card, ErrorCard, Pill, Skeleton, textareaClass } from "../components/ui.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { argus, secondFactor } from "../services/index.js";
import { canManageCorpus, decideCorpusSource } from "../services/corpusSources.js";
import { dateTime } from "../utils/format.js";

const STATUS = { installed: ["Installed", "green"], staged: ["Waiting for review", "amber"] };
const message = (error) => error?.detail ?? (error?.name === "NotAllowedError" ? "The security key was cancelled or timed out." : error?.message) ?? "The request failed.";

// ACR-0034, the local tier: the reference sources Argus may cite. A staged source (downloaded by the isolated corpus
// service, hashed, scanned) is installed only after an approver or an administrator approves it with a security key (ACR-0040).
export function ReferenceSourcesView({ sources, canManage, busy, error, notice, reasons, onReason, onApprove, onReject }) {
  return <div className="space-y-5">
    <div>
      <h1 className="text-[28px] font-semibold tracking-[-0.03em]">Reference sources</h1>
      <p className="mt-1 text-sm text-muted">Vendor documentation Argus may cite in a diagnosis or a suggestion. A staged source is used only after it is approved.</p>
    </div>
    {error && <ErrorCard title="Could not complete this request" text={error} />}
    {notice && <p role="status" className="rounded-xl border border-emerald-400/30 bg-emerald-400/10 p-3 text-sm text-emerald-300">{notice}</p>}
    {!canManage && <Card title="No decisions for this account">
      <p className="text-sm text-muted">Argus grants these decisions to approvers and administrators on the private path, after a security key. Sign in privately from Actions first.</p>
    </Card>}
    {sources === null ? <Skeleton className="h-24" /> : <Card title="Sources" count={sources.length}>
      {sources.length === 0 ? <p className="text-sm text-muted">No reference source is installed or staged.</p> :
        <ul className="divide-y divide-line">
          {sources.map((s) => {
            const [label, tone] = STATUS[s.status] ?? [s.status, "neutral"];
            const reasonId = `reject-reason-${s.name}`;
            const reason = reasons[s.name] ?? "";
            return <li key={s.name} className="space-y-2 py-3 text-sm">
              <div className="flex flex-wrap items-center gap-3">
                <strong className="font-mono">{s.name}</strong>
                <Pill tone={tone}>{label}</Pill>
                <span className="text-muted">ref <code className="font-mono">{s.ref}</code> · {s.licence}</span>
                <span className="text-muted">{s.passages} passages · {s.quarantined} quarantined</span>
              </div>
              <p className="text-xs text-muted">
                {s.staged_at && <>staged {dateTime(s.staged_at)}</>}{s.installed_at && <> · installed {dateTime(s.installed_at)}</>}
                {" · "}sha256 <code className="font-mono">{String(s.sha256).slice(0, 16)}</code>
              </p>
              {canManage && s.status === "staged" && <div className="flex flex-wrap items-end gap-2">
                <button type="button" disabled={busy} onClick={() => onApprove(s)}
                  className="cursor-pointer rounded-lg bg-accent-solid px-3 py-1.5 text-white disabled:opacity-50">Approve with security key</button>
                <label htmlFor={reasonId} className="sr-only">Reason to reject {s.name}</label>
                <textarea id={reasonId} rows={1} value={reason} placeholder="Reason to reject"
                  onChange={(event) => onReason(s.name, event.target.value)} className={`min-w-0 flex-1 ${textareaClass}`} />
                <button type="button" disabled={busy || !reason.trim()} onClick={() => onReject(s)}
                  className="cursor-pointer rounded-lg border border-line px-3 py-1.5 disabled:opacity-50">Reject</button>
              </div>}
            </li>;
          })}
        </ul>}
    </Card>}
  </div>;
}

export default function ReferenceSources() {
  const { user } = useAuth();
  const canManage = canManageCorpus(user);
  const [sources, setSources] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [reasons, setReasons] = useState({});

  const load = useCallback(async () => {
    try {
      setSources(await argus.listCorpusSources());
    } catch (err) {
      setSources([]); setError(message(err));
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const decide = async (source, decision) => {
    if (busy) return;
    setBusy(true); setError(null); setNotice(null);
    try {
      await decideCorpusSource({ source, decision, reason: reasons[source.name] ?? "", secondFactor, argus });
      setNotice(decision === "approve" ? `${source.name} installed.` : `${source.name} rejected.`);
      await load();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  };

  return <ReferenceSourcesView sources={sources} canManage={canManage} busy={busy} error={error} notice={notice}
    reasons={reasons} onReason={(name, text) => setReasons((r) => ({ ...r, [name]: text }))}
    onApprove={(s) => decide(s, "approve")} onReject={(s) => decide(s, "reject")} />;
}
