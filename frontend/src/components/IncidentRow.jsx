import { Link } from "react-router-dom";
import { dateTime, timeAgo } from "../utils/format.js";
import { reason } from "../utils/incidentView.js";
import { OutcomeBadge, StatusBadge } from "./ui.jsx";

// One incident list row (shape of GET /api/v1/incidents). `compact` is used by the Dashboard card.
export default function IncidentRow({ incident: i, compact = false }) {
  return (
    <li>
      <Link to={`/incidents/${i.id}`} className="block rounded-xl bg-field p-3 transition hover:bg-white/[0.06] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-hover motion-reduce:transition-none">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="min-w-0 truncate font-mono text-xs text-accent-hover">{i.id}</span>
          <span className="flex flex-wrap gap-1.5"><StatusBadge status={i.status} /><OutcomeBadge outcome={i.outcome} /></span>
        </div>
        <p className="mt-1.5 text-sm font-medium">{i.target}</p>
        <p className="mt-0.5 text-[13px] text-[#a3abba]">{reason(i)}</p>
        <p className="mt-1 text-xs text-muted">
          <time dateTime={i.opened_at} title={dateTime(i.opened_at)}>{timeAgo(i.opened_at)}</time>
          {!compact && <> · {i.class ?? "—"} · {i.strategy ?? "—"}</>}
        </p>
      </Link>
    </li>
  );
}
