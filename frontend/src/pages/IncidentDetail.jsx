import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import AnswerBlock from "../components/AnswerBlock.jsx";
import ActionSuggestions from "../components/ActionSuggestions.jsx";
import ActionTrail from "../components/ActionTrail.jsx";
import IncidentApproval from "../components/IncidentApproval.jsx";
import CopySummary from "../components/CopySummary.jsx";
import DiagnoseForm from "../components/DiagnoseForm.jsx";
import IncidentChat from "../components/IncidentChat.jsx";
import { AuditSection, EvidenceSection, RestrictedNotice } from "../components/EvidenceAudit.jsx";
import RawOutputDialog from "../components/RawOutputDialog.jsx";
import ResolveIncident, { Resolution } from "../components/ResolveIncident.jsx";
import RunTimeline from "../components/RunTimeline.jsx";
import MiniMap, { miniPair } from "../components/map/MiniMap.jsx";
import SystemMap from "../components/map/SystemMap.jsx";
import { Chevron, ErrorCard, Disclosure, Fact, OUTCOME_META, OutcomeBadge, Skeleton, STATUS_META, StatusBadge, TabList, TabPanel } from "../components/ui.jsx";
import WhyCard from "../components/WhyCard.jsx";
import { useConsoleDock } from "../components/console/dock/ConsoleDockContext.jsx";
import { TerminalIcon } from "../components/console/dock/icons.jsx";
import { useAuth } from "../context/AuthContext.jsx";
import { useIncident } from "../hooks/useIncident.js";
import { useIncidentMetrics } from "../hooks/useIncidentMetrics.js";
import { useTopology } from "../hooks/useTopology.js";
import { dateTime, duration, isActive } from "../utils/format.js";
import { citedEvidence, decidedBy, hostOf, modelCalls } from "../utils/incidentView.js";

// The charts (ECharts, ~190 KB gzipped) load only when an incident has metrics to draw, not with the first page.
const MetricsTab = lazy(() => import("../components/charts/ChartGrid.jsx").then((m) => ({ default: m.MetricsTab })));
const MiniCharts = lazy(() => import("../components/charts/ChartGrid.jsx").then((m) => ({ default: m.MiniCharts })));

const Back = () => (
  <Link to="/incidents" state={{ restore: true }} className="inline-flex text-[13px] text-accent-hover hover:underline">← Incidents</Link>
);
const menuItem = "w-full cursor-pointer rounded-lg px-3 py-2 text-left text-sm text-body hover:bg-ink/5 hover:text-ink";
const ghost = "cursor-pointer rounded-xl border border-line bg-field px-4 py-2 text-sm text-body transition hover:border-field-line hover:text-ink motion-reduce:transition-none";

export default function IncidentDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const dock = useConsoleDock();
  const { view, incident: inc, events, reconnecting, retry, refresh } = useIncident(id);
  const [params, setParams] = useSearchParams();
  const [range, setRange] = useState("30m");
  const [rawOpen, setRawOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);   // open details: the minor actions fold into "More"
  // ACR-0017: the incident overlay (real networks and state from the incident's evidence) is operator/approver only;
  // asking for it as a viewer is a 403, so a viewer gets the plain system map instead.
  const canOverlay = user?.role === "operator" || user?.role === "approver";
  const topology = useTopology(canOverlay ? id : undefined);
  const metrics = useIncidentMetrics(id, range, inc?.status);
  const headingRef = useRef(null);
  const [announce, setAnnounce] = useState("");
  const prevStatus = useRef(null);
  const [openEvidence, setOpenEvidence] = useState(() => new Set());

  useEffect(() => { if (view !== "loading") headingRef.current?.focus(); }, [view, id]);

  // Status changes are announced politely; individual events are not.
  useEffect(() => {
    const status = inc?.status;
    if (prevStatus.current && status && prevStatus.current !== status) {
      const outcome = inc.outcome ? `: ${OUTCOME_META[inc.outcome]?.[0] ?? inc.outcome}` : "";
      setAnnounce(`Incident ${(STATUS_META[status]?.[0] ?? status).toLowerCase()}${outcome}`);
    }
    prevStatus.current = status ?? null;
  }, [inc?.status, inc?.outcome]);

  if (view === "loading") {
    return (
      <div aria-busy="true" className="space-y-4">
        <span className="sr-only">Loading incident…</span>
        <Skeleton className="h-6 w-28" /><Skeleton className="h-40" /><Skeleton className="h-48" />
      </div>
    );
  }
  if (view === "notfound") {
    return (
      <div className="space-y-4">
        <Back />
        <ErrorCard as="h1" headingRef={headingRef} title="Incident not found" text="This incident doesn't exist or is no longer available." />
      </div>
    );
  }
  if (view === "error") {
    return (
      <div className="space-y-4">
        <Back />
        <ErrorCard as="h1" headingRef={headingRef} title="Couldn't load this incident" text="Something went wrong. Please try again." onRetry={retry} />
      </div>
    );
  }

  const active = isActive(inc.status);
  const hasEvidence = "evidence" in inc;
  const hasAudit = "audit" in inc;
  const evidenceIds = new Set((inc.evidence ?? []).map((e) => e.evidence_id));
  const cited = citedEvidence(inc, events);

  // Map and Metrics exist only when their route answered with data: nothing is invented.
  const showMap = Boolean(topology);
  const showMetrics = Boolean(metrics);
  const tabs = [
    { id: "overview", label: "Incident & Diagnosis" },
    ...(showMap ? [{ id: "map", label: "Map" }] : []),
    ...(showMetrics ? [{ id: "metrics", label: "Metrics" }] : []),
    { id: "timeline", label: "Runtime Timeline" },
    { id: "evidence", label: "Evidence", count: hasEvidence ? inc.evidence.length : undefined },
    { id: "audit", label: "Audit", count: hasAudit ? inc.audit.length : undefined },
  ];
  const requested = params.get("tab");
  const tab = tabs.some((t) => t.id === requested) ? requested : "overview";
  const setTab = (next) => {
    const p = new URLSearchParams(params);
    if (next === "overview") p.delete("tab"); else p.set("tab", next);
    setParams(p);
    if (next === "audit") refresh();          // a closed incident is not polled: new console rows appear on opening
  };

  const toggleEvidence = (key) => setOpenEvidence((prev) => { const next = new Set(prev); next.has(key) ? next.delete(key) : next.add(key); return next; });
  const jumpToEvidence = (key) => {
    setOpenEvidence((prev) => new Set(prev).add(key));
    setTab("evidence");
    setTimeout(() => {
      const el = document.getElementById(`evidence-${key}`);
      el?.scrollIntoView?.({ block: "center" });
      el?.focus();
    }, 60);
  };

  const by = decidedBy(events);
  const decided = by === "rules" ? `decided by rules${modelCalls(inc) === 0 ? " (no AI)" : ""}` : by === "AI" ? "decided with AI" : null;
  const subtitle = [inc.reason, inc.incident_class, decided, inc.closed_at ? `took ${duration(inc.opened_at, inc.closed_at)}` : null].filter(Boolean).join(" · ");

  const showMini = showMap && miniPair(topology, inc);

  return (
    <div className="space-y-5">
      <p role="status" aria-live="polite" className="sr-only">{announce}</p>
      <Back />

      <section className="rounded-2xl border border-line bg-card/80 p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="min-w-0 break-all font-mono text-xs text-accent-hover">{inc.id}</span>
          <span className="flex flex-wrap gap-1.5"><StatusBadge status={inc.status} /><OutcomeBadge outcome={inc.outcome} /></span>
        </div>
        <h1 ref={headingRef} tabIndex={-1} className="mt-2 text-[26px] font-semibold leading-tight tracking-[-0.03em] outline-none">{inc.target}</h1>
        {subtitle && <p className="mt-1.5 text-sm leading-relaxed text-soft">{subtitle}</p>}

        <div className="mt-4 border-t border-line pt-4"><AnswerBlock incident={inc} active={active} /></div>
        {inc.resolution && <div className="mt-4"><Resolution resolution={inc.resolution} /></div>}

        <div className="mt-4 flex flex-wrap items-start justify-between gap-3 border-t border-line pt-4">
          <Disclosure summary="Details: trigger, principal, times" className="min-w-0 flex-1 basis-64"
            onToggle={(e) => setDetailsOpen(e.currentTarget.open)}>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-4 md:grid-cols-3">
              <Fact label="Class">{inc.incident_class}</Fact>
              <Fact label="Strategy">{inc.strategy}</Fact>
              <Fact label="Triggered by">{inc.trigger_kind}</Fact>
              <Fact label="Request">{inc.request_kind}</Fact>
              <Fact label="Principal">{inc.principal}</Fact>
              <Fact label="Trigger ID">{inc.trigger_id}</Fact>
              <Fact label="Opened">{dateTime(inc.opened_at)}</Fact>
              <Fact label="Closed">{inc.closed_at ? `${dateTime(inc.closed_at)} (took ${duration(inc.opened_at, inc.closed_at)})` : "Still open"}</Fact>
              {inc.trace_url && (
                <Fact label="Agent trace">
                  <a href={inc.trace_url} target="_blank" rel="noopener noreferrer" className="text-accent-hover hover:underline">Open in Langfuse</a>
                </Fact>
              )}
            </dl>
          </Disclosure>
          {/* ACR-0012: "Investigate again" is shown only when /me allows it */}
          <div className="flex flex-wrap items-center gap-2">
            {detailsOpen ? (
              // T-0016: with the details open the row is narrow: the two minor actions wait in a small menu
              <details className="group relative" onBlur={(e) => !e.currentTarget.contains(e.relatedTarget) && e.currentTarget.removeAttribute("open")}>
                <summary className={`${ghost} flex list-none items-center gap-1.5 [&::-webkit-details-marker]:hidden`}>
                  More <Chevron width="14" height="14" className="transition-transform group-open:rotate-180 motion-reduce:transition-none" />
                </summary>
                <div className="menu-pop absolute right-0 z-20 mt-1 flex min-w-44 flex-col rounded-xl border border-line bg-card p-1.5 shadow-2xl">
                  <button type="button" onClick={() => setRawOpen(true)} className={menuItem}>Raw output</button>
                  <CopySummary incident={inc} cited={cited} className={menuItem} />
                </div>
              </details>
            ) : (
              <>
                <button type="button" onClick={() => setRawOpen(true)} className={ghost}>Raw output</button>
                <CopySummary incident={inc} cited={cited} className={ghost} />
              </>
            )}
            {/* T-0016: this incident's console in the side panel (an approver's; the API decides each command) */}
            {dock.visible && String(inc.target).includes("/") && (
              <button type="button" onClick={() => dock.open({ incident: inc })} title={`Open the console on ${hostOf(inc.target)}`}
                className={`${ghost} inline-flex items-center gap-2`}>
                <TerminalIcon width="16" height="16" /> {detailsOpen ? "Console" : `Open console on ${hostOf(inc.target)}`}
              </button>
            )}
            <DiagnoseForm fixedTarget={inc.target} compact />
            {/* ACR-0041: shown only on an escalated incident, when /me lists resolve_incident */}
            <ResolveIncident incident={inc} onResolved={retry} />
          </div>
        </div>
      </section>

      <TabList tabs={tabs} value={tab} onChange={setTab} label="Incident information" />

      <TabPanel id="overview" value={tab}>
        <div className="space-y-4">
          <div className="grid grid-cols-[minmax(0,1fr)] items-start gap-4 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
            <WhyCard incident={inc} events={events} cited={cited} onJump={jumpToEvidence} />
            <div className="space-y-4">
              {showMini && <MiniMap topology={topology} incident={inc} onOpen={() => setTab("map")} />}
              {showMetrics && <Suspense fallback={<Skeleton className="h-72" />}><MiniCharts metrics={metrics} onOpen={() => setTab("metrics")} /></Suspense>}
              <IncidentChat key={inc.id} incident={inc} events={events} cited={cited} />
            </div>
          </div>
          <ActionTrail action={inc.action} />
          {/* The pending approval, decided here by an approver (the same steps as Actions) */}
          <IncidentApproval key={inc.action?.approval?.id ?? "none"} action={inc.action} onAnswered={retry} />
          <ActionSuggestions items={inc.next_actions} />
        </div>
      </TabPanel>
      <TabPanel id="map" value={tab}>{showMap && <SystemMap topology={topology} incident={inc} title="System map around the incident" />}</TabPanel>
      <TabPanel id="metrics" value={tab}>{showMetrics && <Suspense fallback={<Skeleton className="h-96" />}><MetricsTab metrics={metrics} incident={inc} range={range} onRange={setRange} /></Suspense>}</TabPanel>
      <TabPanel id="timeline" value={tab}>
        <RunTimeline incident={inc} events={events} active={active} reconnecting={reconnecting} evidenceIds={evidenceIds} onJump={jumpToEvidence} />
      </TabPanel>
      <TabPanel id="evidence" value={tab}>
        {hasEvidence ? <EvidenceSection items={inc.evidence} cited={cited} host={hostOf(inc.target)} open={openEvidence} onToggle={toggleEvidence} /> : <RestrictedNotice title="Evidence" label="Evidence" />}
      </TabPanel>
      <TabPanel id="audit" value={tab}>
        {hasAudit ? <AuditSection items={inc.audit} evidenceIds={evidenceIds} onJump={jumpToEvidence} /> : <RestrictedNotice title="Audit" label="Audit" />}
      </TabPanel>

      <RawOutputDialog open={rawOpen} onClose={() => setRawOpen(false)} incident={inc} events={events} />
    </div>
  );
}
