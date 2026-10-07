import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AgentChat from "../components/AgentChat.jsx";
import { Arrow, Badge, Card, Empty, Inbox, Shield } from "../components/ui.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { useLiveOverview } from "../hooks/useLiveOverview.js";
import { argus } from "../services/index.js";

const TRIGGERS = { alert: "Alertmanager webhook", scheduled: "Scheduled check", manual: "Manual" };

const timeAgo = (iso) => {
  const m = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
  return m < 1 ? "just now" : m < 60 ? `${m}m ago` : m < 1440 ? `${Math.round(m / 60)}h ago` : `${Math.round(m / 1440)}d ago`;
};

function IncidentsCard({ incidents, className }) {
  return (
    <Card title="Recent incidents" count={incidents.length} className={className}>
      {incidents.length === 0 ? (
        <Empty icon={Inbox} title="No recent activity" text="Incidents from alerts, scheduled checks or manual runs will show up here." />
      ) : (
        <ul className="space-y-2">
          {incidents.slice(0, 5).map((i) => (
            <li key={i.id} className="rounded-xl bg-field p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-mono text-xs text-muted">{i.id}</span>
                <Badge status={i.status} />
              </div>
              <p className="mt-1.5 text-sm font-medium">{i.target} <span className="font-normal text-muted">· {i.title}</span></p>
              <p className="mt-1 text-xs text-muted">{timeAgo(i.createdAt)} · {TRIGGERS[i.trigger] ?? i.trigger} · {i.severity}</p>
            </li>
          ))}
        </ul>
      )}
      <Link to="/incidents" className="mt-3 inline-flex items-center gap-1.5 text-[13px] text-accent-hover hover:underline">
        View full incident history <Arrow width="14" height="14" />
      </Link>
    </Card>
  );
}

const Row = ({ label, children }) => (
  <div className="flex items-center justify-between gap-3 text-sm"><span className="text-muted">{label}</span>{children}</div>
);
const Status = ({ ok, yes, no }) => (
  <span className="flex items-center gap-2">
    <span className={`size-2 rounded-full ${ok == null ? "bg-zinc-600" : ok ? "bg-emerald-400" : "bg-red-400"}`} />
    {ok == null ? "No data" : ok ? yes : no}
  </span>
);

function HealthCard({ health }) {
  const { used, limit } = health?.tokens ?? {};
  const pct = used != null && limit ? Math.min(100, (used / limit) * 100) : 0;
  return (
    <Card title="Agent status">
      <div className="space-y-3">
        <Row label="WireGuard tunnel (A ↔ T)"><Status ok={health?.wireguard} yes="Connected" no="Down" /></Row>
        <Row label="Prometheus metrics"><Status ok={health?.prometheus} yes="Online" no="Offline" /></Row>
        <div>
          <Row label="LLM tokens today"><span>{used ?? "—"} / {limit ?? "—"}</span></Row>
          <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-white/10"><div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} /></div>
        </div>
        <Row label="Resolved today"><span>{health?.resolvedToday ?? "—"}</span></Row>
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
          <button disabled={expired} onClick={() => onDecide(approval.id, "approve")} className="h-9 flex-1 cursor-pointer rounded-lg bg-accent text-sm font-medium text-white transition enabled:hover:bg-accent-hover disabled:cursor-not-allowed disabled:bg-[#10141b] disabled:text-[#4b5363]">Approve</button>
          <button disabled={expired} onClick={() => onDecide(approval.id, "deny")} className="h-9 flex-1 cursor-pointer rounded-lg border border-line text-sm transition enabled:hover:bg-white/5 disabled:cursor-not-allowed disabled:text-[#4b5363]">Reject</button>
        </div>
      ) : (
        <p className="mt-2 text-xs text-muted">Only operators and admins can decide.</p>
      )}
    </li>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const { incidents, approvals, health, live, refresh } = useLiveOverview();
  // The server derives the actor from the token; an expired/conflicting decision just triggers a refresh.
  const decide = (id, decision) => argus.decideApproval(id, decision).catch(() => {}).finally(refresh);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[28px] font-semibold tracking-[-0.03em]">Dashboard</h1>
          <p className="text-sm text-muted">Live overview of your infrastructure and the Argus agent.</p>
        </div>
        <span className="inline-flex items-center gap-2 rounded-full border border-line bg-card px-3 py-1.5 text-xs text-muted">
          <span className={`size-2 rounded-full ${live ? "animate-pulse bg-emerald-400" : "bg-amber-400"}`} />
          {live ? "Live" : "Reconnecting…"}
        </span>
      </div>

      <AgentChat />

      <div className="grid gap-4 lg:grid-cols-3">
        <IncidentsCard incidents={incidents} className="lg:col-span-2" />
        <div className="space-y-4">
          <HealthCard health={health} />
          <Card title="Pending approvals" count={approvals.length}>
            {approvals.length === 0 ? (
              <Empty icon={Shield} title="No pending approvals" text="Remediations that need a human decision will appear here." />
            ) : (
              <ul className="space-y-2">
                {approvals.map((a) => <ApprovalItem key={a.id} approval={a} canDecide={user.role !== "viewer"} onDecide={decide} />)}
              </ul>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
