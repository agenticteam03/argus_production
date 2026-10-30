import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { useWaitingApprovals } from "../hooks/useWaitingApprovals.js";
import { markAllRead, markRead, NOTHING_SEEN, reconcile, unreadCount } from "../utils/bellReads.js";
import { Bell } from "./ui.jsx";

const summary = "relative grid size-10 cursor-pointer list-none place-items-center rounded-xl border border-line bg-field text-muted hover:text-ink [&::-webkit-details-marker]:hidden";
const LIMIT = 50;                                            // the API counts at most 50
const closeMenu = (e) => e.currentTarget.closest("details")?.removeAttribute("open");
const dot = <span aria-label="Unread" className="size-2 shrink-0 rounded-full bg-accent" />;

// The header's bell (ACR-0042): how many approvals wait for this approver, and the way to them. The count carries
// nothing else; inside a confirmed private session `items` names each one (the private list). T-0016: the red badge
// counts only the unread ones (`unread`, `unreadIds`); opening one marks it read, and "Mark all as read" clears them.
export function NotificationBellView({ count, items, unread = count ?? 0, unreadIds = null, onRead, onReadAll }) {
  const shown = count >= LIMIT ? `${LIMIT}+` : String(count ?? 0);
  const badge = unread >= LIMIT ? `${LIMIT}+` : String(unread);
  const label = !count ? "Notifications"
    : unread === count ? `Notifications: ${shown} approval${count === 1 ? "" : "s"} waiting`
      : `Notifications: ${badge} unread of ${shown} approval${count === 1 ? "" : "s"} waiting`;
  const isUnread = (id) => (unreadIds ? unreadIds.includes(id) : unread > 0);
  return <details className="relative">
    <summary className={summary} aria-label={label} title={label}>
      <Bell />
      {unread > 0 && <span aria-hidden="true" className="absolute -right-1.5 -top-1.5 grid h-5 min-w-5 place-items-center rounded-full bg-red-500 px-1 text-[11px] font-semibold leading-none text-white">{badge}</span>}
    </summary>
    <div className="absolute right-0 z-20 mt-2 w-72 rounded-xl border border-line bg-card p-1.5 shadow-2xl">
      {count === null ? <p className="px-3 py-2 text-sm text-muted">No notifications.</p> : count === 0
        ? <p className="px-3 py-2 text-sm text-muted">No approval is waiting for you.</p>
        : <>
          <div className="flex items-baseline justify-between gap-2 px-3 pt-2">
            <p className="text-sm text-ink">{shown} approval{count === 1 ? " is" : "s are"} waiting for you.</p>
            {unread > 0 && <button type="button" onClick={onReadAll}
              className="shrink-0 cursor-pointer text-xs text-accent-hover hover:underline">Mark all as read</button>}
          </div>
          {items?.length > 0 && <ul className="mt-1">
            {items.slice(0, 5).map((a) => <li key={a.id}>
              <Link to={`/incidents/${encodeURIComponent(a.incident_id)}`} onClick={(e) => { onRead?.(a.id); closeMenu(e); }}
                className="flex items-start gap-2 rounded-lg px-3 py-2 hover:bg-ink/5">
                <span className="min-w-0 flex-1">
                  <span className="font-mono text-sm">{a.capability}</span>
                  <span className="block break-all text-xs text-muted">{a.target} · {a.risk} risk{a.verdict === "doubt" ? " · judge doubted" : ""}</span>
                </span>
                {isUnread(a.id) && <span className="mt-1.5">{dot}</span>}
              </Link>
            </li>)}
          </ul>}
          <Link to="/actions" onClick={(e) => { onRead?.(null); closeMenu(e); }}
            className="mt-1 flex items-center justify-between gap-2 rounded-lg px-3 py-2 text-sm text-accent-hover hover:bg-ink/5">
            Open Actions to decide →{!items?.length && unread > 0 && dot}
          </Link>
        </>}
    </div>
  </details>;
}

// What this person has seen, kept in this browser only (a convenience: a fresh browser shows them unread again).
const key = (name) => `argus.bell.seen.${name}`;
const load = (name) => {
  try { return { ...NOTHING_SEEN, ...JSON.parse(localStorage.getItem(key(name)) ?? "null") }; } catch { return NOTHING_SEEN; }
};
const save = (name, seen) => { try { localStorage.setItem(key(name), JSON.stringify(seen)); } catch { /* storage off */ } };

export default function NotificationBell() {
  const { user } = useAuth();
  const state = useWaitingApprovals(user);
  const name = user?.name ?? "";
  const [seen, setSeen] = useState(() => load(name));

  const update = useCallback((next) => { setSeen(next); save(name, next); }, [name]);
  // decided approvals leave the list: forget them, so a new one later shows as unread
  useEffect(() => {
    if (state.count === null) return;
    const next = reconcile(seen, state);
    if (next.count !== seen.count || next.ids.join() !== seen.ids.join()) update(next);
  }, [state, seen, update]);

  const unread = unreadCount(state, seen);
  const unreadIds = useMemo(() => (Array.isArray(state.items) ? state.items.filter((a) => !seen.ids.includes(a.id)).map((a) => a.id) : null),
    [state.items, seen.ids]);
  return <NotificationBellView count={state.count} items={state.items} unread={unread} unreadIds={unreadIds}
    onRead={(id) => update(markRead(seen, state, id))} onReadAll={() => update(markAllRead(state))} />;
}
