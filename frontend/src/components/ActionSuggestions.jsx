import { Card, Pill } from "./ui.jsx";

const RISK = {
  green: ["Green risk", "green"],
  amber: ["Amber risk", "amber"],
  red: ["Red risk", "red"],
};

const BASIS = { runbook: "Runbook", memory: "Verified memory", reference: "Curated reference", operator: "Operator" };

// Incident candidates are read-only. The approval workflow uses a separate frozen proposal and private session.
export default function ActionSuggestions({ items = [] }) {
  if (!items.length) return null;
  return (
    <Card title="Suggested actions" count={items.length}>
      <p className="mb-3 text-[13px] text-muted">These are suggestions from reviewed cards and current evidence. They do not authorize an action.</p>
      <ul className="stagger space-y-3">
        {items.map((item, index) => {
          const [riskLabel, tone] = RISK[item.risk_color] ?? ["Risk unavailable", "neutral"];
          return <li key={`${item.action}:${item.target}:${index}`} className="rounded-xl border border-line bg-field p-3.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="font-mono text-sm font-medium text-ink">{item.action}</h3>
              <Pill tone={tone}>{riskLabel}</Pill>
            </div>
            <p className="mt-1 break-all text-[13px] text-body">{item.target}</p>
            <p className="mt-2 text-[13px] text-muted">{item.text}</p>
            <dl className="mt-3 grid gap-2 border-t border-line pt-3 text-xs sm:grid-cols-2">
              <div><dt className="text-muted">Basis</dt><dd className="mt-0.5 text-body">{BASIS[item.basis] ?? "Unverified"}</dd></div>
              <div><dt className="text-muted">Grounds</dt><dd className="mt-0.5 break-all text-body">{item.grounds?.join(", ") || "None cited"}</dd></div>
              <div className="sm:col-span-2"><dt className="text-muted">Evidence</dt><dd className="mt-0.5 break-all font-mono text-body">{item.evidence_refs?.join(", ") || "None cited"}</dd></div>
            </dl>
            <p className="mt-3 text-xs font-medium text-muted">Suggestion only · No action is available from this card.</p>
          </li>;
        })}
      </ul>
    </Card>
  );
}
