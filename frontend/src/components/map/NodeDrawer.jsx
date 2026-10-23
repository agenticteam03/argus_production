import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext.jsx";
import { useTargetMetrics } from "../../hooks/useTargetMetrics.js";
import { argus } from "../../services/index.js";
import { investigationError } from "../../utils/investigationError.js";
import { HEALTH_META, HexGlyph } from "../Glyph.jsx";
import { Close, Hint, Pill, Server } from "../ui.jsx";
import { fmtSignal, PROBLEM_LABELS, ROLES } from "./mapModel.js";

// The drawer that opens when a box of the system map is selected (ui-graphs prototype, openNode): what the component
// is, its problems against their thresholds, its last 15 minutes of signals, the incident it belongs to and, for an
// account that may, a button to investigate it. Esc, the close button or a click outside closes it; focus goes back
// to the box that opened it.
const SEVERITY_TONE = { critical: "red", warning: "amber", info: "blue" };
const BAR = { critical: "bg-red-400", warning: "bg-amber-400", info: "bg-sky-400" };

// One signal's last window as a small line, with the warning line when the API gives one.
function Sparkline({ series }) {
  const pts = (series.points ?? []).filter((p) => typeof p[1] === "number");
  const last = pts.at(-1)?.[1] ?? null;
  const t = series.thresholds;
  const over = last != null && t && (t.direction === "below" ? last <= t.warning : last >= t.warning);
  if (pts.length < 2) {
    return (
      <div className="rounded-xl border border-line bg-field/50 p-3">
        <div className="flex justify-between text-xs"><span className="text-muted">{series.title}</span><span>{fmtSignal(last, series.unit)}</span></div>
        <p className="mt-3 text-xs text-muted">No current samples</p>
      </div>
    );
  }
  const W = 180, H = 44, xs = pts.map((p) => Date.parse(p[0])), ys = pts.map((p) => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs);
  const top = Math.max(series.max ?? 0, ...ys, t?.warning ?? 0) || 1;
  const x = (v) => ((v - x0) / (x1 - x0 || 1)) * W, y = (v) => H - 3 - (v / top) * (H - 6);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${x(xs[i]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ");
  return (
    <div className="rounded-xl border border-line bg-field/50 p-3">
      <div className="flex justify-between gap-2 text-xs"><span className="truncate text-muted">{series.title}</span><span className={`font-medium ${over ? "text-amber-300" : "text-ink"}`}>{fmtSignal(last, series.unit)}</span></div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={`${series.title}, last 15 minutes, now ${fmtSignal(last, series.unit)}`} className="mt-1.5 block h-11 w-full">
        {t?.warning != null && <line x1="0" x2={W} y1={y(t.warning)} y2={y(t.warning)} strokeDasharray="3 3" vectorEffect="non-scaling-stroke" className="stroke-amber-400/60" />}
        <path d={d} fill="none" strokeWidth="1.8" strokeLinejoin="round" vectorEffect="non-scaling-stroke" className={over ? "stroke-amber-400" : "stroke-accent"} />
      </svg>
    </div>
  );
}

function Problem({ p }) {
  const max = Math.max(Math.abs(p.value ?? 0), Math.abs(p.threshold ?? 0)) || 1;
  const fill = Math.min(100, (Math.abs(p.value ?? 0) / max) * 100), tick = Math.min(100, (Math.abs(p.threshold ?? 0) / max) * 100);
  return (
    <li className="rounded-xl border border-line bg-field/50 p-3">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-medium text-ink">{PROBLEM_LABELS[p.kind] ?? p.kind} · {p.summary}</p>
        <Pill tone={SEVERITY_TONE[p.severity] ?? "neutral"}>{p.severity}</Pill>
      </div>
      {p.value != null && (
        <>
          <p className="mt-1 text-xs text-muted">Observed <span className="font-medium text-body">{fmtSignal(p.value, p.unit)}</span>{p.threshold != null && <> · threshold {fmtSignal(p.threshold, p.unit)}</>}</p>
          {p.threshold != null && (
            <div role="meter" aria-valuenow={p.value} aria-valuemin={0} aria-valuemax={max} aria-label={`${PROBLEM_LABELS[p.kind] ?? p.kind}: ${p.value} against ${p.threshold}`} className="relative mt-2 h-1.5 rounded-full bg-ink/10">
              <span className={`absolute inset-y-0 left-0 rounded-full ${BAR[p.severity] ?? "bg-accent"}`} style={{ width: `${fill}%` }} />
              <i className="absolute -top-1 h-3.5 w-0.5 rounded bg-ink/70" style={{ left: `calc(${tick}% - 1px)` }} />
            </div>
          )}
        </>
      )}
    </li>
  );
}

export default function NodeDrawer({ node, incidents = [], incident = null, onClose }) {
  const [shown, setShown] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const closeRef = useRef(null);
  const user = useAuth()?.user;      // no AuthProvider (a test): no actions, so no "Investigate this"
  const navigate = useNavigate();
  const metrics = useTargetMetrics(node.idle ? null : node.target);
  const meta = HEALTH_META[node.health] ?? HEALTH_META.unknown;
  const role = node.role ? ROLES[node.role] : null;
  const open = incidents.filter((i) => i.target === node.target && ["queued", "running", "escalated"].includes(i.status));
  const linked = incident && node.role ? [incident] : open;
  const canInvestigate = Boolean(user?.actions?.includes("start_investigation")) && Boolean(node.target) && !node.idle;

  useEffect(() => {
    const opener = document.activeElement;
    const raf = requestAnimationFrame(() => setShown(true));
    closeRef.current?.focus();
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("keydown", onKey);
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
    };
  }, [onClose]);

  const investigate = async () => {
    setBusy(true);
    setError("");
    try {
      const { incident_id } = await argus.startInvestigation({ target: node.target, requestKind: "check", reason: "Opened from the system map" });
      navigate(`/incidents/${incident_id}`);
    } catch (err) {
      setError(investigationError(err));
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-40">
      <div onClick={onClose} className={`absolute inset-0 bg-scrim transition-opacity duration-300 motion-reduce:transition-none ${shown ? "opacity-100" : "opacity-0"}`} />
      <aside role="dialog" aria-modal="true" aria-label={`${node.label}, ${meta.label}`}
        className={`absolute inset-y-0 right-0 flex w-full flex-col border-l border-line bg-card shadow-2xl transition-transform duration-300 motion-reduce:transition-none sm:w-[500px] ${shown ? "translate-x-0" : "translate-x-full"}`}>
        <header className="flex items-start gap-3 border-b border-line p-5">
          <HexGlyph health={node.glyph ?? node.health} icon={node.icon} size={36} />
          <div className="min-w-0 flex-1">
            <h2 className="truncate font-mono text-[15px] font-semibold text-ink">{node.label}</h2>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span className="inline-flex items-center gap-1 rounded-full border border-line px-2.5 py-0.5 text-xs text-muted"><Server width="12" height="12" />{node.host}</span>
              <span className={`inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-0.5 text-xs font-medium ${meta.text}`}><span className="size-1.5 rounded-full bg-current" />{meta.label}</span>
              {role && <Hint align="left" text={role.help}><Pill tone={role.tone}>{role.label}</Pill></Hint>}
              {node.idle && <Hint align="left" text="A scenario container that is intentionally stopped. No failure is implied."><Pill>Idle (expected)</Pill></Hint>}
            </div>
          </div>
          <button ref={closeRef} type="button" onClick={onClose} aria-label="Close" className="grid size-9 shrink-0 cursor-pointer place-items-center rounded-lg text-muted hover:bg-ink/5 hover:text-ink focus-visible:outline-2 focus-visible:outline-accent-hover">
            <Close width="18" height="18" />
          </button>
        </header>

        <div className="min-h-0 flex-1 space-y-6 overflow-y-auto p-5">
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div><dt className="text-xs text-muted">{node.kind === "host" ? "Host state" : "Container state"}</dt><dd className="mt-0.5 text-ink">{node.status ?? "unknown"}</dd></div>
            <div><dt className="text-xs text-muted">Docker networks</dt><dd className="mt-0.5 break-words text-ink">{node.networks?.length ? node.networks.map((n) => <code key={n} className="mr-1 font-mono text-xs">{n}</code>) : <span className="text-muted">Unavailable</span>}</dd></div>
            {(node.info ?? []).filter((r) => r.label !== "Declared networks").map((r) => (
              <div key={r.label}><dt className="text-xs text-muted">{r.label}</dt><dd className="mt-0.5 break-words text-ink">{r.value}</dd></div>
            ))}
          </dl>

          <section>
            <h3 className="text-sm font-medium text-ink">Problems</h3>
            {node.problems?.length ? (
              <ul className="mt-2 space-y-2">{node.problems.map((p, i) => <Problem key={`${p.kind}-${i}`} p={p} />)}</ul>
            ) : (
              <p className="mt-1.5 text-sm text-muted">{node.idle ? "Idle by design. No active health assessment." : "No problems reported for this box."}</p>
            )}
          </section>

          <section>
            <h3 className="text-sm font-medium text-ink">Recent signals <span className="font-normal text-muted">· last 15 min</span></h3>
            {node.idle ? (
              <p className="mt-1.5 text-sm text-muted">No recent reads: the scenario container is not running.</p>
            ) : metrics === undefined ? (
              <div className="mt-2 grid grid-cols-2 gap-2"><div className="h-[86px] animate-pulse rounded-xl bg-ink/5" /><div className="h-[86px] animate-pulse rounded-xl bg-ink/5" /></div>
            ) : metrics ? (
              <div className="mt-2 grid grid-cols-2 gap-2">{metrics.series.map((s) => <Sparkline key={s.key} series={s} />)}</div>
            ) : (
              <p className="mt-1.5 text-sm text-muted">No current samples for this component.</p>
            )}
          </section>

          {linked.length > 0 && (
            <section>
              <h3 className="text-sm font-medium text-ink">{incident && node.role ? "This incident" : "Needs attention"}</h3>
              <ul className="mt-1.5 space-y-1 text-sm">
                {linked.map((i) => (
                  <li key={i.id}><Link to={`/incidents/${i.id}`} className="font-mono text-accent-hover hover:underline">{i.id}</Link>{i.status && <span className="text-muted"> · {i.status}</span>}</li>
                ))}
              </ul>
            </section>
          )}

          {canInvestigate && (
            <div>
              <button type="button" onClick={investigate} disabled={busy}
                className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-xl bg-accent-solid px-4 text-sm font-medium text-white hover:bg-accent-solid-hover disabled:cursor-wait disabled:opacity-70 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-hover">
                {busy ? "Starting…" : "Investigate this"}
              </button>
              {error && <p role="alert" className="mt-2 text-sm text-red-300">{error}</p>}
            </div>
          )}
          <p className="border-t border-line pt-4 text-xs text-muted">Container health and connection health are checked separately. A healthy box can have a broken dependency.</p>
        </div>
      </aside>
    </div>
  );
}
