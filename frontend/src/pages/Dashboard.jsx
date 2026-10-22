import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AgentChat from "../components/AgentChat.jsx";
import DiagnoseForm from "../components/DiagnoseForm.jsx";
import IncidentRow from "../components/IncidentRow.jsx";
import { SystemMapCard } from "../components/SystemMap.jsx";
import { Arrow, Bell, Card, Empty, Inbox, LivePill, OutcomeBadge, Pill, Shield } from "../components/ui.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { useLiveOverview } from "../hooks/useLiveOverview.js";
import { useTopology } from "../hooks/useTopology.js";
import { argus, dataSource } from "../services/index.js";
import { dateTime, timeAgo } from "../utils/format.js";
import { loadLevel, worstLevel } from "../utils/load.js";

function IncidentsCard({ incidents, className }) {
  return (
    <Card title="Recent incidents" count={incidents.length} className={className}>
      {incidents.length === 0 ? (
        <Empty icon={Inbox} title="No recent activity" text="Incidents from alerts, scheduled checks or manual runs will show up here." />
      ) : (
        <ul className="space-y-2">
          {incidents.slice(0, 5).map((i) => <IncidentRow key={i.id} incident={i} compact />)}
        </ul>
      )}
      <Link to="/incidents" className="mt-3 inline-flex items-center gap-1.5 text-[13px] text-accent-hover hover:underline">
        View full incident history <Arrow width="14" height="14" />
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

function HostMetricsCard({ rows, live, updatedAt }) {
  return (
    <Card title="Host metrics" right={<LivePill live={live} source={dataSource} at={updatedAt} />}>
      <div className="space-y-4">
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
                  <span aria-hidden="true" className="h-1.5 overflow-hidden rounded-full bg-white/5">
                    {level && <span className={`block h-full rounded-full ${LEVEL[level][2]}`} style={{ width: `${pct}%` }} />}
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
      </div>
    </Card>
  );
}

function ApprovalItem({ approval, canDecide, onDecide }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const left = Math.max(0, new Date(approval.expiresAt) - now);
  const expired = left === 0;
  const clock = `${String(Math.floor(left / 60000)).padStart(2, "0")}:${String(Math.floor(left / 1000) % 60).padStart(2, "0")}`;
  return (
    <li className="rounded-xl bg-field p-3">
      <p className="text-sm font-medium">{approval.action}</p>
      <p className="mt-0.5 text-xs text-muted">{approval.target} · {expired ? "Expired" : `Expires in ${clock}`}</p>
      {canDecide ? (
        <div className="mt-3 flex gap-2">
          <button disabled={expired} onClick={() => onDecide(approval.id, "approve")} className="h-9 flex-1 cursor-pointer rounded-lg bg-accent-solid text-sm font-medium text-white transition enabled:hover:bg-accent-solid-hover disabled:cursor-not-allowed disabled:bg-[#10141b] disabled:text-[#4b5363]">Approve</button>
          <button disabled={expired} onClick={() => onDecide(approval.id, "deny")} className="h-9 flex-1 cursor-pointer rounded-lg border border-line text-sm transition enabled:hover:bg-white/5 disabled:cursor-not-allowed disabled:text-[#4b5363]">Reject</button>
        </div>
      ) : (
        <p className="mt-2 text-xs text-muted">Only a token with the approve action can decide.</p>
      )}
    </li>
  );
}

function EscalationsCard({ escalations }) {
  return (
    <Card title="Escalations" count={escalations.length}>
      {escalations.length === 0 ? (
        <Empty icon={Bell} title="No escalations" text="Incidents Argus cannot conclude on its own are raised to a human here." />
      ) : (
        <ul className="space-y-2">
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
  const { user } = useAuth();
  const { incidents, approvals, escalations, hostMetrics, live, updatedAt, refresh } = useLiveOverview();
  const topology = useTopology();     // ACR-0017: the live map, any role; the card hides itself when the route is absent
  // A read token never lists `approve`, so the buttons stay hidden (ACR-0001); the UI never decides who may act.
  const canDecide = user.actions?.includes("approve") ?? false;
  // The server derives the actor from the token; an expired/conflicting decision just triggers a refresh.
  const decide = (id, decision) => argus.decideApproval(id, decision).catch(() => {}).finally(refresh);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[28px] font-semibold tracking-[-0.03em]">Dashboard</h1>
          <p className="text-sm text-muted">Live overview of your infrastructure and the Argus agent.</p>
        </div>
        <LivePill live={live} source={dataSource} at={updatedAt} />
      </div>

      <AgentChat />

      <DiagnoseForm />

      {/* items-start: each column is as tall as its own content, so Recent incidents ends at its last row. */}
      <div className="grid items-start gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <IncidentsCard incidents={incidents} />
          <Card title="Pending approvals" count={approvals.length}>
            {approvals.length === 0 ? (
              <Empty icon={Shield} title="No pending approvals" text="Remediations that need a human decision will appear here." />
            ) : (
              <ul className="space-y-2">
                {approvals.map((a) => <ApprovalItem key={a.id} approval={a} canDecide={canDecide} onDecide={decide} />)}
              </ul>
            )}
          </Card>
        </div>
        <div className="space-y-4">
          <HostMetricsCard rows={hostMetrics} live={live} updatedAt={updatedAt} />
          <EscalationsCard escalations={escalations} />
        </div>
      </div>

      <SystemMapCard topology={topology} />
    </div>
  );
}
