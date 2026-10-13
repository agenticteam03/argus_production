import { useEffect, useMemo, useRef, useState } from "react";
import IncidentRow from "../components/IncidentRow.jsx";
import { Card, Empty, ErrorCard, fieldClass, Inbox, LivePill, OUTCOME_META, Search, Select, Skeleton, STATUS_META } from "../components/ui.jsx";
import { useIncidentList } from "../hooks/useIncidentList.js";
import { dataSource } from "../services/index.js";

export default function Incidents() {
  const { rows, error, live, updatedAt, retry } = useIncidentList();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [outcome, setOutcome] = useState("");
  const [target, setTarget] = useState("");
  const headingRef = useRef(null);
  useEffect(() => { headingRef.current?.focus(); }, []);

  const targets = useMemo(() => [...new Set((rows ?? []).map((r) => r.target))].sort(), [rows]);
  const filtered = useMemo(() => {
    const t = query.trim().toLowerCase();
    return (rows ?? []).filter(
      (r) =>
        (!status || r.status === status) &&
        (!outcome || (outcome === "none" ? r.outcome == null : r.outcome === outcome)) &&
        (!target || r.target === target) &&
        (!t || [r.id, r.target, r.class, r.strategy, r.root_cause_target].filter(Boolean).join(" ").toLowerCase().includes(t))
    );
  }, [rows, query, status, outcome, target]);

  const filtersActive = query || status || outcome || target;
  const clear = () => { setQuery(""); setStatus(""); setOutcome(""); setTarget(""); };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 ref={headingRef} tabIndex={-1} className="text-[28px] font-semibold tracking-[-0.03em] outline-none">Incidents</h1>
          <p className="text-sm text-muted">What Argus investigated, and how each run ended.</p>
        </div>
        <LivePill live={live} source={dataSource} at={updatedAt} />
      </div>

      {error && !rows ? (
        <ErrorCard title="Couldn't load incidents" text="Something went wrong while loading the incident list." onRetry={retry} />
      ) : rows === null ? (
        <div aria-busy="true" className="space-y-2 rounded-2xl border border-line bg-card/80 p-4">
          <span className="sr-only">Loading incidents…</span>
          {[0, 1, 2, 3, 4].map((n) => <Skeleton key={n} className="h-[72px]" />)}
        </div>
      ) : rows.length === 0 ? (
        <Empty icon={Inbox} title="No incidents yet" text="Incidents opened by alerts, scheduled checks or manual runs will show up here." />
      ) : (
        <>
          <div className="flex flex-wrap gap-2">
            <div className="relative min-w-60 flex-1">
              <Search className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" width="16" height="16" />
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search by ID, target, class or strategy…" aria-label="Search incidents" className={`${fieldClass} w-full pl-10`} />
            </div>
            <Select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Filter by status">
              <option value="">All statuses</option>
              {Object.entries(STATUS_META).map(([k, [label]]) => <option key={k} value={k}>{label}</option>)}
            </Select>
            <Select value={outcome} onChange={(e) => setOutcome(e.target.value)} aria-label="Filter by outcome">
              <option value="">All outcomes</option>
              {Object.entries(OUTCOME_META).map(([k, [label]]) => <option key={k} value={k}>{label}</option>)}
              <option value="none">No outcome yet</option>
            </Select>
            <Select value={target} onChange={(e) => setTarget(e.target.value)} aria-label="Filter by target">
              <option value="">All targets</option>
              {targets.map((t) => <option key={t} value={t}>{t}</option>)}
            </Select>
            {filtersActive && <button onClick={clear} className="h-11 cursor-pointer rounded-[10px] border border-field-line px-3.5 text-sm text-muted transition hover:text-white">Clear</button>}
          </div>

          {filtered.length === 0 ? (
            <div className="space-y-3 text-center">
              <Empty icon={Search} title="No incidents match your filters" text="Try a different search or clear the filters." />
              <button onClick={clear} className="cursor-pointer text-[13px] text-accent-hover hover:underline">Clear filters</button>
            </div>
          ) : (
            <>
              <p className="text-xs text-muted">Showing {filtered.length} of {rows.length} · only the latest 30 incidents are loaded</p>
              <Card title="Incidents" count={filtered.length}>
                <ul className="space-y-2">{filtered.map((r) => <IncidentRow key={r.id} incident={r} />)}</ul>
              </Card>
            </>
          )}
        </>
      )}
    </div>
  );
}
