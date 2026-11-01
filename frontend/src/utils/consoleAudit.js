// T-0016: the operator console's audit rows in plain words for the incident's Audit tab: who opened it and why, each
// command and its result, every refusal, and how the session ended. Text only; null for any other row.
const CLOSED = { disconnect: "disconnected", time_limit: "its 30-minute limit", signed_out: "signed out" };

export function consoleAuditLine({ event, detail } = {}) {
  const d = detail && typeof detail === "object" ? detail : {};
  switch (event) {
    case "console.session_opened": return d.reason ? `Opened the console · reason: ${d.reason}` : "Opened the console";
    case "console.session_closed": return `Closed the console: ${CLOSED[d.why] ?? d.why ?? "ended"}`;
    case "console.command": return `Ran ${d.command ?? "a command"}${d.cls ? ` (${d.cls})` : ""}${d.status ? ` · ${d.status}` : ""}`;
    case "console.refused": return `Refused input${d.reason ? ` · ${d.reason}` : ""}`;
    case "console.quota_refused": return `Read limit reached${d.quota ? ` (${d.quota})` : ""}${d.command ? ` · ${d.command}` : ""}`;
    case "console.budget_refused": return `This incident's read budget is used${d.command ? ` · ${d.command}` : ""}`;
    case "security.console_refused": return `Console refused${d.reason ? ` · ${d.reason}` : ""}`;
    default: return null;
  }
}
