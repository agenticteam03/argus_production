import { Arrow, Book, Warning } from "./ui.jsx";

const RISK = {
  high: ["High-risk action", "border-red-400/20 bg-red-400/10 text-red-300"],
  mutating: ["Mutating action", "border-amber-400/20 bg-amber-400/10 text-amber-300"],
  "read-only": ["Read-only", "border-emerald-400/20 bg-emerald-400/10 text-emerald-300"],
};
const badge = "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium";
const meta = "rounded-md border border-line bg-white/[0.03] px-2 py-0.5 text-xs text-muted";
const chip = "rounded-md border px-2 py-0.5 font-mono text-[11px]";
const MAX_TOOLS = 3;

export default function RunbookCard({ runbook: rb, onOpen }) {
  const [riskLabel, riskTone] = RISK[rb.risk];
  const isMutating = (t) => t.safety.startsWith("MUTATING");
  const tools = [...rb.tools.filter(isMutating), ...rb.tools.filter((t) => !isMutating(t))];

  return (
    <article className="group flex flex-col overflow-hidden rounded-2xl border border-line bg-card/80 transition hover:border-accent/40 hover:shadow-[0_0_40px_-20px_rgba(59,130,246,0.6)] motion-reduce:transition-none">
      <div className="flex flex-1 flex-col gap-4 p-5">
        <header className="flex items-start gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-accent/20 bg-accent/10 text-accent-hover">
            <Book />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-xs text-accent-hover">{rb.id}</span>
              <div className="flex gap-1.5">
                {rb.version && <span className={meta}>v{rb.version}</span>}
                <span className={`${meta} capitalize`}>{rb.status}</span>
              </div>
            </div>
            <h3 className="mt-1 text-base font-semibold leading-snug tracking-tight">{rb.title}</h3>
          </div>
        </header>

        <p className="line-clamp-3 text-[13px] leading-relaxed text-[#a3abba]">{rb.summary || "No summary available."}</p>

        <div className="flex flex-wrap items-center gap-2">
          <span className={`${badge} ${riskTone}`}><span className="size-1.5 rounded-full bg-current" />{riskLabel}</span>
          {rb.missing > 0 && (
            <span title="Argus will have limitations when running this runbook" className={`${badge} border-amber-400/20 bg-amber-400/10 text-amber-300`}>
              <Warning width="13" height="13" /> {rb.missing} missing {rb.missing === 1 ? "tool" : "tools"}
            </span>
          )}
        </div>

        <dl className="mt-auto grid grid-cols-[4.5rem_1fr] gap-x-3 gap-y-2.5 rounded-xl border border-line bg-field/60 p-3.5 text-xs">
          <dt className="pt-0.5 text-muted">Detector</dt>
          <dd><code className="font-mono text-[#d6dbe6]">{rb.detector ?? "—"}</code></dd>
          <dt className="pt-0.5 text-muted">Scope</dt>
          <dd className="leading-relaxed text-[#d6dbe6]">{rb.scope || "—"}</dd>
          {tools.length > 0 && (
            <>
              <dt className="pt-1 text-muted">Key tools</dt>
              <dd className="flex flex-wrap gap-1.5">
                {tools.slice(0, MAX_TOOLS).map((t) => (
                  <code key={t.name} title={t.safety} className={`${chip} ${isMutating(t) ? "border-red-400/20 bg-red-400/10 text-red-300" : "border-line bg-card text-muted"}`}>{t.name}</code>
                ))}
                {tools.length > MAX_TOOLS && <span className={`${chip} border-transparent text-muted`}>+{tools.length - MAX_TOOLS} more</span>}
              </dd>
            </>
          )}
        </dl>
      </div>

      <button
        onClick={() => onOpen(rb.id)}
        className="flex w-full cursor-pointer items-center justify-between border-t border-line px-5 py-3.5 text-[13px] font-medium text-accent-hover transition hover:bg-white/[0.03] focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent-hover motion-reduce:transition-none"
      >
        Read full runbook
        <Arrow width="15" height="15" className="transition group-hover:translate-x-0.5 motion-reduce:transition-none" />
      </button>
    </article>
  );
}
