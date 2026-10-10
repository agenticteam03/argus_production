export const isActive = (status) => status === "queued" || status === "running";

export const timeAgo = (iso) => {
  const m = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
  return m < 1 ? "just now" : m < 60 ? `${m}m ago` : m < 1440 ? `${Math.round(m / 60)}h ago` : `${Math.round(m / 1440)}d ago`;
};

export const dateTime = (iso) => (iso ? new Date(iso).toLocaleString([], { dateStyle: "medium", timeStyle: "medium" }) : "—");
export const clock = (iso) => new Date(iso).toLocaleTimeString([], { hour12: false });
export const shortHash = (hash) => (hash ? `${hash.slice(0, 12)}…` : "—");

export const duration = (from, to) => {
  const s = Math.max(0, Math.round((new Date(to) - new Date(from)) / 1000));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h ? `${h}h ${m}m` : m ? `${m}m ${s % 60}s` : `${s}s`;
};
