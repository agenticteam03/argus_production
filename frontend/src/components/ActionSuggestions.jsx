import { Card, Pill } from "./ui.jsx";

const RISK = {
  green: ["Green risk", "green"],
  amber: ["Amber risk", "amber"],
  red: ["Red risk", "red"],
};
// The suggestion's left edge takes its risk colour, so the riskier one is seen first.
const EDGE = { green: "border-l-emerald-400", amber: "border-l-amber-400", red: "border-l-red-400", neutral: "border-l-line" };

const BASIS = { runbook: "Runbook", memory: "Verified memory", reference: "Curated reference", operator: "Operator" };

const Chip = ({ name, mono = false, children }) => (
  <span className="inline-flex max-w-full items-baseline gap-1 rounded-md bg-ink/5 px-2 py-0.5 text-xs">
    <span className="text-muted">{name}</span>
    <span className={`min-w-0 break-all text-body ${mono ? "font-mono" : ""}`}>{children}</span>
  </span>
);

// Incident candidates are read-only. The approval workflow uses a separate frozen proposal and private session.
export default function ActionSuggestions({ items = [] }) {
  if (!items.length) return null;
  return (
    <Card title="Suggested actions" count={items.length}>
      <p className="mb-3 text-[13px] text-muted">These are suggestions from reviewed cards and current evidence. They do not authorize an action.</p>
      <ul className="space-y-2.5">
        {items.map((item, index) => {
          const [riskLabel, tone] = RISK[item.risk_color] ?? ["Risk unavailable", "neutral"];
          return <li key={`${item.action}:${item.target}:${index}`}
            className={`rounded-xl border border-l-4 border-line bg-ink/[0.02] p-3.5 ${EDGE[tone] ?? EDGE.neutral}`}>
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <h3 className="font-mono text-sm font-semibold text-ink">{item.action}</h3>
                <p className="break-all font-mono text-xs text-muted">{item.target}</p>
              </div>
              <Pill tone={tone}>{riskLabel}</Pill>
            </div>
            <p className="mt-2 text-[13px] text-body">{item.text}</p>
            <div className="mt-3 flex flex-wrap gap-1.5">
              <Chip name="Basis">{BASIS[item.basis] ?? "Unverified"}</Chip>
              <Chip name="Grounds">{item.grounds?.join(", ") || "None cited"}</Chip>
              <Chip name="Evidence" mono>{item.evidence_refs?.join(", ") || "None cited"}</Chip>
            </div>
            <p className="mt-3 text-xs text-muted">Suggestion only · No action is available from this card.</p>
          </li>;
        })}
      </ul>
    </Card>
  );
}
