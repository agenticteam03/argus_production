import { dateTime } from "./format.js";

// Pure derivations for the incident page and the incident lists. No React, no fetch: easy to unit-test.

const TRIGGER_KINDS = new Set(["reported_symptom", "alert"]);
export const humanize = (v) => (v ? String(v).replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()) : null);

export const shortName = (target) => (target ? String(target).split(/[/:]/).pop() : "");
export const hostOf = (target) => (target ? String(target).split("/")[0] : "");

export function firstSentence(text) {
  const t = String(text ?? "").trim();
  const m = t.match(/^[\s\S]*?[.!?](?=\s|$)/);
  return m ? m[0] : t;
}

export function formatMs(ms) {
  if (ms == null || !Number.isFinite(ms)) return "—";
  if (ms < 60000) return `${(ms / 1000).toFixed(1)} s`;
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)} min ${s % 60} s`;
}

const last = (list, test) => [...list].reverse().find(test);

// The real events can carry objects where the demo has plain strings (a recalled passage, a decision). Take a readable
// string from them and never print "[object Object]"; when nothing readable is there, say nothing about it.
const REF_KEYS = ["runbook_id", "runbook", "id", "doc_id", "source", "file", "path", "name", "title"];
const KIND_KEYS = ["kind", "type", "action", "decision", "name", "next", "choice"];
const pick = (v, keys) => {
  if (typeof v === "string") return v.trim() || null;
  if (typeof v === "number") return String(v);
  if (v && typeof v === "object") for (const k of keys) if (typeof v[k] === "string" && v[k].trim()) return v[k].trim();
  return null;
};
const refName = (s) => String(s).split("/").pop().replace(/\.md$/i, "");
const unique = (list) => [...new Set(list)];
const refsOf = (passages) => unique((Array.isArray(passages) ? passages : []).map((p) => pick(p, REF_KEYS)).filter(Boolean).map(refName));

function summarize(name, evs, reads) {
  const exit = last(evs, (e) => e.phase === "exit");
  const d = exit?.data ?? {};
  switch (name) {
    case "detect":
      { const found = pick(d.class ?? d.result, []); return found ? `Matched ${found}` : exit ? "Detection finished" : "Detecting"; }
    case "recall": {
      const refs = refsOf(d.passages);
      const n = Array.isArray(d.passages) ? d.passages.length : 0;
      if (refs.length) return `Runbook ${refs.join(", ")}`;
      return n ? `${n} runbook ${n === 1 ? "passage" : "passages"} recalled` : exit ? "No runbook recalled" : "Recalling runbooks";
    }
    case "investigate": {
      const dec = d.decision && typeof d.decision === "object" ? d.decision : {};
      const kind = pick(d.decision, KIND_KEYS);
      const who = d.decided_by ?? dec.decided_by;
      const by = who === "rule" ? " (rules)" : who === "model" ? " (AI)" : "";
      const root = d.root_cause_target ?? dec.root_cause_target;
      const conf = d.confidence ?? dec.confidence;
      if (kind === "conclude" || (!kind && root)) {
        return `Concluded${root ? `: root cause ${shortName(String(root))}` : ""}${conf != null && typeof conf !== "object" ? `, confidence ${conf}` : ""}${by}`;
      }
      if (kind === "use_read_tools") {
        const n = Array.isArray(dec.calls) ? dec.calls.length : 0;
        return n ? `Chose ${n} read ${n === 1 ? "tool" : "tools"}${by}` : `Chose read tools${by}`;
      }
      if (kind === "escalate") return `Escalated${pick(dec.reason, []) ? `: ${pick(dec.reason, [])}` : ""}${by}`;
      if (kind) return `${humanize(kind)}${by}`;
      return exit ? `Decision recorded${by}` : "Investigating";
    }
    case "act": {
      if (!reads.length) return exit ? "No reads" : "Reading";
      const bad = reads.filter((r) => r.status && r.status !== "ok").length;
      return `${reads.length} read${reads.length === 1 ? "" : "s"} · ${bad ? `${bad} not ok` : "all ok"}`;
    }
    case "propose_action":
      return d.action ? `Proposed ${humanize(d.action).toLowerCase()}` : exit ? "Action proposed" : "Proposing an action";
    case "evidence_pack":
      return exit ? "Evidence pack collected" : "Collecting evidence";
    case "record":
      return d.outcome ? `Closed as ${humanize(d.outcome).toLowerCase()}` : exit ? "Recorded" : "Recording";
    default:
      return exit ? "Finished" : "In progress";
  }
}

// One entry per run of consecutive events of the same node (a node can appear twice, e.g. investigate before and after act).
export function stages(events) {
  const groups = [];
  for (const e of events ?? []) {
    const g = groups.at(-1);
    if (g && g.name === e.node) g.events.push(e);
    else groups.push({ name: e.node, events: [e] });
  }
  return groups.map((g, i) => {
    const start = Date.parse(g.events[0].at);
    const next = groups[i + 1]?.events[0];
    const end = Date.parse((next ?? g.events.at(-1)).at);
    const reads = g.events
      .filter((e) => e.phase === "step" && e.data?.capability)
      .map((e) => ({ capability: e.data.capability, target: e.data.target ?? null, status: e.data.status ?? null, evidenceId: e.data.evidence_id ?? null }));
    return {
      name: g.name,
      at: g.events[0].at,
      start,
      end,
      durationMs: Number.isFinite(start) && Number.isFinite(end) ? Math.max(0, end - start) : null,
      done: i < groups.length - 1 || g.events.some((e) => e.phase === "exit"),
      summary: summarize(g.name, g.events, reads),
      reads,
    };
  });
}

export function decidedBy(events) {
  const d = (events ?? []).filter((e) => e.node === "investigate" && e.phase === "exit").map((e) => e.data?.decided_by).filter(Boolean);
  if (d.includes("model")) return "AI";
  return d.length ? "rules" : null;
}

// Never guessed: only what the backend reports.
export const modelCalls = (inc) => (Number.isFinite(inc?.model_calls) ? inc.model_calls : null);

export function citedEvidence(inc, events) {
  if (Array.isArray(inc?.cited_evidence)) return inc.cited_evidence;
  const rec = last(events ?? [], (e) => e.node === "record" && e.phase === "exit" && Array.isArray(e.data?.cited));
  return rec ? rec.data.cited : [];
}

export function groupEvidence(evidence, host) {
  const key = (e) => (TRIGGER_KINDS.has(e.kind) ? "triggered" : e.kind === "metric_snapshot" ? "metrics" : e.kind === "observation" ? "reads" : "other");
  const defs = [["triggered", "What triggered it"], ["metrics", "Metrics"], ["reads", host ? `Reads on ${host}` : "Reads"], ["other", "Other"]];
  return defs.map(([k, title]) => ({ title, items: (evidence ?? []).filter((e) => key(e) === k) })).filter((g) => g.items.length);
}

// Runbooks the agent recalled to guide the run: the ids in the recall stage's `passages`, once each, in order.
// A passage is a string or an object; the reference is its runbook id, file or title (see REF_KEYS), shortened to the file name.
export function runbooksRead(events) {
  const refs = [];
  for (const e of events ?? []) {
    if (e.node !== "recall" || e.phase !== "exit") continue;
    for (const r of refsOf(e.data?.passages)) if (!refs.includes(r)) refs.push(r);
  }
  return refs;
}

export function chain(inc) {
  const from = inc?.target ?? null;
  const to = inc?.root_cause_target ?? null;
  return { from, to, sameTarget: !to || to === from };
}

const REASONS = {
  no_incident: "Healthy: no incident found",
  undiagnosable: "No conclusion reached: evidence was recorded",
  unsupported_escalated: "Not covered by a runbook: escalated to a person",
  no_action_escalated: "No safe action available: escalated to a person",
  refused: "Request refused",
};

// One line for the lists: the answer when there is one, otherwise what the outcome means.
export function reason(inc) {
  if (inc?.outcome == null) return inc?.status === "queued" ? "Waiting to start" : inc?.status === "running" ? "Investigation in progress" : "No outcome yet";
  if (inc.outcome === "diagnosed") {
    return inc.root_cause_target && inc.root_cause_target !== inc.target ? `Root cause: ${shortName(inc.root_cause_target)}` : "Diagnosed on the target itself";
  }
  return REASONS[inc.outcome] ?? humanize(inc.outcome);
}

export function summaryText(inc, cited = []) {
  const lines = [`Incident ${inc.id}`, `Target: ${inc.target}`, `Status: ${humanize(inc.status) ?? "Unknown"} · Outcome: ${inc.outcome ? humanize(inc.outcome) : "none yet"}`];
  if (inc.root_cause_target) lines.push(`Root cause: ${inc.root_cause_target}`);
  if (inc.confidence != null) lines.push(`Confidence: ${inc.confidence}`);
  if (inc.diagnosis) lines.push(`Diagnosis: ${inc.diagnosis}`);
  if (inc.recommendation) lines.push(`Next step: ${inc.recommendation}`);
  if (cited.length) lines.push(`Cited evidence: ${cited.join(", ")}`);
  if (inc.opened_at) lines.push(`Opened: ${dateTime(inc.opened_at)}`);
  return lines.join("\n");
}
