import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import DiagnoseForm from "../components/DiagnoseForm.jsx";
import { AuditSection, EvidenceSection, RestrictedNotice } from "../components/EvidenceAudit.jsx";
import RunTimeline from "../components/RunTimeline.jsx";
import SafeMarkdown from "../components/SafeMarkdown.jsx";
import { Card, ErrorCard, OUTCOME_META, OutcomeBadge, Skeleton, STATUS_META, StatusBadge } from "../components/ui.jsx";
import { useIncident } from "../hooks/useIncident.js";
import { dateTime, duration, isActive } from "../utils/format.js";

const Back = () => (
  <Link to="/incidents" className="inline-flex text-[13px] text-accent-hover hover:underline">← Incidents</Link>
);
const Fact = ({ label, children }) => (
  <div className="min-w-0">
    <dt className="text-xs text-muted">{label}</dt>
    <dd className="mt-0.5 break-words text-sm leading-snug text-[#d6dbe6]">{children ?? "—"}</dd>
  </div>
);

export default function IncidentDetail() {
  const { id } = useParams();
  const { view, incident: inc, events, reconnecting, retry } = useIncident(id);
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

  const toggleEvidence = (key) => setOpenEvidence((prev) => { const next = new Set(prev); next.has(key) ? next.delete(key) : next.add(key); return next; });
  const jumpToEvidence = (key) => {
    setOpenEvidence((prev) => new Set(prev).add(key));
    setTimeout(() => document.getElementById(`evidence-${key}`)?.focus(), 0);
  };

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
  const evidenceIds = new Set((inc.evidence ?? []).map((e) => e.evidence_id));

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
        {inc.reason && <p className="mt-1.5 text-sm leading-relaxed text-[#a3abba]">{inc.reason}</p>}
        <dl className="mt-5 grid grid-cols-2 gap-x-4 gap-y-4 md:grid-cols-3">
          <Fact label="Class">{inc.incident_class}</Fact>
          <Fact label="Strategy">{inc.strategy}</Fact>
          <Fact label="Triggered by">{inc.trigger_kind}</Fact>
          <Fact label="Request">{inc.request_kind}</Fact>
          <Fact label="Principal">{inc.principal}</Fact>
          <Fact label="Trigger ID">{inc.trigger_id}</Fact>
          <Fact label="Opened">{dateTime(inc.opened_at)}</Fact>
          {inc.trace_url && (
            <Fact label="Agent trace">
              <a href={inc.trace_url} target="_blank" rel="noopener noreferrer" className="text-accent-hover hover:underline">Open in Langfuse</a>
            </Fact>
          )}
          <Fact label="Closed">{inc.closed_at ? `${dateTime(inc.closed_at)} (took ${duration(inc.opened_at, inc.closed_at)})` : "Still open"}</Fact>
        </dl>
        {/* ACR-0012: a new investigation of the same target (shown only when /me allows it) */}
        <div className="mt-5"><DiagnoseForm fixedTarget={inc.target} compact /></div>
      </section>

      <Card title="Diagnosis">
        {inc.diagnosis ? (
          <div className="markdown-body"><SafeMarkdown>{inc.diagnosis}</SafeMarkdown></div>
        ) : (
          <p className="text-sm text-muted">{active ? "No diagnosis yet" : "No diagnosis was produced"}</p>
        )}
        <dl className="mt-4 grid gap-4 border-t border-line pt-4 sm:grid-cols-2">
          <Fact label="Root cause target">{inc.root_cause_target}</Fact>
          <Fact label="Confidence">{inc.confidence == null ? null : String(inc.confidence)}</Fact>
        </dl>
        <div className="mt-4 border-t border-line pt-4">
          <h3 className="text-sm font-medium">Findings</h3>
          {inc.findings?.length ? (
            <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-[#d6dbe6]">{inc.findings.map((f, i) => <li key={i}>{f}</li>)}</ul>
          ) : (
            <p className="mt-2 text-sm text-muted">No findings recorded.</p>
          )}
        </div>
      </Card>

      <RunTimeline events={events} active={active} reconnecting={reconnecting} />

      {"evidence" in inc ? <EvidenceSection items={inc.evidence} open={openEvidence} onToggle={toggleEvidence} /> : <RestrictedNotice title="Evidence" label="Evidence" />}
      {"audit" in inc ? <AuditSection items={inc.audit} evidenceIds={evidenceIds} onJump={jumpToEvidence} /> : <RestrictedNotice title="Audit" label="Audit" />}
    </div>
  );
}
