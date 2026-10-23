// What to say when POST /api/v1/investigations is refused (ACR-0012), shared by the dashboard form and the system
// map's drawer: the quota (429, with Retry-After), a role that may not start one (403), else the API's short reason
// when http.js kept it as `err.detail`, else a generic line.
export function investigationError(err) {
  if (err?.status === 429) {
    const min = err.retryAfter ? Math.max(1, Math.ceil(err.retryAfter / 60)) : null;
    return `Too many investigations right now${min ? `: try again in about ${min} min` : ""}.`;
  }
  if (err?.status === 403) return "Your account may not start investigations.";
  if (err?.detail) return `Could not start the investigation: ${err.detail.replace(/\.$/, "")}.`;
  return "Could not start the investigation. Please try again.";
}
