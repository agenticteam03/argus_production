export const isActive = (status) => status === "queued" || status === "running";

export const timeAgo = (iso) => {
  const m = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
  return m < 1 ? "just now" : m < 60 ? `${m}m ago` : m < 1440 ? `${Math.round(m / 60)}h ago` : `${Math.round(m / 1440)}d ago`;
};

export const dateTime = (iso) => (iso ? new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "medium" }) : "—");

// The "Live" pill: mock data is labelled as demo whatever the poll says, so it is never mistaken for a
// live deployment; otherwise it reflects whether the last request to the API actually succeeded.
export const liveLabel = (live, source) => (source === "demo" ? "Demo data" : live ? "Live" : "Reconnecting…");
export const clock = (iso) => new Date(iso).toLocaleTimeString([], { hour12: false });
export const shortHash = (hash) => (hash ? `${hash.slice(0, 12)}…` : "—");

export const duration = (from, to) => {
  const s = Math.max(0, Math.round((new Date(to) - new Date(from)) / 1000));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${m}m` : m ? `${m}m ${s % 60}s` : `${s}s`;
};

// An audit record's `detail` is a JSON object on the real API (AuditRecord.detail is a dict) but free text in the
// demo fixtures. Say how to render it instead of handing React a raw object, which it refuses to render and which
// (with no error boundary) would blank the whole page.
export const auditDetail = (detail) => {
  if (typeof detail === "string") return detail.trim() ? { kind: "text", text: detail } : { kind: "empty" };
  if (detail && typeof detail === "object") return Object.keys(detail).length ? { kind: "json", text: JSON.stringify(detail, null, 2) } : { kind: "empty" };
  return detail == null ? { kind: "empty" } : { kind: "text", text: String(detail) };
};
