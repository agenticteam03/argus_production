import { clock } from "../utils/format.js";
import { hostOf } from "../utils/incidentView.js";
import { Card, InsetRow, Segmented } from "./ui.jsx";

// Hand-rolled SVG line chart, no library. Expected data (GET incident metrics window, see hooks/useIncidentMetrics.js):
//   { from, to, series: [{ key, title, unit?, max?, fired?, points: [[time, value | null], ...] }] }
// A null value is a gap in the line, never a zero. Values are drawn from 0 up to `max` (or the largest sample).
const W = 300, H = 72, T = 5, B = 3;
export const RANGES = [{ value: "15m", label: "15 m" }, { value: "30m", label: "30 m" }, { value: "1h", label: "1 h" }];

const ms = (t) => (typeof t === "number" ? t : Date.parse(t));
const fmt = (v, unit) => (v == null ? "—" : `${Number.isInteger(v) ? v : v.toFixed(1)}${unit ? ` ${unit}` : ""}`);

export default function MetricChart({ series, from, to, band }) {
  const t0 = ms(from);
  const t1 = ms(to);
  const pts = (series.points ?? []).map(([t, v]) => [ms(t), Number.isFinite(v) ? v : null]);
  const values = pts.map((p) => p[1]).filter((v) => v != null);
  const lastValue = values.at(-1) ?? null;
  const max = series.max ?? Math.max(1, ...values);
  const x = (t) => 2 + ((t - t0) / (t1 - t0)) * (W - 4);
  const y = (v) => T + (1 - Math.min(Math.max(v, 0), max) / max) * (H - T - B);

  let d = "";
  let on = false;
  for (const [t, v] of pts) {
    if (v == null || t < t0 || t > t1) { on = false; continue; }
    d += `${on ? "L" : "M"}${x(t).toFixed(1)},${y(v).toFixed(1)}`;
    on = true;
  }
  const bx0 = band ? Math.max(2, x(band.from)) : 0;
  const bx1 = band ? Math.min(W - 2, x(band.to)) : 0;
  const label = `${series.title}: ${fmt(lastValue, series.unit)}`;

  return (
    <InsetRow className="px-3 pb-2 pt-2">
      <div className="flex items-baseline justify-between gap-2 text-[13px]">
        <span className="min-w-0 truncate text-body">{series.title}</span>
        <span className={`font-mono text-xs ${series.fired ? "text-red-300" : "text-ink"}`}>{fmt(lastValue, series.unit)}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" role="img" aria-label={label} className="mt-1 block h-[4.4rem] w-full">
        <line x1="0" x2={W} y1={H - B} y2={H - B} vectorEffect="non-scaling-stroke" className="stroke-line" />
        {band && bx1 > bx0 && <rect x={bx0} y={T} width={bx1 - bx0} height={H - T - B} className="fill-red-400/[0.06]" />}
        {d && <path d={d} fill="none" strokeWidth="1.4" strokeLinejoin="round" vectorEffect="non-scaling-stroke" className={series.fired ? "stroke-red-400" : "stroke-accent/75"} />}
      </svg>
      <div className="mt-0.5 flex justify-between font-mono text-[11px] text-muted">
        <span>{clock(t0)}</span><span>{clock((t0 + t1) / 2)}</span><span>{clock(t1)}</span>
      </div>
    </InsetRow>
  );
}

const windowOf = (metrics, incident) => (incident?.opened_at ? { from: ms(incident.opened_at), to: incident.closed_at ? ms(incident.closed_at) : ms(metrics.to) } : null);

export function ChartGrid({ metrics, incident, limit, columns = "sm:grid-cols-2 xl:grid-cols-3" }) {
  const band = windowOf(metrics, incident);
  return (
    <div className={`grid gap-2 ${columns}`}>
      {metrics.series.slice(0, limit).map((s) => <MetricChart key={s.key} series={s} from={metrics.from} to={metrics.to} band={band} />)}
    </div>
  );
}

// The "Metrics" tab.
export function MetricsTab({ metrics, incident, range, onRange }) {
  return (
    <Card title={`${hostOf(incident.target) || "Host"} around the incident`} right={<Segmented label="Range" options={RANGES} value={range} onChange={onRange} />}>
      <ChartGrid metrics={metrics} incident={incident} />
      <p className="mt-3 text-xs text-muted">The shaded band is the incident window. A missing sample is a gap, never zero.</p>
    </Card>
  );
}

export function MiniCharts({ metrics, incident, onOpen }) {
  return (
    <Card title="Around the incident" right={<button type="button" onClick={onOpen} className="cursor-pointer text-xs text-accent-hover hover:underline">All metrics</button>}>
      <ChartGrid metrics={metrics} incident={incident} limit={2} columns="sm:grid-cols-2" />
    </Card>
  );
}
