import { useCallback, useEffect, useState } from "react";
import PrivateAccess from "../components/PrivateAccess.jsx";
import { Card, ErrorCard, Pill, Skeleton, textareaClass } from "../components/ui.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { argus, secondFactor } from "../services/index.js";
import { corpusStep } from "../services/actionsStep.js";
import { bundles, canManageCorpus, decideCorpusSource } from "../services/corpusSources.js";
import { dateTime } from "../utils/format.js";

const message = (error) => error?.detail ?? (error?.name === "NotAllowedError" ? "The security key was cancelled or timed out." : error?.message) ?? "The request failed.";

const SourceRow = ({ s }) => <li className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm">
  <strong className="font-mono">{s.source ?? s.name}</strong>
  <span className="text-muted">ref <code className="font-mono">{s.ref}</code></span>
  <span className="text-muted">{s.licence}</span>
  <span className="text-muted">{s.passages} passages · {s.quarantined} quarantined</span>
</li>;

// ACR-0034, the local tier: the reference sources Argus may cite. A staged bundle (downloaded by the isolated corpus
// service, hashed, scanned) is installed only after an approver or an administrator approves it with a security key (ACR-0040).
export function ReferenceSourcesView({ sources, canManage, busy, error, notice, reasons, onReason, onApprove, onReject, access = null }) {
  const groups = sources === null ? null : bundles(sources);
  const installed = groups?.find((g) => g.status === "installed");
  return <div className="space-y-5">
    <div>
      <h1 className="text-[28px] font-semibold tracking-[-0.03em]">Reference sources</h1>
      <p className="mt-1 text-sm text-muted">Vendor documentation Argus may cite in a diagnosis or a suggestion. A staged bundle is used only after it is approved; approving it replaces the sources it carries.</p>
    </div>
    {error && <ErrorCard title="Could not complete this request" text={error} />}
    {notice && <p role="status" className="rounded-xl border border-emerald-400/30 bg-emerald-400/10 p-3 text-sm text-emerald-300">{notice}</p>}
    {access}
    {!canManage && !access && <Card title="No decisions for this account">
      <p className="text-sm text-muted">Argus grants these decisions to approvers and administrators on the private path, after a security key.</p>
    </Card>}
    {groups === null ? (canManage && <Skeleton className="h-24" />) : groups.length === 0
      ? <Card title="Sources"><p className="text-sm text-muted">No reference source is installed or staged.</p></Card>
      : groups.map((g) => {
        const staged = g.status === "staged";
        const reasonId = `reject-reason-${g.name}`;
        const reason = reasons[g.name] ?? "";
        const same = staged && installed && g.sha256 === installed.sha256;
        return <Card key={g.key} title={staged ? <>Staged bundle <span className="font-mono">{g.name}</span></> : "Installed"}
          count={g.sources.length} right={<Pill tone={staged ? "amber" : "green"}>{staged ? "Waiting for review" : "In use"}</Pill>}>
          <p className="text-xs text-muted">
            {g.at && <>{staged ? "built" : "installed bundle built"} {dateTime(g.at)} · </>}sha256 <code className="font-mono">{String(g.sha256).slice(0, 16)}</code>
          </p>
          {same && <p className="mt-2 rounded-xl border border-amber-400/30 bg-amber-400/10 p-3 text-sm text-amber-300">
            Identical to the installed corpus: approving it changes nothing; rejecting it deletes this staged copy.</p>}
          <ul className="mt-2 divide-y divide-line">{g.sources.map((s) => <SourceRow key={s.source ?? s.name} s={s} />)}</ul>
          {canManage && staged && <div className="mt-3 flex flex-wrap items-end gap-2">
            <button type="button" disabled={busy} onClick={() => onApprove(g)}
              className="cursor-pointer rounded-lg bg-accent-solid px-3 py-1.5 text-sm text-white disabled:opacity-50">Approve with security key</button>
            <label htmlFor={reasonId} className="sr-only">Reason to reject {g.name}</label>
            <textarea id={reasonId} rows={1} value={reason} placeholder="Reason to reject"
              onChange={(event) => onReason(g.name, event.target.value)} className={`min-w-0 flex-1 ${textareaClass}`} />
            <button type="button" disabled={busy || !reason.trim()} onClick={() => onReject(g)}
              className="cursor-pointer rounded-lg border border-line px-3 py-1.5 text-sm disabled:opacity-50">Reject</button>
          </div>}
        </Card>;
      })}
  </div>;
}

export default function ReferenceSources() {
  const { user, loginPrivate, refresh } = useAuth();
  const step = corpusStep(user);
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
  useEffect(() => { if (step === "ready") load(); }, [step, load]);

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

  const decide = (bundle, decision) => run(async () => {
    await decideCorpusSource({ source: bundle, decision, reason: reasons[bundle.name] ?? "", secondFactor, argus });
    setNotice(decision === "approve" ? `${bundle.name} installed.` : `${bundle.name} rejected.`);
    await load();
  });

  const access = step === "private-login" || step === "second-factor"
    ? <PrivateAccess step={step} busy={busy} run={run} loginPrivate={loginPrivate} secondFactor={secondFactor} refresh={refresh} />
    : null;
  return <ReferenceSourcesView sources={sources} canManage={canManage} busy={busy} error={error} notice={notice}
    reasons={reasons} onReason={(name, text) => setReasons((r) => ({ ...r, [name]: text }))} access={access}
    onApprove={(b) => decide(b, "approve")} onReject={(b) => decide(b, "reject")} />;
}
