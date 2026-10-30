import { Link } from "react-router-dom";
import DiagnoseForm from "../components/DiagnoseForm.jsx";
import IncidentRow from "../components/IncidentRow.jsx";
import StatusBanner from "../components/StatusBanner.jsx";
import SystemMap from "../components/map/SystemMap.jsx";
import { Arrow, Bell, Card, Empty, Inbox, LivePill, OutcomeBadge, Pill, SkeletonList } from "../components/ui.jsx";
import { useLiveOverview } from "../hooks/useLiveOverview.js";
import { useTopology } from "../hooks/useTopology.js";
import { dataSource } from "../services/index.js";
import { dateTime, timeAgo } from "../utils/format.js";
import { loadLevel, worstLevel } from "../utils/load.js";

// T-0016: until the first read answers, each card shimmers where its data will be, instead of saying "nothing yet".
function IncidentsCard({ incidents, loading, className }) {
  return (
    <Card title="Recent incidents" count={loading ? null : incidents.length} className={className}>
      {loading ? <SkeletonList label="Loading…" /> : incidents.length === 0 ? (
        <Empty icon={Inbox} title="No recent activity" text="Incidents from alerts, scheduled checks or manual runs will show up here." />
      ) : (
        <ul className="stagger space-y-2">
          {incidents.slice(0, 5).map((i) => <IncidentRow key={i.id} incident={i} compact />)}
        </ul>
      )}
      <Link to="/incidents" className="group mt-3 inline-flex items-center gap-1.5 text-[13px] text-accent-hover hover:underline">
        View full incident history <Arrow width="14" height="14" className="transition-transform group-hover:translate-x-0.5 motion-reduce:transition-none" />
      </Link>
    </Card>
  );
}

const HOST_LABELS = { "vm-095": "Host A", "vm-166": "Host T" };
const HOST_METRICS = [
  ["CPU", "cpu_busy_ratio"], ["Memory", "memory_used_ratio"], ["Disk /", "disk_used_ratio"],
];

// Load level -> [label, Pill tone, bar colour]. Colour is never the only signal: the label is always written.
const LEVEL = {
  ok: ["Normal", "green", "bg-emerald-400"],
  high: ["High", "amber", "bg-amber-400"],
  critical: ["Critical", "red", "bg-red-400"],
};

function HostMetricsCard({ rows, live, updatedAt, loading }) {
  return (
    <Card title="Host metrics" right={<LivePill live={live} source={dataSource} at={updatedAt} />}>
      {loading ? <SkeletonList label="Loading…" rows={2} className="h-[116px]" grid="space-y-4" /> : <div className="stagger space-y-4">
        {["vm-095", "vm-166"].map((host) => {
          const row = rows.find((item) => item.host === host);
          const levels = HOST_METRICS.map(([, key]) => loadLevel(row?.values?.[key]));
          const overall = worstLevel(levels);
          return <div key={host} className="rounded-lg bg-field p-3">
            <div className="flex items-center justify-between gap-2 text-sm font-medium">
              <span>{HOST_LABELS[host]} <span className="text-xs font-normal text-muted">({host})</span></span>
              {overall ? <Pill tone={LEVEL[overall][1]}>{LEVEL[overall][0]}</Pill> : <span className="text-xs font-normal text-muted">No current data</span>}
            </div>
            <ul className="mt-2 space-y-1.5">
              {HOST_METRICS.map(([label, key], i) => {
                const value = row?.values?.[key];
                const level = levels[i];
                const pct = Math.min(100, Math.max(0, value * 100));
                return <li key={key} className="grid grid-cols-[4.5rem_minmax(0,1fr)_3.75rem] items-center gap-3 text-sm">
                  <span className="text-muted">{label}</span>
                  <span aria-hidden="true" className="h-1.5 overflow-hidden rounded-full bg-ink/5">
                    {level && <span className={`block h-full origin-left animate-grow-x rounded-full ${LEVEL[level][2]}`} style={{ width: `${pct}%` }} />}
                  </span>
                  <span className="text-right">
                    {level ? `${(value * 100).toFixed(1)}%` : "No data"}
                    {level && <span className="sr-only"> ({LEVEL[level][0]})</span>}
                  </span>
                </li>;
              })}
            </ul>
          </div>;
        })}
      </div>}
    </Card>
  );
}

function EscalationsCard({ escalations, loading }) {
  return (
    <Card title="Escalations" count={loading ? null : escalations.length}>
      {loading ? <SkeletonList label="Loading…" rows={2} className="h-[88px]" /> : escalations.length === 0 ? (
        <Empty icon={Bell} title="No escalations" text="Incidents Argus cannot conclude on its own are raised to a human here." />
      ) : (
        <ul className="stagger space-y-2">
          {escalations.slice(0, 5).map((e) => (
            <li key={e.key} className="rounded-xl bg-field p-3">
              <div className="flex items-start justify-between gap-2">
                <Link to={`/incidents/${e.payload.incident_id}`} className="min-w-0 truncate text-sm font-medium text-accent-hover hover:underline">
                  {e.payload.target}
                </Link>
                <time dateTime={e.at} title={dateTime(e.at)} className="shrink-0 text-xs text-muted">{timeAgo(e.at)}</time>
              </div>
              <div className="mt-1.5 flex items-center gap-2">
                <OutcomeBadge outcome={e.payload.outcome} />
                <span className="truncate font-mono text-xs text-muted">{e.payload.route}</span>
              </div>
              {e.payload.diagnosis && <p className="mt-1.5 line-clamp-2 text-[13px] text-muted">{e.payload.diagnosis}</p>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export default function Dashboard() {
  const { incidents, escalations, hostMetrics, live, updatedAt, refresh } = useLiveOverview();
  const topology = useTopology();     // ACR-0017: the live map, any role; the card hides itself when the route is absent
  const loading = updatedAt == null && live;      // the first read is on its way (a failed one shows the cards as they are)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[28px] font-semibold tracking-[-0.03em]">Dashboard</h1>
          <p className="text-sm text-muted">Live overview of your infrastructure and the Argus agent.</p>
        </div>
        <LivePill live={live} source={dataSource} at={updatedAt} onRefresh={refresh} />
      </div>

      <StatusBanner incidents={incidents} hostMetrics={hostMetrics} topology={topology} hosts={HOST_LABELS} loaded={updatedAt != null} />

      {/* items-start: each column is as tall as its own content, so Recent incidents ends at its last row. */}
      <div className="grid items-start gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <DiagnoseForm />
          <IncidentsCard incidents={incidents} loading={loading} />
        </div>
        <div className="space-y-4">
          <HostMetricsCard rows={hostMetrics} live={live} updatedAt={updatedAt} loading={loading} />
          <EscalationsCard escalations={escalations} loading={loading} />
        </div>
      </div>

      {topology?.nodes?.length > 0 && <SystemMap topology={topology} incidents={incidents} />}
    </div>
  );
}
