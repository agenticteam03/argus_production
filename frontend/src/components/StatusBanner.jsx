import { Link } from "react-router-dom";
import { fleetStatus } from "../utils/fleetStatus.js";
import { Box, CircleAlert, CircleCheck, Database, Pill, Radio, Server, Warning } from "./ui.jsx";

// The Dashboard's summary: is anything wrong, or is everything fine? Built from the overview and (when it answers)
// the topology; see utils/fleetStatus.js for exactly what counts.
const TONE = {
  good: { box: "border-emerald-400/25 bg-emerald-400/[0.05]", icon: "text-emerald-300", Icon: CircleCheck },
  warn: { box: "border-amber-400/25 bg-amber-400/[0.05]", icon: "text-amber-300", Icon: Warning },
  critical: { box: "border-red-400/30 bg-red-400/[0.06]", icon: "text-red-300", Icon: CircleAlert },
  checking: { box: "border-line bg-card/80", icon: "text-muted", Icon: Radio },
};
const DOT = { critical: "bg-red-400", warning: "bg-amber-400" };
const HEALTH_WORD = { ok: "running", degraded: "degraded", failed: "failing", unknown: "unknown" };
// Health -> [edge/fill colour, icon colour]. Same idea as the MVP: tone = health, icon = what the component is.
const HEX_TONE = { ok: ["text-emerald-400", "text-emerald-300"], degraded: ["text-amber-400", "text-amber-300"], failed: ["text-red-400", "text-red-300"], unknown: ["text-slate-500", "text-muted"] };
const KIND_ICON = { box: Box, database: Database, server: Server };
const HEX_POINTS = "20,1.5 38.2,12 38.2,32 20,42.5 1.8,32 1.8,12";

// One hexagon per monitored component: its colour says how it is (green running, amber degraded, red failing, dashed
// grey unknown), its icon says what it is, and a failing one pulses. Decorative: the counts say the same in words.
function Hex({ node }) {
  const [tone, iconTone] = HEX_TONE[node.health];
  const Ico = KIND_ICON[node.icon] ?? Box;
  return (
    <span title={`${node.label}: ${HEALTH_WORD[node.health]}`} className={`relative inline-grid h-[33px] w-[30px] shrink-0 place-items-center ${tone}`}>
      <svg viewBox="0 0 40 44" aria-hidden="true" className="absolute inset-0 size-full overflow-visible">
        <polygon points={HEX_POINTS} strokeWidth="1.6" strokeDasharray={node.health === "unknown" ? "4 3" : undefined} className={`fill-current/15 stroke-current ${node.health === "failed" ? "hex-glow" : ""}`} />
        {node.health === "failed" && <polygon points={HEX_POINTS} strokeWidth="1.5" className="hex-pulse fill-none stroke-current" />}
      </svg>
      <Ico width="13" height="13" className={`relative ${iconTone}`} />
    </span>
  );
}

function Honeycomb({ nodes }) {
  const PER_ROW = 5;
  const rows = Array.from({ length: Math.ceil(nodes.length / PER_ROW) }, (_, r) => nodes.slice(r * PER_ROW, (r + 1) * PER_ROW));
  const label = ["ok", "degraded", "failed", "unknown"].map((h) => `${nodes.filter((n) => n.health === h).length} ${HEALTH_WORD[h]}`).join(", ");
  return (
    <div role="img" aria-label={`${nodes.length} components: ${label}`} className="shrink-0 pt-1">
      {rows.map((row, r) => (
        <div key={r} className="flex gap-1" style={{ marginLeft: r % 2 ? 17 : 0, marginTop: r ? -7 : 0 }}>
          {row.map((n) => <Hex key={n.id} node={n} />)}
        </div>
      ))}
    </div>
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
