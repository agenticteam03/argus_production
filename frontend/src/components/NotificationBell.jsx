import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { useWaitingApprovals } from "../hooks/useWaitingApprovals.js";
import { Bell } from "./ui.jsx";

const summary = "relative grid size-10 cursor-pointer list-none place-items-center rounded-xl border border-line bg-field text-muted hover:text-ink [&::-webkit-details-marker]:hidden";
const LIMIT = 50;                                            // the API counts at most 50
const closeMenu = (e) => e.currentTarget.closest("details")?.removeAttribute("open");

// The header's bell (ACR-0042): how many approvals wait for this approver, and the way to them. The count carries
// nothing else; inside a confirmed private session `items` names each one (the private list).
export function NotificationBellView({ count, items }) {
  const shown = count >= LIMIT ? `${LIMIT}+` : String(count ?? 0);
  const label = count ? `Notifications: ${shown} approval${count === 1 ? "" : "s"} waiting` : "Notifications";
  return <details className="relative">
    <summary className={summary} aria-label={label} title={label}>
      <Bell />
      {count > 0 && <span aria-hidden="true" className="absolute -right-1.5 -top-1.5 grid h-5 min-w-5 place-items-center rounded-full bg-red-500 px-1 text-[11px] font-semibold leading-none text-white">{shown}</span>}
    </summary>
    <div className="absolute right-0 z-20 mt-2 w-72 rounded-xl border border-line bg-card p-1.5 shadow-2xl">
      {count === null ? <p className="px-3 py-2 text-sm text-muted">No notifications.</p> : count === 0
        ? <p className="px-3 py-2 text-sm text-muted">No approval is waiting for you.</p>
        : <>
          <p className="px-3 pt-2 text-sm text-ink">{shown} approval{count === 1 ? " is" : "s are"} waiting for you.</p>
          {items?.length > 0 && <ul className="mt-1">
            {items.slice(0, 5).map((a) => <li key={a.id}>
              <Link to={`/incidents/${encodeURIComponent(a.incident_id)}`} onClick={closeMenu} className="block rounded-lg px-3 py-2 hover:bg-ink/5">
                <span className="font-mono text-sm">{a.capability}</span>
                <span className="block break-all text-xs text-muted">{a.target} · {a.risk} risk{a.verdict === "doubt" ? " · judge doubted" : ""}</span>
              </Link>
            </li>)}
          </ul>}
          <Link to="/actions" onClick={closeMenu} className="mt-1 block rounded-lg px-3 py-2 text-sm text-accent-hover hover:bg-ink/5">Open Actions to decide →</Link>
        </>}
    </div>
  </details>;
}

export default function NotificationBell() {
  const { user } = useAuth();
  const { count, items } = useWaitingApprovals(user);
  return <NotificationBellView count={count} items={items} />;
}
