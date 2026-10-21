export const isActive = (status) => status === "queued" || status === "running";

export const timeAgo = (iso) => {
  const m = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
  return m < 1 ? "just now" : m < 60 ? `${m}m ago` : m < 1440 ? `${Math.round(m / 60)}h ago` : `${Math.round(m / 1440)}d ago`;
};

// Times are shown in the browser's own time zone, always followed by the zone's name so nobody has to guess it.
// Intl only knows abbreviations for a few zones in English (EST, PDT, UTC...) and writes the rest as "GMT-5", so the
// zones the team is likely to use get their usual abbreviation here; any other zone shows its GMT offset.
const ZONE_ABBR = { "America/Bogota": "COT", "America/Lima": "PET", "America/Guayaquil": "ECT", "America/Caracas": "VET" };
export const browserTimeZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone;
export const zoneLabel = (iso, timeZone = browserTimeZone()) =>
  ZONE_ABBR[timeZone] ??
  new Intl.DateTimeFormat("en-US", { timeZone, timeZoneName: "short" }).formatToParts(new Date(iso)).find((p) => p.type === "timeZoneName")?.value ??
  timeZone;
export const dateTime = (iso, timeZone = browserTimeZone()) =>
  (iso ? `${new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "medium", timeZone })} ${zoneLabel(iso, timeZone)}` : "—");

// The "Live" pill: mock data is labelled as demo whatever the poll says, so it is never mistaken for a
// live deployment; otherwise it reflects whether the last request to the API actually succeeded.
export const liveLabel = (live, source) => (source === "demo" ? "Demo data" : live ? "Live" : "Reconnecting…");
export const clock = (iso, timeZone = browserTimeZone()) => new Date(iso).toLocaleTimeString([], { hour12: false, timeZone });
export const clockZone = (iso, timeZone = browserTimeZone()) => `${clock(iso, timeZone)} ${zoneLabel(iso, timeZone)}`;
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
