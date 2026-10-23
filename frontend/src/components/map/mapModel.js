// What the system map shows, as plain data (no DOM): each box's health, glyph, icon and incident role, each link's
// style and text. One source for the map, the node drawer and the mini map. Topology shape: docs/API-FOR-UI.md item 12
// (ACR-0017, ACR-0021); every field past id/host/label/status is optional.
import { incidentLevels, nodeHealth, nodeIcon } from "../../utils/fleetStatus.js";

// Link styles: a Tailwind stroke class, an SVG dash and the words. "unknown" is "Not checked", never OK (ACR-0017).
export const CONNECTIONS = {
  ok: { label: "Checked · OK", short: "OK", stroke: "stroke-emerald-400", text: "text-emerald-300", dash: undefined },
  slow: { label: "Slow", short: "Slow", stroke: "stroke-amber-400", text: "text-amber-300", dash: undefined },
  broken: { label: "Broken", short: "Broken", stroke: "stroke-red-400", text: "text-red-300", dash: "6 4" },
  not_checked: { label: "Not checked", short: "Not checked", stroke: "stroke-slate-500", text: "text-muted", dash: "2 5" },
  argus_reads: { label: "Argus reads", short: "Observation", stroke: "stroke-accent", text: "text-accent-hover", dash: "2 6" },
};
export const connectionOf = (edge) => (edge.kind === "argus_reads" || edge.state === "read" ? "argus_reads" : CONNECTIONS[edge.state] && edge.state !== "argus_reads" ? edge.state : "not_checked");

// The second line of a link's label: its reason when the API gives one, else its state (and latency when checked).
export function edgeDetail(edge) {
  if (edge.reason) return edge.reason;
  const c = connectionOf(edge);
  if ((c === "ok" || c === "slow") && edge.latency_ms != null) return `${CONNECTIONS[c].short} · ${edge.latency_ms} ms`;
  return CONNECTIONS[c].short;
}

export const ROLES = {
  root_cause: { label: "Root cause", tone: "red", help: "The component best supported by the evidence as the source of the incident." },
  affected: { label: "Affected", tone: "amber", help: "The component the incident was raised on." },
  on_path: { label: "On path", tone: "neutral", help: "A component between the affected one and the root cause." },
};

export const PROBLEM_LABELS = { memory: "Memory", cpu: "CPU", disk: "Disk", network: "Network", restarts: "Restarts", health: "Health check", database: "Database", config: "Config", stale_metrics: "Stale" };

const causeTarget = (incident) => incident?.root_cause_target ?? incident?.cause?.target ?? null;

// The incident overlay (operator/approver) sends each box's `role`; without it (a viewer) the UI marks the incident's
// target and root cause itself, from the incident it already has.
export function roleOf(node, incident) {
  if (node.role) return node.role;
  if (!incident) return null;
  if (causeTarget(incident) && node.target === causeTarget(incident)) return "root_cause";
  if (incident.target && node.target === incident.target) return "affected";
  return null;
}

// Node ids from the affected box to the root cause: the overlay's `cause_path`, else those two boxes.
export function causePathOf(topology, incident) {
  if (topology?.cause_path?.length) return topology.cause_path;
  if (!incident) return [];
  const idOf = (t) => (t ? topology?.nodes?.find((n) => n.target === t)?.id : null);
  return [idOf(incident.target), idOf(causeTarget(incident))].filter(Boolean);
}

// Every box with: `health` (fleetStatus nodeHealth: the API's health, made worse by problems and by an incident that
// still needs attention; not by its links: box and link health are checked apart, and a healthy box can have a broken
// dependency, which its link shows), `glyph` (the hexagon's tone: the root cause draws as failing, a healthy
// affected box as degraded), `icon` and `role`.
export function mapNodes(topology, { incidents = [], incident = null, now = Date.now() } = {}) {
  const levels = incidentLevels(incidents, now);
  return (topology?.nodes ?? []).map((n) => {
    const health = nodeHealth(n, { incident: levels.get(n.target) });
    const role = roleOf(n, incident);
    const glyph = role === "root_cause" ? "failed" : role === "affected" && health === "ok" ? "degraded" : health;
    // An idle scenario container with an incident that needs a look is not "expected": it leaves the idle group.
    return { ...n, health, glyph, role, icon: nodeIcon(n), idle: Boolean(n.idle) && health === "idle" && !role };
  });
}

// A drawer signal value: ratios as %, bytes as MiB, anything else as is.
export function fmtSignal(value, unit) {
  if (value == null) return "—";
  if (unit === "ratio") return `${(value * 100).toFixed(1)} %`;
  if (unit === "bytes") return `${(value / 1048576).toFixed(1)} MiB`;
  const v = Number.isInteger(value) ? String(value) : value.toFixed(Math.abs(value) >= 10 ? 1 : 2);
  return unit ? `${v} ${unit}` : v;
}
