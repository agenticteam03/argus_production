import { useId, useState } from "react";
import hero from "../../public/images/argus-hero.jpg";
import { Logo } from "../components/ui.jsx";

const focusRing =
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-hover";

const inputClass =
  "h-11 w-full rounded-[10px] border border-field-line bg-field px-3.5 text-sm outline-none " +
  "transition placeholder:text-faint hover:border-field-hover motion-reduce:transition-none " +
  "focus:border-accent focus:ring-[3px] focus:ring-accent/20 " +
  "aria-[invalid=true]:border-danger aria-[invalid=true]:ring-[3px] aria-[invalid=true]:ring-danger/10";

const EyeIcon = ({ off }) => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z" />
    <circle cx="12" cy="12" r="3" />
    {off && <path d="M4 4l16 16" />}
  </svg>
);

export default function LoginPage({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const errorId = useId();

  const canSubmit = username.trim() !== "" && password !== "" && !loading;

  async function handleSubmit(event) {
    event.preventDefault();
    if (!canSubmit) return;
    setLoading(true);
    setError("");
    try {
      await onLogin({ username: username.trim(), password });
    } catch (err) {
      setError(err?.message || "Something went wrong. Please try again.");
      setLoading(false);
    }
  }

  const clearError = () => error && setError("");

  return (
    <div className="grid min-h-full place-items-center p-3 sm:p-6">
      <main className="grid w-full max-w-[1120px] grid-cols-1 overflow-hidden rounded-[20px] border border-line bg-card shadow-[0_40px_120px_-40px_rgba(59,130,246,0.25)] sm:rounded-3xl min-[900px]:min-h-[min(700px,calc(100vh-48px))] min-[900px]:grid-cols-2">
        <section className="flex flex-col px-5 py-6 sm:p-8">
          <header className="flex items-center gap-2.5 text-xl font-semibold tracking-tight">
            <Logo width="22" height="22" className="text-ink" />
            <span>Argus</span>
          </header>

          <form className="m-auto flex w-full max-w-[360px] flex-col gap-5 py-8" onSubmit={handleSubmit} noValidate>
            <h1 className="text-[28px] font-semibold tracking-[-0.03em]">Welcome back</h1>
            <p className="-mt-3.5 mb-2 text-sm text-muted">Log in to Argus to continue.</p>

            <div className="flex flex-col gap-2">
              <label htmlFor="username" className="text-[13px] font-medium">Username</label>
              <input
                id="username"
                type="text"
                autoComplete="username"
                placeholder="Enter your username"
                className={inputClass}
                value={username}
                onChange={(e) => { setUsername(e.target.value); clearError(); }}
              />
            </div>

            <div className="flex flex-col gap-2">
              <div className="flex items-baseline justify-between">
                <label htmlFor="password" className="text-[13px] font-medium">Password</label>
                <a href="#forgot" className={`rounded text-[13px] text-accent-hover hover:underline hover:underline-offset-4 ${focusRing}`}>
                  Forgot password?
                </a>
              </div>
              <div className="relative">
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  placeholder="••••••••"
                  className={`${inputClass} pr-11`}
                  value={password}
                  aria-invalid={error ? "true" : undefined}
                  aria-describedby={error ? errorId : undefined}
                  onChange={(e) => { setPassword(e.target.value); clearError(); }}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  className={`absolute right-0 top-0 grid h-11 w-11 cursor-pointer place-items-center rounded-[10px] text-muted hover:text-ink ${focusRing}`}
                >
                  <EyeIcon off={showPassword} />
                </button>
              </div>
              {error && <p id={errorId} role="alert" className="text-[13px] text-danger">{error}</p>}
            </div>

            <button
              type="submit"
              disabled={!canSubmit}
              className={`mt-1 inline-flex h-11 cursor-pointer items-center justify-center gap-2.5 rounded-[10px] bg-accent text-sm font-medium text-white shadow-[inset_0_0_0_1px_rgba(255,255,255,0.12),0_10px_30px_-10px_rgba(59,130,246,0.6)] transition motion-reduce:transition-none enabled:hover:bg-accent-hover enabled:active:translate-y-px disabled:cursor-not-allowed disabled:bg-disabled disabled:text-faint disabled:shadow-[inset_0_0_0_1px_var(--color-line)] ${focusRing}`}
            >
              {loading && (
                <span className="size-3.5 animate-spin rounded-full border-2 border-white/35 border-t-white motion-reduce:[animation-duration:1.6s]" aria-hidden="true" />
              )}
              {loading ? "Logging in…" : "Log in"}
            </button>
          </form>
        </section>

        <aside className="relative hidden bg-card min-[900px]:block" aria-hidden="true">
          <img src={hero} alt="" className="hero-img absolute inset-y-0 right-0 h-full w-[86%] object-cover object-top" />
          <div className="hero-fade pointer-events-none absolute inset-0" />
        </aside>
      </main>
    </div>
  );
}
