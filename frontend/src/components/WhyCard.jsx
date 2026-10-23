import { Link } from "react-router-dom";
import { chain, decidedBy, firstSentence, modelCalls, runbooksRead, shortName } from "../utils/incidentView.js";
import RunbooksRead from "./RunbooksRead.jsx";
import SafeMarkdown from "./SafeMarkdown.jsx";
import { Card, Disclosure, Fact, InsetRow } from "./ui.jsx";

const firstLine = (text) => String(text ?? "").split("\n").find((l) => l.trim())?.trim() ?? "";

function CitedRow({ id, evidence, onJump }) {
  const e = evidence?.find((x) => x.evidence_id === id);
  const short = id.length > 12 ? `${id.slice(0, 7)}…` : id;
  return (
    <InsetRow className="grid grid-cols-[4.5rem_minmax(0,1fr)_auto] items-baseline gap-3 text-[13px]">
      <span className="truncate text-xs text-muted">{e?.capability ?? e?.kind ?? "evidence"}</span>
      <span className="truncate text-body" title={e ? firstLine(e.model_text) : undefined}>{e ? `${shortName(e.target)} · ${firstLine(e.model_text) || "—"}` : id}</span>
      {e ? (
        <Link to={{ search: "?tab=evidence", hash: `#evidence-${id}` }} onClick={(ev) => { ev.preventDefault(); onJump(id); }} className="font-mono text-xs text-accent-hover hover:underline">{short}</Link>
      ) : (
        <span className="font-mono text-xs text-muted">{short}</span>
      )}
    </InsetRow>
  );
}

export default function WhyCard({ incident: inc, events, cited, onJump }) {
  const c = chain(inc);
  const by = decidedBy(events);
  const calls = modelCalls(inc);
  const rest = inc.diagnosis && inc.diagnosis.trim() !== firstSentence(inc.diagnosis) ? inc.diagnosis : null;
  const ruledOut = Array.isArray(inc.ruled_out) ? inc.ruled_out : [];
  const runbooks = runbooksRead(events);

  return (
    <Card title="Why Argus concluded this">
      {c.to && (
        <p className="mb-4 flex flex-wrap items-center gap-2 text-sm">
          <code className="font-mono text-ink">{shortName(c.from)}</code>
          {c.sameTarget ? (
            <span className="text-muted">is the root cause</span>
          ) : (
            <>
              <span className="text-muted" aria-hidden="true">→</span>
              <span className="sr-only">root cause</span>
              <code className="font-mono text-red-300">{shortName(c.to)}</code>
            </>
          )}
        </p>
      )}

      <dl className="grid grid-cols-2 gap-x-6 gap-y-3">
        <Fact label="Confidence">{inc.confidence == null ? null : String(inc.confidence)}</Fact>
        <Fact label="Decided by">{by === "rules" ? "Rules (no AI)" : by}</Fact>
        {calls != null && <Fact label="AI calls">{String(calls)}</Fact>}
      </dl>

      {rest && (
        <div className="mt-4 border-t border-line pt-4">
          <Disclosure summary="Full diagnosis"><div className="markdown-body"><SafeMarkdown>{rest}</SafeMarkdown></div></Disclosure>
        </div>
      )}

      <div className="mt-4 border-t border-line pt-4">
        <h3 className="text-sm font-medium">Findings</h3>
        {inc.findings?.length ? (
          <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-body">{inc.findings.map((f, i) => <li key={i}>{f}</li>)}</ul>
        ) : (
          <p className="mt-2 text-sm text-muted">No findings recorded.</p>
        )}
      </div>

      {runbooks.length > 0 && (
        <div className="mt-4 border-t border-line pt-4">
          <h3 className="text-sm font-medium">Runbooks it read</h3>
          <RunbooksRead ids={runbooks} />
        </div>
      )}

      {cited.length > 0 && (
        <div className="mt-4 border-t border-line pt-4">
          <h3 className="text-sm font-medium">Evidence it cites</h3>
          <div className="mt-2 space-y-1.5">{cited.map((id) => <CitedRow key={id} id={id} evidence={inc.evidence} onJump={onJump} />)}</div>
        </div>
      )}

      {ruledOut.length > 0 && (
        <div className="mt-4 border-t border-line pt-4">
          <Disclosure summary={`${ruledOut.length} other ${ruledOut.length === 1 ? "cause" : "causes"} ruled out`}>
            <ul className="list-disc space-y-1 pl-5 text-sm text-body">{ruledOut.map((r, i) => <li key={i}>{r}</li>)}</ul>
          </Disclosure>
        </div>
      )}
    </Card>
  );
}
