import { useState } from "react";
import { consoleAuditLine } from "../utils/consoleAudit.js";
import { auditDetail, clock, dateTime, shortHash } from "../utils/format.js";
import { groupEvidence } from "../utils/incidentView.js";
import SafeMarkdown from "./SafeMarkdown.jsx";
import { Card, InsetRow, Lock, Segmented } from "./ui.jsx";

// Shown when the server sent no `evidence` / `audit` key at all (viewer). Not an error.
export const RestrictedNotice = ({ title, label }) => (
  <Card title={title}>
    <p className="flex items-center gap-2 text-sm text-muted"><Lock width="16" height="16" /> {label} is visible to operators and approvers.</p>
  </Card>
);

const NoItems = ({ children }) => <p className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-muted">{children}</p>;
const link = "cursor-pointer font-mono text-xs text-accent-hover hover:underline";
const toggle = "cursor-pointer text-xs text-accent-hover hover:underline";

const FILTERS = [{ value: "all", label: "All" }, { value: "cited", label: "Cited" }, { value: "errors", label: "Errors" }];

function EvidenceItem({ e, cited, open, onToggle }) {
  const panel = `evidence-panel-${e.evidence_id}`;
  const facts = [["Executor", e.executor], ["Caller", e.caller], ["Source time", dateTime(e.source_time)], ["SHA-256", shortHash(e.sha256)]];
  return (
    <InsetRow as="li" id={`evidence-${e.evidence_id}`} tabIndex={-1} className="outline-none focus:ring-2 focus:ring-inset focus:ring-accent-hover">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="min-w-0 text-sm">
          <span className="font-mono text-xs text-accent-hover">{e.evidence_id}</span> · <span className="font-medium">{e.kind ?? "—"}</span> <span className="text-muted">via {e.capability ?? "—"}</span>
        </p>
        <span className="flex items-center gap-2 text-xs text-muted">
          {cited && <span>cited</span>}
          <span className="rounded-md border border-line px-2 py-0.5">{e.status ?? "—"}</span>
        </span>
      </div>
      <p className="mt-0.5 break-words text-xs text-muted">{e.target ?? "—"} · collected {dateTime(e.collected_at)}</p>
      <button aria-expanded={open} aria-controls={panel} onClick={onToggle} className={`mt-1.5 ${toggle}`}>{open ? "Hide content" : "Show content"}</button>
      <div id={panel} hidden={!open} className="mt-2 space-y-2 border-t border-line pt-2">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs md:grid-cols-4">
          {facts.map(([k, v]) => <div key={k} className="min-w-0"><dt className="text-muted">{k}</dt><dd className="break-words text-body">{v ?? "—"}</dd></div>)}
        </dl>
        <div className="markdown-body !text-[13px]"><SafeMarkdown>{e.model_text ?? "—"}</SafeMarkdown></div>
        <p className="break-all font-mono text-[11px] text-muted">{e.sha256 ?? "—"}</p>
      </div>
    </InsetRow>
  );
}

export function EvidenceSection({ items, cited, host, open, onToggle }) {
  const [filter, setFilter] = useState("all");
  const isCited = (e) => cited.includes(e.evidence_id);
  const shown = items.filter((e) => filter === "all" || (filter === "cited" ? isCited(e) : e.status && e.status !== "ok"));
  const groups = groupEvidence(shown, host);

  return (
    <Card title="Evidence" count={items.length} right={items.length > 0 && <Segmented label="Filter evidence" options={FILTERS} value={filter} onChange={setFilter} />}>
      {items.length === 0 ? (
        <NoItems>No evidence was collected.</NoItems>
      ) : groups.length === 0 ? (
        <NoItems>Nothing matches this filter.</NoItems>
      ) : (
        <div className="max-h-[62vh] space-y-4 overflow-auto pr-1">
          {groups.map((g) => (
            <section key={g.title}>
              <h3 className="mb-1.5 text-xs text-muted">{g.title}</h3>
              <ul className="space-y-2">{g.items.map((e) => <EvidenceItem key={e.evidence_id} e={e} cited={isCited(e)} open={open.has(e.evidence_id)} onToggle={() => onToggle(e.evidence_id)} />)}</ul>
            </section>
          ))}
        </div>
      )}
    </Card>
  );
}

// `detail` is an object on the real API and a string in the demo data; render text inline and an object as JSON.
function AuditDetail({ detail }) {
  const d = auditDetail(detail);
  if (d.kind === "empty") return <p className="text-[13px] text-muted">—</p>;
  if (d.kind === "json") return <pre className="overflow-x-auto rounded-lg bg-card p-3 text-xs text-body">{d.text}</pre>;
  return <p className="whitespace-pre-wrap text-[13px] text-body">{d.text}</p>;
}

export function AuditSection({ items, evidenceIds, onJump }) {
  // Rows stay compact; the JSON detail and the policy rule are shown on demand.
  const [open, setOpen] = useState(() => new Set());
  const flip = (i) => setOpen((prev) => { const next = new Set(prev); next.has(i) ? next.delete(i) : next.add(i); return next; });

  return (
    <Card title="Audit" count={items.length} right={<span className="text-xs text-muted">Insert-only</span>}>
      {items.length === 0 ? (
        <NoItems>No audit entries.</NoItems>
      ) : (
        <ul className="max-h-[62vh] space-y-1.5 overflow-auto pr-1">
          {items.map((a, i) => {
            const detail = auditDetail(a.detail);
            const said = consoleAuditLine(a);       // T-0016: a console row in plain words; its JSON stays under Details
            const panel = `audit-detail-${i}`;
            const expandable = detail.kind === "json" || Boolean(a.policy_rule);
            const linked = a.evidence_id && evidenceIds.has(a.evidence_id);
            return (
              <InsetRow as="li" key={i} className="text-[13px]">
                <div className="grid grid-cols-[4.5rem_minmax(0,1fr)] items-baseline gap-x-3 gap-y-0.5 md:grid-cols-[4.5rem_minmax(0,14rem)_minmax(0,1fr)_9rem]">
                  <time dateTime={a.at} title={dateTime(a.at)} className="font-mono text-xs text-muted">{clock(a.at)}</time>
                  <span className="min-w-0 break-words font-mono text-xs text-ink">{a.event ?? "—"}</span>
                  <span className="col-start-2 min-w-0 break-words md:col-start-auto">
                    {linked ? <button onClick={() => onJump(a.evidence_id)} className={link}>{a.evidence_id}</button>
                      : said ? <span className="text-body">{said}</span>
                      : detail.kind === "text" ? <span className="text-body">{detail.text}</span>
                        : a.evidence_id ? <span className="font-mono text-xs text-muted">{a.evidence_id}</span>
                          : <span className="text-muted">—</span>}
                    {expandable && <button aria-expanded={open.has(i)} aria-controls={panel} onClick={() => flip(i)} className={`ml-3 ${toggle}`}>Details</button>}
                  </span>
                  <span className="col-start-2 min-w-0 truncate text-xs text-muted md:col-start-auto" title={a.actor ?? undefined}>{a.actor ?? "—"}</span>
                </div>
                {expandable && (
                  <div id={panel} hidden={!open.has(i)} className="mt-2 space-y-2 border-t border-line pt-2">
                    <dl className="grid grid-cols-2 gap-x-4 text-xs">
                      <div><dt className="text-muted">Capability</dt><dd>{a.capability ?? "—"}</dd></div>
                      <div><dt className="text-muted">Policy rule</dt><dd className="break-words font-mono">{a.policy_rule ?? "—"}</dd></div>
                    </dl>
                    {detail.kind === "json" && <AuditDetail detail={a.detail} />}
                  </div>
                )}
              </InsetRow>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
