import PrivateLogin from "./PrivateLogin.jsx";
import { Card } from "./ui.jsx";

// ACR-0032: the two steps before a privileged decision, wherever it is offered (Actions, an incident, the reference
// sources): the private login, then the security key that completes that session. `run` reports a failure.
export default function PrivateAccess({ step, busy, run, loginPrivate, secondFactor, refresh }) {
  if (step === "private-login") return <PrivateLogin busy={busy} onSubmit={(credentials) => run(() => loginPrivate(credentials))} />;
  if (step !== "second-factor") return null;
  return <Card title="Confirm with your security key">
    <p className="mb-3 text-sm text-muted">Your private session is open. Touch your security key to confirm it before any decision.</p>
    <button type="button" disabled={busy} onClick={() => run(async () => { await secondFactor.confirmLogin(); await refresh(); })}
      className="cursor-pointer rounded-lg bg-accent-solid px-4 py-2 text-sm text-white disabled:opacity-50">Use security key</button>
  </Card>;
}
