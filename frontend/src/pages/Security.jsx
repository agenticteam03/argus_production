// ACR-0018 phase 16 step 3: the account's security keys. The first key needs a one-time code from another
// administrator (D4); a further key is added after confirming with an enrolled one (a step-up); a privileged
// permission counts only for a login confirmed with a key, by a person with two (D3). Argus decides all of it: this
// page shows what /me and the credential list say and runs the browser's side of each ceremony.
import { useCallback, useEffect, useState } from "react";
import { Card, ErrorCard, InsetRow, Lock, Pill, Shield, Skeleton, fieldClass } from "../components/ui.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { secondFactor } from "../services/index.js";
import { registerObject } from "../services/secondFactorAdapter.js";
import { supported } from "../services/webauthn.js";
import { dateTime } from "../utils/format.js";

const button =
  "inline-flex h-10 shrink-0 cursor-pointer items-center justify-center rounded-[10px] bg-accent-solid px-4 text-sm font-medium text-white transition enabled:hover:bg-accent-solid-hover disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-hover motion-reduce:transition-none";
const reason = (err) => err?.detail ?? (err?.name === "NotAllowedError" ? "The key was not used (cancelled or timed out)." : err?.message) ?? "Something went wrong.";
// Messages as tinted boxes, like the rest of the app; the text stays the box's first child (screen readers read it).
const ALERT = "animate-rise rounded-xl border border-red-400/30 bg-red-400/10 px-3.5 py-2.5 text-sm text-red-300";
const NOTICE = "rounded-xl border border-emerald-400/30 bg-emerald-400/10 px-3.5 py-2.5 text-sm text-emerald-300";
const code = "rounded-md bg-ink/5 px-1.5 py-0.5 font-mono text-[12px] text-body";

// Only theme tokens (text-ink, bg-ink/5, border-line, text-muted...): the page follows the light and dark themes.
export function SecurityView({ status, keys, browserOk, busy, error, notice, onEnrol, onAddAnother, onConfirm }) {
  const [ticket, setTicket] = useState("");
  const [label, setLabel] = useState("");
  if (status === undefined) return <Skeleton className="h-40" />;
  if (status === null) {
    return <Card title="Security keys"><p className="text-sm text-muted">Security keys are not set up on this Argus.</p></Card>;
  }
  const first = status.enrolled === 0;
  const [state, tone] = status.verified ? ["Confirmed", "green"] : first ? ["No key yet", "neutral"] : ["Not confirmed", "amber"];
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-[28px] font-semibold tracking-[-0.03em]">Security keys</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted">
          A passkey or a security key confirms it is you. Privileged actions need a login confirmed with a key and two
          keys registered, so one lost key never locks you out.
        </p>
      </div>
      {!browserOk && <p role="alert" className={ALERT}>This browser cannot use security keys.</p>}
      {error && <p role="alert" className={ALERT}>{error}</p>}
      {notice && <p role="status" className={NOTICE}>{notice}</p>}

      <Card title={<><Shield width="16" height="16" className="text-muted" />This login</>} right={<Pill tone={tone}>{state}</Pill>}>
        <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
          <span className="text-body">{status.verified ? "Confirmed with a key." : first ? "No key registered yet." : "Not confirmed with a key yet."}</span>
          {!first && !status.verified && (
            <button type="button" className={button} disabled={busy || !browserOk} onClick={onConfirm}>Confirm with my key</button>
          )}
        </div>
      </Card>

      <Card title={<><Lock width="16" height="16" className="text-muted" />Registered keys</>} count={status.enrolled}>
        {keys.length > 0 && (
          <ul className="stagger mb-4 space-y-2">
            {keys.map((k) => (
              <InsetRow as="li" key={k.credential} className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-sm">
                <span className="flex items-center gap-2.5 text-ink">
                  <span className="grid size-7 place-items-center rounded-lg border border-line bg-card"><Lock width="13" height="13" className="text-muted" /></span>
                  {k.label || "Unnamed key"}
                </span>
                <span className="text-xs text-muted">
                  added {dateTime(k.created_at)}{k.last_used_at ? ` · last used ${dateTime(k.last_used_at)}` : ""}
                </span>
              </InsetRow>
            ))}
          </ul>
        )}
        <form className={`grid gap-3 sm:items-end ${first ? "sm:grid-cols-[1fr_1fr_auto]" : "sm:grid-cols-[minmax(0,24rem)_auto] sm:justify-start"}`}
          onSubmit={(e) => { e.preventDefault(); (first ? onEnrol({ ticket: ticket.trim(), label }) : onAddAnother({ label })); }}>
          {first && (
            <label className="flex flex-col gap-1.5 text-[13px] font-medium text-ink">
              Enrolment code
              <input className={fieldClass} value={ticket} onChange={(e) => setTicket(e.target.value)} autoComplete="off"
                required placeholder="From another administrator" />
            </label>
          )}
          <label className="flex flex-col gap-1.5 text-[13px] font-medium text-ink">
            Name this key
            <input className={fieldClass} value={label} maxLength={64} onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. laptop passkey" />
          </label>
          <button type="submit" className={button} disabled={busy || !browserOk || (first && !ticket.trim())}>
            {first ? "Register this key" : "Add another key"}
          </button>
        </form>
        <div className="mt-3 space-y-1 text-xs text-muted">
          {first && (
            <p>Ask another administrator for a one-time code (<code className={code}>argus webauthn allow-enrol</code>); it is valid for a day.</p>
          )}
          {!first && status.enrolled < 2 && <p>Add a second key (for example your phone) before you need privileged actions.</p>}
          {!first && <p>Adding a key asks you to confirm with one you already have.</p>}
        </div>
      </Card>
    </div>
  );
}

export default function Security() {
  const { user } = useAuth();
  const [status, setStatus] = useState(undefined);
  const [keys, setKeys] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    try {
      const s = await secondFactor.status();
      setStatus(s);
      setKeys(s ? await secondFactor.credentials() : []);
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const run = (fn, done) => async (args) => {
    setBusy(true); setError(null); setNotice(null);
    try {
      await fn(args);
      setNotice(done);
      await load();
    } catch (err) {
      setError(reason(err));
    } finally {
      setBusy(false);
    }
  };

  if (failed) return <ErrorCard title="Could not load your security keys" text="Try again in a moment." onRetry={load} as="h1" />;
  return (
    <SecurityView
      status={status} keys={keys} browserOk={supported()} busy={busy} error={error} notice={notice}
      onEnrol={run(({ ticket, label }) => secondFactor.enrol({ ticket, label }), "Key registered.")}
      onAddAnother={run(async ({ label }) => {
        const { token } = await secondFactor.stepUp(registerObject(user.name));   // confirm with an enrolled key first
        await secondFactor.enrol({ stepUpToken: token, label });
      }, "Key added.")}
      onConfirm={run(() => secondFactor.confirmLogin(), "This login is confirmed with your key.")}
    />
  );
}
