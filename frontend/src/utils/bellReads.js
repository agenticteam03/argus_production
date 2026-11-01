// T-0016: which of the bell's waiting approvals (ACR-0042) this person has already seen, so the red badge counts only
// the new ones. An ordinary session knows only how many wait; a confirmed private session also knows which (their
// ids), so it can mark each one. Pure rules; NotificationBell.jsx keeps the state in this browser (localStorage).
export const NOTHING_SEEN = { count: 0, ids: [] };

export function unreadCount({ count, items }, seen) {
  if (Array.isArray(items)) return items.filter((a) => !seen.ids.includes(a.id)).length;
  return Math.max(0, (count ?? 0) - seen.count);
}

export const markAllRead = ({ count, items }) => ({ count: count ?? 0, ids: (items ?? []).map((a) => a.id) });

// One approval opened (`id`), or the summary line of an ordinary session (`id` null: what waits now is read).
export function markRead(seen, { count, items }, id) {
  if (!id || !Array.isArray(items)) return { ...seen, count: Math.max(seen.count, count ?? 0) };
  return { count: seen.count, ids: seen.ids.includes(id) ? seen.ids : [...seen.ids, id] };
}

// Decided approvals leave the list: forget them, so a new one later is unread again. When the private session first
// names the approvals, those already read by count (the oldest ones) count as read: the same approvals, not new ones.
export function reconcile(seen, { count, items }) {
  if (!Array.isArray(items)) return { count: Math.min(seen.count, count ?? 0), ids: seen.ids };
  const ids = seen.ids.filter((id) => items.some((a) => a.id === id));
  if (!seen.ids.length && seen.count > 0) {
    const byAge = [...items].sort((a, b) => String(a.expires_at ?? a.id).localeCompare(String(b.expires_at ?? b.id)));
    ids.push(...byAge.slice(0, seen.count).map((a) => a.id));
  }
  return { count: Math.min(seen.count, count ?? 0), ids };
}
