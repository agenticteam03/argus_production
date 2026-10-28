import { Card, Pill } from "./ui.jsx";
import { dateTime } from "../utils/format.js";

const RISKS = { green: ["Green risk", "green"], amber: ["Amber risk", "amber"], red: ["Red risk", "red"] };

// The approvals waiting for a person (GET /api/v1/ops/approvals). Opening one shows its frozen proposal.
export default function PendingApprovals({ items, onOpen }) {
  return <Card title="Waiting for a decision" count={items.length}>
    {items.length === 0 ? <p className="text-sm text-muted">No approval is waiting in your scope.</p> :
      <ul className="divide-y divide-line">
        {items.map((a) => {
          const [label, tone] = RISKS[a.risk] ?? ["Risk unavailable", "neutral"];
          return <li key={a.id} className="flex flex-wrap items-center gap-3 py-3 text-sm">
            <strong className="font-mono">{a.capability}</strong>
            <span className="break-all text-muted">{a.target}</span>
            <Pill tone={tone}>{label}</Pill>
            {a.verdict === "doubt" && <Pill tone="amber">Judge doubted</Pill>}
            <span className="text-xs text-muted">{a.id} · expires {dateTime(a.expires_at)}</span>
            <button type="button" onClick={() => onOpen(a.id)}
              className="ml-auto cursor-pointer rounded-lg bg-accent-solid px-3 py-1.5 text-white">Open</button>
          </li>;
        })}
      </ul>}
  </Card>;
}
