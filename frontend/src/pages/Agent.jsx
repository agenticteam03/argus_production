import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Card, LivePill, StatusBadge } from "../components/ui.jsx";
import { argus, dataSource } from "../services/index.js";
import { summarizeRun } from "../utils/agentObservability.js";
import { dateTime } from "../utils/format.js";

const NODE_LABEL = { detect: "Detection", recall: "Runbook recall", investigate: "Investigation", act: "Read-only tools", evidence_pack: "Evidence pack", record: "Record outcome" };
// Same cadence as the other pages (overview and incident list).
const REFRESH_MS = 30000;
const EVENT_LABEL = { enter: "Started", step: "Tool read", exit: "Completed" };

export default function Agent() {
  const [incidents, setIncidents] = useState([]);
  const [selected, setSelected] = useState(null);
  const [events, setEvents] = useState([]);
  const [error, setError] = useState(false);
  const [updated, setUpdated] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (document.hidden) return;
    try {
      const rows = await argus.listIncidents({ limit: 30 });
      setIncidents(rows);
      setSelected((current) => current && rows.some((row) => row.id === current)
        ? current : rows.find((row) => row.status === "running")?.id ?? rows[0]?.id ?? null);
      setUpdated(Date.now());
      setError(false);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); const timer = setInterval(refresh, REFRESH_MS); return () => clearInterval(timer); }, [refresh]);
  const selectedStatus = incidents.find((incident) => incident.id === selected)?.status;
  const live = selectedStatus === "queued" || selectedStatus === "running";
  // Events with the `after` cursor; polled only while the run is live (one final read when it closes).
  useEffect(() => {
    if (!selected) { setEvents([]); return undefined; }
    setEvents([]);
    let alive = true;
    let after = 0;
    const load = async () => {
      if (document.hidden) return;
      try {
        const batch = await argus.getIncidentEvents(selected, { after });
        if (!alive || !batch.length) return;
        after = Math.max(after, ...batch.map((event) => event.seq));
        setEvents((prev) => [...prev, ...batch.filter((event) => event.seq > (prev.at(-1)?.seq ?? 0))]);
      } catch {
        // keep the events already shown; the next poll retries
      }
    };
    load();
    const timer = live ? setInterval(load, 3000) : null;
    return () => { alive = false; if (timer) clearInterval(timer); };
  }, [selected, live]);

  const current = incidents.find((incident) => incident.id === selected);
  const run = summarizeRun(events);
  const active = incidents.filter((incident) => incident.status === "running").length;
  const escalated = incidents.filter((incident) => incident.status === "escalated").length;

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[28px] font-semibold tracking-[-0.03em]">Investigation activity</h1>
          <p className="max-w-2xl text-sm text-muted">Follow Argus runs and correlate them with private Langfuse traces. This view reads Argus events; it does not expose Langfuse credentials.</p>
        </div>
        <LivePill live={!error} source={dataSource} at={updated} onRefresh={refresh} />
      </header>

      <div className="grid gap-3 sm:grid-cols-3">
        <Metric label="Active runs" value={active} detail="Investigations in progress" />
        <Metric label="Recent runs" value={incidents.length} detail="Latest 30 incidents" />
        <Metric label="Escalated" value={escalated} detail="Human follow-up needed" />
      </div>

      {error && <div role="alert" className="rounded-xl border border-amber-400/20 bg-amber-400/5 p-4 text-sm text-amber-200">Could not refresh agent activity. Showing the last available data.</div>}

      <div className="grid gap-5 lg:grid-cols-[minmax(280px,0.85fr)_minmax(0,1.45fr)]">
        <Card title="Runs" count={incidents.length}>
          {loading ? <p className="text-sm text-muted">Loading runs…</p> : incidents.length === 0 ? <p className="py-8 text-center text-sm text-muted">No investigations recorded yet.</p> : (
            <ul className="max-h-[680px] space-y-2 overflow-y-auto pr-1">
              {incidents.map((incident) => (
                <li key={incident.id}>
                  <button type="button" onClick={() => setSelected(incident.id)} aria-current={selected === incident.id ? "true" : undefined}
                    className={`w-full cursor-pointer rounded-xl border p-3 text-left transition ${selected === incident.id ? "border-accent/50 bg-accent/10" : "border-transparent bg-field hover:border-line"}`}>
                    <div className="flex items-start justify-between gap-2"><span className="min-w-0 truncate text-sm font-medium">{incident.target}</span><StatusBadge status={incident.status} /></div>
                    <p className="mt-1 truncate font-mono text-[11px] text-muted">{incident.id}</p>
                    <p className="mt-2 text-xs text-muted">{incident.class ?? "Unclassified"} · {dateTime(incident.opened_at)}</p>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <div className="space-y-5">
          <Card title="Selected investigation" right={current && <Link to={`/incidents/${encodeURIComponent(current.id)}`} className="text-xs text-accent-hover hover:underline">Open incident →</Link>}>
            {!current ? <p className="text-sm text-muted">Select a run to see its activity.</p> : (
              <>
                <div className="grid gap-3 sm:grid-cols-3">
                  <SmallMetric label="Current node" value={NODE_LABEL[run.node] ?? "Waiting"} />
                  <SmallMetric label="Tool reads" value={run.tools} />
                  <SmallMetric label="Decisions" value={run.decisions} />
                </div>
                <div className="mt-4 rounded-xl border border-line bg-field p-3">
                  <p className="text-xs font-medium text-ink">Langfuse correlation</p>
                  {run.traceId ? <><p className="mt-1 break-all font-mono text-xs text-accent-hover">{run.traceId}</p><p className="mt-1 text-xs text-muted">Trace ID emitted by the worker. Ingestion status is checked in the private Langfuse service.</p></> : <p className="mt-1 text-xs text-muted">No trace ID in this run. Langfuse may be disabled, or this run predates instrumentation.</p>}
                </div>
              </>
            )}
          </Card>
          <Card title="Execution timeline" count={events.length}>
            {events.length === 0 ? <p className="py-8 text-center text-sm text-muted">No execution events for this run yet.</p> : (
              <ol className="max-h-[540px] space-y-0 overflow-y-auto pr-1">
                {events.map((event) => (
                  <li key={event.seq} className="relative flex gap-3 border-l border-line py-3 pl-5 first:pt-1 last:pb-1">
                    <span className="absolute -left-[5px] top-5 size-[9px] rounded-full border-2 border-accent bg-card" />
                    <div className="min-w-0 flex-1"><div className="flex flex-wrap items-baseline justify-between gap-2"><p className="text-sm font-medium">{NODE_LABEL[event.node] ?? event.node}</p><time className="text-[11px] text-muted">{dateTime(event.at)}</time></div><p className="mt-0.5 text-xs text-muted">{EVENT_LABEL[event.phase] ?? event.phase}{event.phase === "step" && event.data?.capability ? ` · ${event.data.capability}` : ""}{event.phase === "step" && event.data?.status ? ` · ${event.data.status}` : ""}</p></div>
                  </li>
                ))}
              </ol>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value, detail }) {
  return <div className="rounded-2xl border border-line bg-card/80 p-4"><p className="text-xs text-muted">{label}</p><p className="mt-2 text-[30px] font-semibold tracking-[-0.04em]">{value}</p><p className="mt-1 text-xs text-muted">{detail}</p></div>;
}

function SmallMetric({ label, value }) {
  return <div className="rounded-xl bg-field p-3"><p className="text-xs text-muted">{label}</p><p className="mt-1 text-sm font-medium">{value}</p></div>;
}
