import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../../../context/AuthContext.jsx";
import { argus, secondFactor } from "../../../services/index.js";
import { hostOf } from "../../../utils/incidentView.js";
import { CircleAlert, Server, StatusBadge, textareaClass } from "../../ui.jsx";
import { DOCK_HOSTS, dockAccess, hostIncidents, unlockStep } from "./consoleDock.js";
import { KeyIcon, TerminalIcon } from "./icons.jsx";

// T-0016: before the console opens. A modal like the prototype's, small enough that the page stays in view behind it:
// the host and its incident (the console works inside one), then the access case from /me (two registered keys, and
// the private session confirmed with one, ACR-0032), then the reason, recorded with the person (an audit row).
const COPY = {
  "no-keys": ["No security key yet",
    "You have no security key registered, so the console cannot open. Your account probably has no console access yet, "
    + "or you have not received the one-time code for your first key. Ask your Argus administrator for one."],
  "one-key": ["Register a second key",
    "The console needs two registered security keys (one recovers the other). You have one: register the second from "
    + "this computer, for example your phone with a QR code."],
  unlock: ["Confirm it is you",
    "Commands run on a private session confirmed with your security key. Sign in privately, then touch your key."],
  unconfigured: ["Security keys are not set up",
    "This Argus has no security keys configured, so the console cannot open. Ask your Argus administrator."],
};

const field = "h-10 w-full rounded-lg border border-field-line bg-field px-3 text-sm text-ink outline-none transition placeholder:text-faint focus:border-accent focus:ring-[3px] focus:ring-accent/20";
const primary = "inline-flex h-9 cursor-pointer items-center justify-center gap-2 rounded-lg bg-accent-solid px-3 text-sm font-medium text-white transition enabled:hover:bg-accent-solid-hover disabled:cursor-wait disabled:opacity-60";

// Case 3 inside the dialog (the team's PrivateAccess is a page-width card): the private sign-in (ACR-0032) as a
// compact form, then the key. Its own <form>, so the dialog's body is not one.
function UnlockSteps({ step, busy, run, loginPrivate, refresh }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  if (step === "private-login") {
    return (
      <form className="grid gap-2 sm:grid-cols-2" onSubmit={(e) => {
        e.preventDefault();
        if (username && password) run(() => loginPrivate({ username, password }));
      }}>
        <label htmlFor="dock-private-user" className="sr-only">Username</label>
        <input id="dock-private-user" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username"
          placeholder="Username" className={field} />
        <label htmlFor="dock-private-password" className="sr-only">Password</label>
        <input id="dock-private-password" type="password" value={password} onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password" placeholder="Password" className={field} />
        <button type="submit" disabled={busy || !username || !password} className={`${primary} sm:col-span-2`}>
          {busy ? "Signing in…" : "Sign in privately"}
        </button>
        <p className="text-xs text-muted sm:col-span-2">The private session ends after 15 minutes without use, after one hour, or if the page reloads.</p>
      </form>
    );
  }
  if (step !== "second-factor") return null;
  return (
    <button type="button" disabled={busy} className={primary}
      onClick={() => run(async () => { await secondFactor.confirmLogin(); await refresh(); })}>
      <KeyIcon width="15" height="15" /> {busy ? "Waiting for your key…" : "Use security key"}
    </button>
  );
}

const fail = (e) => e?.detail ?? (e?.status === 404 ? "This is only available on the private path (the deployed Argus)."
  : e?.name === "NotAllowedError" ? "The key confirmation was cancelled." : e?.message ?? "Something went wrong.");

export default function ConsoleAccessDialog({ request, openIds, full, onCancel, onEnter }) {
  const { user, loginPrivate, refresh } = useAuth();
  const ref = useRef(null);
  const titleId = useId();
  const reasonId = useId();
  const fixed = request.incident ?? null;
  const [host, setHost] = useState(fixed ? hostOf(fixed.target) : request.host ?? DOCK_HOSTS[1]);
  const [incidents, setIncidents] = useState(null);
  const [incidentId, setIncidentId] = useState(fixed?.id ?? "");
  const [reason, setReason] = useState(fixed ? `Investigate ${fixed.id} on ${hostOf(fixed.target)}` : "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { if (ref.current && !ref.current.open) ref.current.showModal(); }, []);

  useEffect(() => {
    if (fixed) return undefined;
    let alive = true;
    argus.listIncidents({ limit: 50 }).then((d) => alive && setIncidents(d?.incidents ?? d ?? []))
      .catch(() => alive && setIncidents([]));
    return () => { alive = false; };
  }, [fixed]);

  const choices = useMemo(() => (fixed ? [fixed] : hostIncidents(incidents, host)), [fixed, incidents, host]);
  useEffect(() => {
    if (fixed) return;
    const first = choices.find((i) => !openIds.includes(i.id));
    setIncidentId((id) => (choices.some((i) => i.id === id) ? id : first?.id ?? ""));
  }, [fixed, choices, openIds]);

  const run = async (fn) => {
    setBusy(true);
    setError("");
    try { await fn(); } catch (e) { setError(fail(e)); } finally { setBusy(false); }
  };

  const kase = dockAccess(user);
  const incident = choices.find((i) => i.id === incidentId);
  const canEnter = kase === "ready" && incident && !openIds.includes(incident.id) && !full && reason.trim().length >= 3;
  const submit = () => { if (canEnter) run(() => onEnter(incident, reason.trim())); };

  return (
    <dialog ref={ref} aria-labelledby={titleId} onClose={onCancel}
      className="m-auto max-h-[calc(100dvh-2rem)] w-[min(32rem,calc(100vw-2rem))] overflow-y-auto overflow-x-hidden rounded-2xl border border-line bg-card p-0 text-body shadow-[0_24px_64px_-16px_rgb(0_0_0/0.45)] backdrop:bg-black/30">
      <div className="flex flex-col">
        <div className="flex items-start gap-3 border-b border-line px-5 py-4">
          <span className="grid size-9 shrink-0 place-items-center rounded-xl border border-line bg-field text-ink">
            <TerminalIcon width="18" height="18" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-[15px] font-medium text-ink">Open the operator console</h2>
            <p className="mt-0.5 text-xs text-muted">Commands run through Argus&apos;s own tools on the lab host. No shell; writes need an approval.</p>
          </div>
        </div>

        <div className="flex flex-col gap-4 px-5 py-4">
          {!fixed && (
            <fieldset>
              <legend className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Host</legend>
              <div className="flex flex-wrap gap-2">
                {DOCK_HOSTS.map((h) => (
                  <label key={h} className={`flex cursor-pointer items-center gap-2 rounded-xl border px-3 py-2 text-sm transition has-[:focus-visible]:ring-[3px] has-[:focus-visible]:ring-accent/30 ${host === h ? "border-accent bg-accent/10 text-ink" : "border-line text-muted hover:text-ink"}`}>
                    <input type="radio" name="dock-host" value={h} checked={host === h} onChange={() => setHost(h)} className="sr-only" />
                    <Server width="15" height="15" /><span className="font-mono">{h}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          )}

          <fieldset>
            <legend className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Incident</legend>
            {!fixed && incidents === null && <p className="text-sm text-muted" role="status">Loading the incidents…</p>}
            {!fixed && incidents !== null && !choices.length && (
              <p className="text-sm text-muted">No incident on <span className="font-mono text-ink">{host}</span>. The console works inside an incident: start an investigation of a service on this host first.</p>
            )}
            <div className="flex max-h-48 flex-col gap-1.5 overflow-y-auto">
              {choices.map((i) => {
                const taken = openIds.includes(i.id);
                return (
                  <label key={i.id} className={`flex cursor-pointer items-center gap-3 rounded-xl border px-3 py-2 text-sm transition has-[:focus-visible]:ring-[3px] has-[:focus-visible]:ring-accent/30 ${incidentId === i.id ? "border-accent bg-accent/10" : "border-line hover:bg-ink/5"} ${taken ? "cursor-not-allowed opacity-60" : ""}`}>
                    <input type="radio" name="dock-incident" value={i.id} checked={incidentId === i.id} disabled={taken || Boolean(fixed)}
                      onChange={() => setIncidentId(i.id)} className="sr-only" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-ink">{i.target.split("/").slice(1).join("/") || i.target}</span>
                      <span className="block truncate font-mono text-xs text-muted">{i.id}{taken ? " · already open" : ""}</span>
                    </span>
                    {i.status && <StatusBadge status={i.status} />}
                  </label>
                );
              })}
            </div>
            {full && <p className="mt-2 text-xs text-muted">Four consoles are open: disconnect one first.</p>}
          </fieldset>

          {COPY[kase] && (
            <div className={`rounded-xl border px-4 py-3 text-sm ${kase === "unlock" ? "border-line bg-ink/[0.03]" : "border-amber-400/30 bg-amber-400/10"}`}>
              <p className="flex items-center gap-2 font-medium text-ink">
                <CircleAlert width="16" height="16" className={kase === "unlock" ? "text-accent-hover" : "text-amber-500"} />
                {COPY[kase][0]}
              </p>
              <p className="mt-1 text-muted">{COPY[kase][1]}</p>
              {kase === "one-key" && (
                <Link to="/account/security" onClick={onCancel}
                  className="mt-3 inline-flex h-9 items-center rounded-lg bg-accent-solid px-3 text-sm font-medium text-white hover:bg-accent-solid-hover">
                  Register your second key
                </Link>
              )}
              {kase === "unlock" && (
                <div className="mt-3">
                  <UnlockSteps step={unlockStep(user)} busy={busy} run={run} loginPrivate={loginPrivate} refresh={refresh} />
                </div>
              )}
            </div>
          )}

          {kase === "ready" && (
            <div>
              <label htmlFor={reasonId} className="mb-1.5 flex flex-wrap items-baseline justify-between gap-x-2 text-sm font-medium text-ink">
                Reason for access <span className="text-xs font-normal text-muted">Required · recorded with your name</span>
              </label>
              <textarea id={reasonId} rows={2} required minLength={3} maxLength={300} value={reason} autoFocus
                onChange={(e) => setReason(e.target.value)} placeholder="What will you check or fix?" className={textareaClass}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } }} />
            </div>
          )}

          {error && <p role="alert" className="text-[13px] text-danger">{error}</p>}
        </div>

        <div className="flex justify-end gap-2 border-t border-line px-5 py-3">
          <button type="button" onClick={onCancel}
            className="h-9 cursor-pointer rounded-lg border border-line px-3 text-sm text-ink hover:bg-ink/5">Cancel</button>
          {kase === "ready" && (
            <button type="button" onClick={submit} disabled={!canEnter || busy}
              className="h-9 cursor-pointer rounded-lg bg-accent-solid px-3 text-sm font-medium text-white transition enabled:hover:bg-accent-solid-hover disabled:cursor-not-allowed disabled:bg-disabled disabled:text-faint">
              {busy ? "Opening…" : "Enter the console"}
            </button>
          )}
        </div>
      </div>
    </dialog>
  );
}
