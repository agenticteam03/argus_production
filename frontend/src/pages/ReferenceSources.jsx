import { useCallback, useEffect, useState } from "react";
import PrivateAccess from "../components/PrivateAccess.jsx";
import { Book, Card, CircleCheck, ErrorCard, fieldClass, Pill, Skeleton } from "../components/ui.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { argus, secondFactor } from "../services/index.js";
import { corpusStep } from "../services/actionsStep.js";
import { bundles, canManageCorpus, decideCorpusSource } from "../services/corpusSources.js";
import { dateTime } from "../utils/format.js";

const message = (error) => error?.detail ?? (error?.name === "NotAllowedError" ? "The security key was cancelled or timed out." : error?.message) ?? "The request failed.";

// One source of a bundle: its name, the upstream version it was built from, its licence, and how many passages Argus
// may cite (quarantined ones failed the scan and are never cited).
const SourceRow = ({ s }) => <li className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 rounded-xl border border-line px-3 py-2 text-sm sm:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1fr)_auto]">
  <strong className="flex min-w-0 items-center gap-2 font-mono text-ink"><Book width="14" height="14" className="shrink-0 text-muted" />
    <span className="truncate">{s.source ?? s.name}</span></strong>
  <span className="order-last col-span-2 min-w-0 truncate text-xs text-muted sm:order-none sm:col-span-1">ref <code className="font-mono">{s.ref}</code></span>
  <span className="hidden min-w-0 truncate text-xs text-muted sm:block">{s.licence}</span>
  <span className={`text-right text-xs ${s.quarantined > 0 ? "text-amber-300" : "text-muted"}`}>{s.passages} passages · {s.quarantined} quarantined</span>
</li>;

// What this page is for, in three steps (T-0016: "I do not understand what it is").
const HOW = [
  ["Prepared", "Argus downloads vendor documentation (nginx, redis…) into a staged bundle, hashed and scanned."],
  ["Reviewed", "An approver or an administrator reads what changed and approves it with a security key, or rejects it."],
  ["Cited", "The approved bundle replaces the installed one; Argus may then quote its passages in a diagnosis."],
];

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
    <ol className="grid gap-3 sm:grid-cols-3">
      {HOW.map(([title, text], i) => <li key={title} className="flex gap-3 rounded-2xl border border-line bg-card/80 p-3">
        <span className="grid size-6 shrink-0 place-items-center rounded-full bg-accent/15 text-xs font-semibold text-accent-hover">{i + 1}</span>
        <span><span className="block text-sm font-medium text-ink">{title}</span><span className="block text-xs text-muted">{text}</span></span>
      </li>)}
    </ol>
    {error && <ErrorCard title="Could not complete this request" text={error} />}
    {notice && <p role="status" className="flex items-center gap-2 rounded-xl border border-emerald-400/30 bg-emerald-400/10 p-3 text-sm text-emerald-300">
      <CircleCheck width="16" height="16" className="shrink-0" /> {notice}</p>}
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
          <ul className="mt-3 space-y-1.5">{g.sources.map((s) => <SourceRow key={s.source ?? s.name} s={s} />)}</ul>
          {canManage && staged && <div className="mt-4 grid gap-2 rounded-xl border border-line bg-ink/[0.02] p-3 sm:grid-cols-[auto_minmax(0,1fr)_auto] sm:items-center">
            <button type="button" disabled={busy} onClick={() => onApprove(g)}
              className="h-11 cursor-pointer rounded-lg bg-accent-solid px-4 text-sm font-medium text-white transition enabled:hover:bg-accent-solid-hover disabled:cursor-not-allowed disabled:opacity-50">Approve with security key</button>
            <label htmlFor={reasonId} className="sr-only">Reason to reject {g.name}</label>
            <input id={reasonId} value={reason} placeholder="Reason to reject"
              onChange={(event) => onReason(g.name, event.target.value)} className={`min-w-0 ${fieldClass}`} />
            <button type="button" disabled={busy || !reason.trim()} onClick={() => onReject(g)}
              className="h-11 cursor-pointer rounded-lg border border-line bg-field px-4 text-sm text-ink transition enabled:hover:bg-ink/5 disabled:cursor-not-allowed disabled:opacity-50">Reject</button>
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
