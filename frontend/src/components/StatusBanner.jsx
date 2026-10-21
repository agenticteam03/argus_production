import { Link } from "react-router-dom";
import { fleetStatus } from "../utils/fleetStatus.js";
import { CircleAlert, CircleCheck, Pill, Radio, Warning } from "./ui.jsx";

// The Dashboard's summary: is anything wrong, or is everything fine? Built from the overview and (when it answers)
// the topology; see utils/fleetStatus.js for exactly what counts.
const TONE = {
  good: { box: "border-emerald-400/25 bg-emerald-400/[0.05]", icon: "text-emerald-300", Icon: CircleCheck },
  warn: { box: "border-amber-400/25 bg-amber-400/[0.05]", icon: "text-amber-300", Icon: Warning },
  critical: { box: "border-red-400/30 bg-red-400/[0.06]", icon: "text-red-300", Icon: CircleAlert },
  checking: { box: "border-line bg-card/80", icon: "text-muted", Icon: Radio },
};
const DOT = { critical: "bg-red-400", warning: "bg-amber-400" };
const CELL = { ok: "fill-emerald-400/25 stroke-emerald-400", degraded: "fill-amber-400/25 stroke-amber-400", failed: "fill-red-400/30 stroke-red-400", unknown: "fill-slate-500/20 stroke-slate-500" };
const HEALTH_WORD = { ok: "running", degraded: "degraded", failed: "failing", unknown: "unknown" };

// One hexagon per monitored component, coloured by its health. Decorative: the counts next to it say the same in words.
function Honeycomb({ nodes }) {
  const PER_ROW = 6;
  const rows = Array.from({ length: Math.ceil(nodes.length / PER_ROW) }, (_, r) => nodes.slice(r * PER_ROW, (r + 1) * PER_ROW));
  return (
    <svg role="img" aria-label={`Components: ${["ok", "degraded", "failed", "unknown"].map((h) => `${nodes.filter((n) => n.health === h).length} ${HEALTH_WORD[h]}`).join(", ")}`}
      viewBox={`0 0 ${PER_ROW * 26 + 13} ${rows.length * 22 + 6}`} className="h-auto w-44 shrink-0">
      {rows.map((row, r) => row.map((n, c) => (
        <g key={n.id} transform={`translate(${c * 26 + (r % 2 ? 13 : 0) + 2},${r * 22 + 2})`}>
          <title>{`${n.label}: ${HEALTH_WORD[n.health]}`}</title>
          <polygon points="12,1 22,6.5 22,17.5 12,23 2,17.5 2,6.5" strokeWidth="1.3" className={CELL[n.health]} />
        </g>
      )))}
    </svg>
  );
}

const Stat = ({ label, value, sub }) => (
  <div className="min-w-0 px-5 py-3">
    <dt className="text-xs text-muted">{label}</dt>
    <dd className="mt-0.5 text-xl font-semibold tracking-tight">{value}</dd>
    {sub && <dd className="text-xs text-muted">{sub}</dd>}
  </div>
);

export default function StatusBanner({ incidents, hostMetrics, topology, hosts, loaded }) {
  const s = fleetStatus({ incidents, hostMetrics, topology, hosts, loaded, now: Date.now() });
  const { box, icon, Icon } = TONE[s.level];
  const st = s.stats;

  return (
    <section aria-label="Infrastructure status" className={`overflow-hidden rounded-2xl border ${box}`}>
      <div className="flex flex-wrap items-start gap-4 p-5">
        <Icon width="26" height="26" className={`mt-0.5 shrink-0 ${icon}`} />
        <div className="min-w-0 flex-1 basis-72">
          <h2 role="status" className="text-lg font-semibold tracking-tight">{s.headline}</h2>
          <p className="mt-0.5 text-sm text-soft">{s.detail}</p>

          {s.attention.length > 0 && (
            <ul className="mt-3 space-y-1.5">
              {s.attention.map((a, i) => (
                <li key={i} className="flex items-start gap-2 text-sm">
                  <span aria-hidden="true" className={`mt-1.5 size-2 shrink-0 rounded-full ${DOT[a.tone]}`} />
                  <span className="min-w-0 break-words">
                    <span className="sr-only">{a.tone === "critical" ? "Critical: " : "Warning: "}</span>
                    {a.text}
                    {a.to && <> · <Link to={a.to} className="text-accent-hover hover:underline">Open incident</Link></>}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {s.level !== "checking" && (
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {s.level === "good" && <Pill tone="green">No open issues</Pill>}
              {s.counts.critical > 0 && <Pill tone="red">{s.counts.critical} critical</Pill>}
              {s.counts.warning > 0 && <Pill tone="amber">{s.counts.warning} {s.counts.warning === 1 ? "warning" : "warnings"}</Pill>}
              {s.counts.running > 0 && <Pill tone="blue" pulse>{s.counts.running} {s.counts.running === 1 ? "investigation" : "investigations"} running</Pill>}
            </div>
          )}

          {s.hosts.length > 0 && (
            <p className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
              {s.hosts.map((h) => (
                <span key={h.host} className={`inline-flex items-center gap-1.5 ${h.available && !h.stale ? "" : "text-amber-300"}`}>
                  <Radio width="13" height="13" aria-hidden="true" />
                  <span className="font-medium text-body">{h.host}</span>
                  {h.available ? (h.age ? `heartbeat ${h.age}${h.stale ? " (stale)" : ""}` : "reporting") : "no signal"}
                </span>
              ))}
            </p>
          )}
        </div>
        {s.nodes.length > 0 && <Honeycomb nodes={s.nodes} />}
      </div>

      {st && (
        <dl className="grid grid-cols-2 divide-x divide-line border-t border-line bg-field/40 sm:grid-cols-4">
          <Stat label="Hosts reporting" value={`${st.hostsReporting}/${st.hostsTotal}`} sub={st.hostsReporting === st.hostsTotal ? "Fresh samples" : "Some signals are missing"} />
          <Stat label="Active runs" value={st.running} sub={st.escalated ? `${st.escalated} escalated in 24 h` : "Nothing escalated in 24 h"} />
          {st.links && <Stat label="Checked links OK" value={`${st.links.ok}/${st.links.total}`} sub={st.links.ok === st.links.total ? "All dependencies answer" : `${st.links.total - st.links.ok} not ok`} />}
          {st.components && <Stat label="Components" value={st.components.total} sub={st.components.unknown ? `${st.components.unknown} unknown` : "All states known"} />}
        </dl>
      )}
    </section>
  );
}
