import { Link } from "react-router-dom";
import { Arrow, Badge, Card, Empty, Inbox, Shield } from "../components/ui.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { useLiveOverview } from "../hooks/useLiveOverview.js";
import { ROLE_INFO, ROLES } from "../routes.js";

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

// ACR-0001: the UI only reads in this release. Say so instead of offering controls that would be refused.
function ReadOnlyCard({ user }) {
  return (
    <Card title="Read-only view" right={<span className="rounded-full border border-accent/30 bg-accent/10 px-2.5 py-1 text-xs text-accent-hover">Role: {ROLES[user.role]}</span>}>
      <div className="space-y-3 text-sm text-muted">
        <p className="flex gap-2"><Shield width="18" height="18" className="mt-0.5 shrink-0 text-accent-hover" />{ROLE_INFO[user.role]}</p>
        <p>Starting an investigation and answering approvals are not available in the web UI in this release. Use the
          CLI (<code className="font-mono text-xs">argus run</code>) or Swagger.</p>
      </div>
    </Card>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const { incidents, live } = useLiveOverview();

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[28px] font-semibold tracking-[-0.03em]">Dashboard</h1>
          <p className="text-sm text-muted">Live overview of the incidents Argus is working on.</p>
        </div>
        <span className="inline-flex items-center gap-2 rounded-full border border-line bg-card px-3 py-1.5 text-xs text-muted">
          <span className={`size-2 rounded-full ${live ? "animate-pulse bg-emerald-400" : "bg-amber-400"}`} />
          {live ? "Live" : "Reconnecting…"}
        </span>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <IncidentsCard incidents={incidents} className="lg:col-span-2" />
        <ReadOnlyCard user={user} />
      </div>
    </div>
  );
}
