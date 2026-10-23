import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigationType } from "react-router-dom";
import IncidentRow from "../components/IncidentRow.jsx";
import { Card, Empty, ErrorCard, fieldClass, Inbox, LivePill, OUTCOME_META, Search, Select, Skeleton, STATUS_META } from "../components/ui.jsx";
import { useIncidentList } from "../hooks/useIncidentList.js";
import { dataSource } from "../services/index.js";
import { hostsOf, matchesHost, targetsOfHost, withoutHost } from "../utils/incidentFilter.js";
import { incidentsSummary, PAGE_SIZE } from "../utils/paging.js";

// The list (filters, "Show more" count, scroll) is remembered while an incident is open, so coming back lands on the
// same row. Kept in module memory only: one small object, gone on reload, never sent anywhere.
let remembered = null;

export default function Incidents() {
  const location = useLocation();
  const navType = useNavigationType();
  // Restore only when coming back (browser Back, or the incident page's "← Incidents"); a fresh visit starts clean.
  const restore = useRef(remembered && (navType === "POP" || location.state?.restore) ? remembered : null).current;
  const scrollY = useRef(restore?.scrollY ?? 0);
  const pendingScroll = useRef(restore ? restore.scrollY : null);
  const { rows, error, live, updatedAt, retry, truncated } = useIncidentList();
  const [query, setQuery] = useState(restore?.query ?? "");
  const [status, setStatus] = useState(restore?.status ?? "");
  const [outcome, setOutcome] = useState(restore?.outcome ?? "");
  const [host, setHost] = useState(restore?.host ?? "");
  const [target, setTarget] = useState(restore?.target ?? "");
  const [visible, setVisible] = useState(restore?.visible ?? PAGE_SIZE);
  const headingRef = useRef(null);
  // preventScroll: when returning, focusing the heading must not pull the page back to the top.
  useEffect(() => { headingRef.current?.focus({ preventScroll: Boolean(restore) }); }, [restore]);
  // A new filter is a new result set: go back to the first page so "Show more" always starts from the top.
  // (Compared with the previous key, so restoring the filters on arrival does not count as a change.)
  const filterKey = [query, status, outcome, host, target].join("\u0000");
  const lastKey = useRef(filterKey);
  useEffect(() => {
    if (lastKey.current !== filterKey) { lastKey.current = filterKey; setVisible(PAGE_SIZE); }
  }, [filterKey]);
  useEffect(() => { remembered = { query, status, outcome, host, target, visible, scrollY: scrollY.current }; }, [query, status, outcome, host, target, visible]);
  // Once the rows (and the restored "Show more" count) are on screen, go back to where the person was.
  useLayoutEffect(() => {
    if (rows && pendingScroll.current != null) { window.scrollTo(0, pendingScroll.current); pendingScroll.current = null; }
  }, [rows]);
  const rememberScroll = () => { scrollY.current = window.scrollY; if (remembered) remembered.scrollY = window.scrollY; };

  // Host first, then a target inside that host: both lists come from the incidents already loaded.
  const hosts = useMemo(() => hostsOf(rows), [rows]);
  const targets = useMemo(() => targetsOfHost(rows, host), [rows, host]);
  const filtered = useMemo(() => {
    const t = query.trim().toLowerCase();
    return (rows ?? []).filter(
      (r) =>
        (!status || r.status === status) &&
        (!outcome || (outcome === "none" ? r.outcome == null : r.outcome === outcome)) &&
        matchesHost(r, host, target) &&
        (!t || [r.id, r.target, r.class, r.strategy, r.root_cause_target].filter(Boolean).join(" ").toLowerCase().includes(t))
    );
  }, [rows, query, status, outcome, host, target]);

  const filtersActive = query || status || outcome || host || target;
  const clear = () => { setQuery(""); setStatus(""); setOutcome(""); setHost(""); setTarget(""); };

  const shown = filtered.slice(0, visible);
  const remaining = filtered.length - shown.length;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 ref={headingRef} tabIndex={-1} className="text-[28px] font-semibold tracking-[-0.03em] outline-none">Incidents</h1>
          <p className="text-sm text-muted">What Argus investigated, and how each run ended.</p>
        </div>
        <LivePill live={live} source={dataSource} at={updatedAt} onRefresh={retry} />
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
            <Select value={host} onChange={(e) => { setHost(e.target.value); setTarget(""); }} aria-label="Filter by host">
              <option value="">All hosts</option>
              {hosts.map((h) => <option key={h} value={h}>{h}</option>)}
            </Select>
            <Select value={target} onChange={(e) => setTarget(e.target.value)} aria-label="Filter by target" disabled={!host} title={host ? undefined : "Choose a host first"}>
              <option value="">{host ? "All targets in this host" : "Choose a host first"}</option>
              {targets.map((t) => <option key={t} value={t}>{withoutHost(t, host)}</option>)}
            </Select>
            {filtersActive && <button onClick={clear} className="h-11 cursor-pointer rounded-[10px] border border-field-line px-3.5 text-sm text-muted transition hover:text-ink">Clear</button>}
          </div>

          {filtered.length === 0 ? (
            <div className="space-y-3 text-center">
              <Empty icon={Search} title="No incidents match your filters" text="Try a different search or clear the filters." />
              <button onClick={clear} className="cursor-pointer text-[13px] text-accent-hover hover:underline">Clear filters</button>
            </div>
          ) : (
            <>
              <p className="text-xs text-muted">
                {incidentsSummary({ shown: shown.length, matched: filtered.length, total: rows.length, hasFilters: Boolean(filtersActive), truncated })}
              </p>
              <Card title="Incidents" count={filtered.length}>
                <ul onClickCapture={rememberScroll} className="space-y-2">{shown.map((r) => <IncidentRow key={r.id} incident={r} />)}</ul>
                {remaining > 0 && (
                  <div className="mt-4 flex justify-center">
                    <button
                      onClick={() => setVisible((v) => v + PAGE_SIZE)}
                      className="cursor-pointer rounded-lg border border-line px-4 py-2 text-sm transition hover:bg-ink/5"
                    >
                      Show {Math.min(PAGE_SIZE, remaining)} more
                    </button>
                  </div>
                )}
              </Card>
            </>
          )}
        </>
      )}
    </div>
  );
}
