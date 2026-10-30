import { Card, Pill } from "./ui.jsx";
import { dateTime } from "../utils/format.js";

const RISKS = { green: ["Green risk", "green"], amber: ["Amber risk", "amber"], red: ["Red risk", "red"] };

// The approvals waiting for a person (GET /api/v1/ops/approvals). Opening one shows its frozen proposal; the open one
// (`selected`) stays marked.
export default function PendingApprovals({ items, onOpen, selected = null }) {
  return <Card title="Waiting for a decision" count={items.length}>
    {items.length === 0 ? <p className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-sm text-muted">No approval is waiting in your scope.</p> :
      <ul className="stagger space-y-2">
        {items.map((a) => {
          const [label, tone] = RISKS[a.risk] ?? ["Risk unavailable", "neutral"];
          const on = a.id === selected;
          return <li key={a.id} className={`rounded-xl border p-3 text-sm transition ${on ? "border-accent bg-accent/[0.06]" : "border-line hover:bg-ink/[0.03]"}`}>
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <strong className="font-mono text-ink">{a.capability}</strong>
                <p className="break-all text-xs text-muted">{a.target}</p>
              </div>
              <button type="button" onClick={() => onOpen(a.id)} aria-current={on || undefined}
                className="shrink-0 cursor-pointer rounded-lg border border-line bg-field px-3 py-1.5 text-xs font-medium text-ink hover:bg-ink/5">Open</button>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <Pill tone={tone}>{label}</Pill>
              {a.verdict === "doubt" && <Pill tone="amber">Judge doubted</Pill>}
            </div>
            <p className="mt-2 break-all text-xs text-muted">{a.id} · expires {dateTime(a.expires_at)}</p>
          </li>;
        })}
      </ul>}
  </Card>;
}
