import { dateTime, duration } from "./format.js";
import { decidedBy, firstSentence, humanize, modelCalls, runbooksRead, shortName } from "./incidentView.js";

// "Ask about this incident": answers built only from the incident's own data (its fields, run events and evidence).
// No model is called and nothing is invented: a question the data cannot answer says so. Free text is matched to a
// topic by keywords; anything else gets the list of topics.
export const SUGGESTIONS = ["What happened?", "Why this root cause?", "What should I do next?", "Which runbooks did it read?"];

const plain = (t) => String(t ?? "").replace(/[*`#>]/g, "").replace(/\s+\n/g, "\n").trim();
const firstLine = (t) => plain(t).split("\n").find((l) => l.trim()) ?? "";
const list = (items) => items.map((i) => `• ${i}`).join("\n");

const TOPICS = [
  ["runbooks", ["runbook", "playbook", "guide"]],
  ["evidence", ["evidence", "proof", "cite", "cites", "support", "sure", "based on"]],
  ["next", ["next", "what do i do", "what should", "fix", "recommend", "action", "solve", "resolve", "remediat"]],
  ["ruledOut", ["ruled out", "rule out", "other cause", "alternative", "else"]],
  ["decided", ["who decided", "decided", "ai", "model", "rules", "llm"]],
  ["time", ["how long", "duration", "took", "when", "opened", "closed", "time", "start", "finish"]],
  ["findings", ["finding", "found", "observ"]],
  ["cause", ["root cause", "cause", "why", "because", "reason", "confidence", "diagnos"]],
  ["summary", ["what happened", "happen", "summar", "explain", "overview", "tell me", "what is", "what's"]],
];

export function topicOf(question) {
  const q = ` ${String(question).toLowerCase()} `;
  return TOPICS.find(([, words]) => words.some((w) => (w.length <= 3 ? new RegExp(`\\b${w}\\b`).test(q) : q.includes(w))))?.[0] ?? null;
}

export function answerAboutIncident(question, { incident: inc, events = [], cited = [] }) {
  const topic = topicOf(question);
  const status = humanize(inc.status) ?? "unknown status";

  switch (topic) {
    case "summary": {
      const head = `${inc.target}: ${status.toLowerCase()}${inc.outcome ? `, ${humanize(inc.outcome).toLowerCase()}` : ""}.`;
      const what = inc.diagnosis ? firstSentence(plain(inc.diagnosis)) : "No diagnosis was recorded for this incident.";
      return [head, what, inc.opened_at ? `Opened ${dateTime(inc.opened_at)}.` : null].filter(Boolean).join("\n");
    }
    case "cause": {
      if (!inc.root_cause_target && !inc.diagnosis) return "No root cause was identified for this incident.";
      return [
        inc.root_cause_target ? `Root cause: ${inc.root_cause_target}.` : null,
        inc.diagnosis ? plain(inc.diagnosis) : null,
        inc.confidence != null ? `Confidence: ${inc.confidence}.` : null,
      ].filter(Boolean).join("\n");
    }
    case "evidence": {
      if (!cited.length) {
        return "Argus did not cite specific evidence for this incident."
          + ("evidence" in inc ? ` ${inc.evidence.length} record${inc.evidence.length === 1 ? " was" : "s were"} collected.` : "");
      }
      const rows = cited.map((id) => {
        const e = inc.evidence?.find((x) => x.evidence_id === id);
        return e ? `${id}: ${e.capability ?? e.kind ?? "evidence"} on ${shortName(e.target)}${firstLine(e.model_text) ? ` — ${firstLine(e.model_text)}` : ""}` : id;
      });
      return `It cites ${cited.length} evidence record${cited.length === 1 ? "" : "s"}:\n${list(rows)}\nOpen the Evidence tab to read them.${"evidence" in inc ? "" : " (Evidence content is visible to operators and approvers.)"}`;
    }
    case "next":
      return inc.recommendation ? plain(inc.recommendation) : `No next step was recorded for this incident.${inc.status === "escalated" ? " Argus handed it to a person." : ""}`;
    case "ruledOut":
      return Array.isArray(inc.ruled_out) && inc.ruled_out.length ? `Causes ruled out:\n${list(inc.ruled_out.map(plain))}` : "No ruled-out causes were recorded.";
    case "runbooks": {
      const ids = runbooksRead(events);
      return ids.length ? `It read ${ids.join(", ")}. Open them from "Runbooks it read" on the Incident & Diagnosis tab.` : "No runbook was recalled for this run.";
    }
    case "decided": {
      const by = decidedBy(events);
      const calls = modelCalls(inc);
      if (!by && calls == null) return "This incident does not record who made the decisions.";
      return [by ? `Decisions were made ${by === "rules" ? "by rules" : "with AI"}.` : null, calls != null ? (calls === 0 ? "No AI calls were made." : `${calls} AI call${calls === 1 ? "" : "s"} were made.`) : null].filter(Boolean).join(" ");
    }
    case "time": {
      if (!inc.opened_at) return "No times were recorded.";
      return inc.closed_at
        ? `Opened ${dateTime(inc.opened_at)}, closed ${dateTime(inc.closed_at)}. It took ${duration(inc.opened_at, inc.closed_at)}.`
        : `Opened ${dateTime(inc.opened_at)} and still open.`;
    }
    case "findings":
      return inc.findings?.length ? `Findings:\n${list(inc.findings.map(plain))}` : "No findings were recorded.";
    default:
      return "I can answer about this incident: what happened, the root cause, the evidence it cites, the runbooks it read, the next step, who decided, and how long it took.";
  }
}
