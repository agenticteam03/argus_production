import { loadLevel, worstLevel } from "./load.js";

// The Dashboard's status banner, computed from what the UI already reads: the overview (latest incidents, host
// metrics) and, when the route answers, the topology. Nothing here is invented: a signal that is missing is reported
// as missing, and "unknown" is never counted as healthy.
export const STALE_MS = 2 * 60 * 1000; // a host sample older than this means its signals stopped (the poll is 30 s)
const DAY_MS = 24 * 60 * 60 * 1000;
const METRICS = [["CPU", "cpu_busy_ratio"], ["Memory", "memory_used_ratio"], ["Disk /", "disk_used_ratio"]];
const WORD = { critical: "critical", high: "high" };

export function ageLabel(ms) {
  if (ms == null) return null;
  const s = Math.round(ms / 1000);
  return s < 60 ? `${s} s ago` : s < 3600 ? `${Math.round(s / 60)} min ago` : `${Math.round(s / 3600)} h ago`;
}

// Health of one map component, for the honeycomb: broken link -> failed; unknown/missing status -> unknown; a running
// component -> ok; anything else (exited, restarting...) -> degraded.
export function nodeHealth(node, brokenIds = new Set()) {
  if (brokenIds.has(node.id)) return "failed";
  if (!node.status || node.status === "unknown") return "unknown";
  return ["running", "healthy", "ok"].includes(node.status) ? "ok" : "degraded";
}

// What a component is, for its icon in the honeycomb: a database, a host, or (by default) a container.
export function nodeIcon(node) {
  const name = `${node.kind ?? ""} ${node.label ?? ""} ${node.id ?? ""}`;
  if (node.kind === "database" || /\b(db|database|postgres(ql)?|mysql|mariadb|redis|mongo\w*)\b/i.test(name)) return "database";
  if (node.kind === "host" || /\/host:/.test(String(node.target ?? node.id ?? ""))) return "server";
  return "box";
}

export function fleetStatus({ incidents = [], hostMetrics = [], topology = null, hosts = {}, now = Date.now(), loaded = true }) {
  if (!loaded) {
    return { level: "checking", headline: "Checking the infrastructure…", detail: "Waiting for the first reading.", attention: [], counts: { critical: 0, warning: 0, running: 0 }, hosts: [], stats: null, nodes: [] };
  }

  const attention = [];
  const beats = Object.entries(hosts).map(([host, label]) => {
    const row = hostMetrics.find((r) => r.host === host);
    const at = row?.observed_at ? Date.parse(row.observed_at) : null;
    const ageMs = Number.isFinite(at) ? Math.max(0, now - at) : null;
    const available = Boolean(row?.available);
    const stale = available && ageMs != null && ageMs > STALE_MS;
    const levels = METRICS.map(([, key]) => loadLevel(row?.values?.[key]));
    return { host, label, available, stale, reporting: available && !stale, ageMs, age: ageLabel(ageMs), level: worstLevel(levels), levels, row };
  });

  for (const b of beats) {
    if (!b.available) attention.push({ tone: "warning", text: `${b.label} (${b.host}): no current metrics` });
    else if (b.stale) attention.push({ tone: "warning", text: `${b.label} (${b.host}): signals are stale, last sample ${b.age}` });
    if (b.level === "critical" || b.level === "high") {
      const worst = METRICS.map(([name, key], i) => ({ name, value: b.row.values[key], level: b.levels[i] }))
        .filter((m) => m.level === b.level).sort((a, c) => c.value - a.value)[0];
      attention.push({ tone: b.level === "critical" ? "critical" : "warning", text: `${b.label} (${b.host}): ${worst.name} ${WORD[b.level]} at ${(worst.value * 100).toFixed(1)}%` });
    }
  }

  const nodes = (topology?.nodes ?? []).filter((n) => n.kind !== "argus");
  const labelOf = Object.fromEntries((topology?.nodes ?? []).map((n) => [n.id, n.label]));
  const links = (topology?.edges ?? []).filter((e) => e.state !== "read");
  const broken = links.filter((e) => e.state === "broken");
  for (const e of broken) {
    attention.push({ tone: "critical", text: `Dependency broken: ${labelOf[e.from] ?? e.from} → ${labelOf[e.to] ?? e.to}${e.label ? ` (${e.label})` : ""}` });
  }

  const escalated = incidents.filter((i) => i.status === "escalated" && now - Date.parse(i.opened_at) <= DAY_MS);
  for (const i of escalated) attention.push({ tone: "warning", text: `Escalated to a person: ${i.target}`, to: `/incidents/${i.id}` });

  const counts = {
    critical: attention.filter((a) => a.tone === "critical").length,
    warning: attention.filter((a) => a.tone === "warning").length,
    running: incidents.filter((i) => i.status === "queued" || i.status === "running").length,
  };
  const level = counts.critical ? "critical" : counts.warning ? "warn" : "good";
  const total = counts.critical + counts.warning;

  const brokenIds = new Set(broken.flatMap((e) => [e.from, e.to]));
  const stats = {
    running: counts.running,
    escalated: escalated.length,
    hostsReporting: beats.filter((b) => b.reporting).length,
    hostsTotal: beats.length,
    links: topology ? { ok: links.filter((e) => (e.state ?? "ok") === "ok").length, total: links.length } : null,
    components: topology ? { total: nodes.length, unknown: nodes.filter((n) => nodeHealth(n) === "unknown").length } : null,
  };

  return {
    level,
    headline: level === "good" ? "All monitored hosts look healthy" : `${total} ${total === 1 ? "issue needs" : "issues need"} your attention`,
    detail: level === "good"
      ? `Host metrics are within limits${topology ? ", checked links are OK" : ""} and nothing was escalated to a person in the last 24 h.`
      : level === "critical" ? "Something is failing right now." : "Nothing is down, but it is worth a look.",
    attention, counts, hosts: beats, stats,
    nodes: nodes.map((n) => ({ id: n.id, label: n.label, icon: nodeIcon(n), health: nodeHealth(n, brokenIds) })),
  };
}
