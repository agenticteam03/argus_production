import { firstSentence } from "../utils/incidentView.js";
import SafeMarkdown from "./SafeMarkdown.jsx";

// The answer at the top of the incident: root cause and, only when the backend provides it, the next step for a person.
export default function AnswerBlock({ incident: inc, active }) {
  const hasCause = Boolean(inc.root_cause_target || inc.diagnosis);
  if (!hasCause) return <p className="text-sm text-muted">{active ? "No diagnosis yet" : "No diagnosis was produced"}</p>;

  return (
    <div className={`grid gap-x-6 gap-y-4 ${inc.recommendation ? "md:grid-cols-[minmax(0,1fr)_minmax(0,0.75fr)]" : ""}`}>
      <div className="min-w-0">
        <p className="text-xs text-muted">Root cause</p>
        {inc.root_cause_target && <p className="mt-0.5 break-all font-mono text-sm font-medium text-ink">{inc.root_cause_target}</p>}
        {inc.diagnosis && <div className="markdown-body mt-1 !text-sm"><SafeMarkdown>{firstSentence(inc.diagnosis).replace(/^\**root cause\**\s*[:\-–]\s*/i, "")}</SafeMarkdown></div>}
      </div>
      {inc.recommendation && (
        <div className="min-w-0">
          <p className="text-xs text-muted">Next step for a person</p>
          <div className="markdown-body mt-0.5 !text-sm"><SafeMarkdown>{inc.recommendation}</SafeMarkdown></div>
        </div>
      )}
    </div>
  );
}
