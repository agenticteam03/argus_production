// ACR-0018 phase 16 step 3: the account's security keys. The first key needs a one-time code from another
// administrator (D4); a further key is added after confirming with an enrolled one (a step-up); a privileged
// permission counts only for a login confirmed with a key, by a person with two (D3). Argus decides all of it: this
// page shows what /me and the credential list say and runs the browser's side of each ceremony.
import { useCallback, useEffect, useState } from "react";
import { Card, ErrorCard, Lock, Shield, Skeleton, fieldClass } from "../components/ui.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { secondFactor } from "../services/index.js";
import { registerObject } from "../services/secondFactorAdapter.js";
import { supported } from "../services/webauthn.js";
import { dateTime } from "../utils/format.js";

const button =
  "inline-flex h-10 cursor-pointer items-center justify-center rounded-[10px] bg-accent-solid px-4 text-sm font-medium text-white transition enabled:hover:bg-accent-solid-hover disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:transition-none";
const reason = (err) => err?.detail ?? (err?.name === "NotAllowedError" ? "The key was not used (cancelled or timed out)." : err?.message) ?? "Something went wrong.";

export function SecurityView({ status, keys, browserOk, busy, error, notice, onEnrol, onAddAnother, onConfirm }) {
  const [ticket, setTicket] = useState("");
  const [label, setLabel] = useState("");
  if (status === undefined) return <Skeleton className="h-40" />;
  if (status === null) {
    return <Card title="Security keys"><p className="p-4 text-sm text-muted">Security keys are not set up on this Argus.</p></Card>;
  }
  const first = status.enrolled === 0;
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold">Security keys</h1>
        <p className="mt-1 text-sm text-muted">
          A passkey or a security key confirms it is you. Privileged actions need a login confirmed with a key and two
          keys registered, so one lost key never locks you out.
        </p>
      </div>
      {!browserOk && <p role="alert" className="text-sm text-danger">This browser cannot use security keys.</p>}
      {error && <p role="alert" className="text-sm text-danger">{error}</p>}
      {notice && <p role="status" className="text-sm text-emerald-300">{notice}</p>}

      <Card title="This login" right={<Shield width="16" height="16" className="text-muted" />}>
        <div className="flex flex-wrap items-center justify-between gap-3 p-4 text-sm">
          <span>{status.verified ? "Confirmed with a key." : first ? "No key registered yet." : "Not confirmed with a key yet."}</span>
          {!first && !status.verified && (
            <button type="button" className={button} disabled={busy || !browserOk} onClick={onConfirm}>Confirm with my key</button>
          )}
        </div>
      </Card>

      <Card title="Registered keys" count={status.enrolled}>
        {keys.length > 0 && (
          <ul className="divide-y divide-line">
            {keys.map((k) => (
              <li key={k.credential} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm">
                <span className="flex items-center gap-2"><Lock width="14" height="14" className="text-muted" />{k.label || "Unnamed key"}</span>
                <span className="text-xs text-muted">
                  added {dateTime(k.created_at)}{k.last_used_at ? ` · last used ${dateTime(k.last_used_at)}` : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
        <form className="grid gap-3 p-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
          onSubmit={(e) => { e.preventDefault(); (first ? onEnrol({ ticket: ticket.trim(), label }) : onAddAnother({ label })); }}>
          {first && (
            <label className="flex flex-col gap-1.5 text-[13px] font-medium">
              Enrolment code
              <input className={fieldClass} value={ticket} onChange={(e) => setTicket(e.target.value)} autoComplete="off"
                required placeholder="From another administrator" />
            </label>
          )}
          <label className="flex flex-col gap-1.5 text-[13px] font-medium">
            Name this key
            <input className={fieldClass} value={label} maxLength={64} onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. laptop passkey" />
          </label>
          <button type="submit" className={button} disabled={busy || !browserOk || (first && !ticket.trim())}>
            {first ? "Register this key" : "Add another key"}
          </button>
        </form>
        {first && (
          <p className="px-4 pb-4 text-xs text-muted">
            Ask another administrator for a one-time code (<code>argus webauthn allow-enrol</code>); it is valid for a day.
          </p>
        )}
        {!first && status.enrolled < 2 && (
          <p className="px-4 pb-4 text-xs text-muted">Add a second key (for example your phone) before you need privileged actions.</p>
        )}
        {!first && <p className="px-4 pb-4 text-xs text-muted">Adding a key asks you to confirm with one you already have.</p>}
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
