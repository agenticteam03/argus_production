import { dateTime, shortHash } from "../utils/format.js";
import SafeMarkdown from "./SafeMarkdown.jsx";
import { Card, Lock } from "./ui.jsx";

// Shown when the server sent no `evidence` / `audit` key at all (viewer). Not an error.
export const RestrictedNotice = ({ title, label }) => (
  <Card title={title}>
    <p className="flex items-center gap-2 text-sm text-muted"><Lock width="16" height="16" /> {label} is visible to operators and admins.</p>
  </Card>
);

const NoItems = ({ children }) => <p className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-muted">{children}</p>;

function EvidenceItem({ e, open, onToggle }) {
  const panel = `evidence-panel-${e.evidence_id}`;
  const facts = [["Target", e.target], ["Executor", e.executor], ["Caller", e.caller], ["Collected", dateTime(e.collected_at)], ["Source time", dateTime(e.source_time)], ["SHA-256", shortHash(e.sha256)]];
  return (
    <li id={`evidence-${e.evidence_id}`} tabIndex={-1} className="rounded-xl bg-field p-3 outline-none focus-visible:ring-2 focus-visible:ring-accent-hover">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium">
          <span className="font-mono text-xs text-accent-hover">{e.evidence_id}</span> · {e.kind ?? "—"} <span className="font-normal text-muted">via {e.capability ?? "—"}</span>
        </p>
        <span className="rounded-md border border-line px-2 py-0.5 text-xs text-muted">{e.status ?? "—"}</span>
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs md:grid-cols-3">
        {facts.map(([k, v]) => <div key={k} className="min-w-0"><dt className="text-muted">{k}</dt><dd className="truncate text-[#d6dbe6]">{v ?? "—"}</dd></div>)}
      </dl>
      <button aria-expanded={open} aria-controls={panel} onClick={onToggle} className="mt-2 cursor-pointer text-xs text-accent-hover hover:underline">Details</button>
      <div id={panel} hidden={!open} className="mt-2 space-y-2 border-t border-line pt-2">
        <div className="markdown-body !text-[13px]"><SafeMarkdown>{e.model_text ?? "—"}</SafeMarkdown></div>
        <p className="break-all font-mono text-[11px] text-muted">{e.sha256 ?? "—"}</p>
      </div>
    </li>
  );
}

export function EvidenceSection({ items, open, onToggle }) {
  return (
    <Card title="Evidence" count={items.length}>
      {items.length === 0 ? (
        <NoItems>No evidence was collected.</NoItems>
      ) : (
        <ul className="space-y-2">{items.map((e) => <EvidenceItem key={e.evidence_id} e={e} open={open.has(e.evidence_id)} onToggle={() => onToggle(e.evidence_id)} />)}</ul>
      )}
    </Card>
  );
}

export function AuditSection({ items, evidenceIds, onJump }) {
  return (
    <Card title="Audit" count={items.length}>
      {items.length === 0 ? (
        <NoItems>No audit entries.</NoItems>
      ) : (
        <ul className="space-y-2">
          {items.map((a, i) => (
            <li key={i} className="rounded-xl bg-field p-3 text-xs">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <time dateTime={a.at} className="font-mono text-muted">{dateTime(a.at)}</time>
                <span className="text-sm font-medium">{a.event ?? "—"}</span>
                <span className="text-muted">{a.capability ?? "—"}</span>
              </div>
              <dl className="mt-1.5 grid grid-cols-2 gap-x-4 gap-y-1 md:grid-cols-3">
                <div><dt className="text-muted">Actor</dt><dd>{a.actor ?? "—"}</dd></div>
                <div><dt className="text-muted">Policy rule</dt><dd className="font-mono">{a.policy_rule ?? "—"}</dd></div>
                <div>
                  <dt className="text-muted">Evidence</dt>
                  <dd>
                    {a.evidence_id && evidenceIds.has(a.evidence_id) ? (
                      <button onClick={() => onJump(a.evidence_id)} className="cursor-pointer font-mono text-accent-hover hover:underline">{a.evidence_id}</button>
                    ) : (
                      <span className="font-mono">{a.evidence_id ?? "—"}</span>
                    )}
                  </dd>
                </div>
              </dl>
              <p className="mt-1.5 whitespace-pre-wrap text-[13px] text-[#d6dbe6]">{a.detail ?? "—"}</p>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
