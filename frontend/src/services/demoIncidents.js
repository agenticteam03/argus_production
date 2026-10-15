// DEMO ONLY — temporary fixtures. Delete this file with the mock adapters once the HTTP adapter exists.
// Shaped exactly like the incident contract: GET /api/v1/incidents, /incidents/{id}, /incidents/{id}/events.
// The "running" incident progresses by itself (1 event / 3 s) once its timeline is opened, so polling is visible.

const ago = (min, sec = 0) => new Date(Date.now() - (min * 60 + sec) * 1000).toISOString();
const hash = (c) => c.repeat(64);
const events = (id, startMin, steps) =>
  steps.map(([node, phase, data = {}], i) => ({ incident_id: id, seq: i + 1, at: ago(startMin, -i * 4), node, phase, data }));
const evidence = (id, i, kind, capability, target, minAgo, model_text) => ({
  evidence_id: `ev_${id.slice(-4).toLowerCase()}_${i}`, kind, capability, target, executor: "local", status: "ok",
  caller: "argus-agent", collected_at: ago(minAgo), source_time: ago(minAgo, 2), sha256: hash("abcdef0123456789"[i % 16]), model_text,
});
const audit = (minAgo, event, capability, evidence_id, detail) => ({
  at: ago(minAgo), event, capability, actor: "argus-agent", policy_rule: "read_only_allowed", evidence_id, detail,
});
const make = (o) => ({
  trigger_kind: "alert", request_kind: "check", reason: null, principal: "alertmanager", trigger_id: null, incident_class: null,
  strategy: null, status: "closed", outcome: null, diagnosis: null, confidence: null, root_cause_target: null, findings: [],
  closed_at: null, evidence: [], audit: [], ...o,
});

const evId = (id, i) => `ev_${id.slice(-4).toLowerCase()}_${i}`;
// One run of the agent, with the data the real events carry: the matched class, the runbooks it recalled (`passages`),
// who decided each step, the tool reads (with their evidence) and the record. Runbook ids here are demo ids:
// use ids that exist in your runbook library if you want the "Runbooks it read" links to open a real runbook.
const run = (id, o = {}) => {
  const { target = "lab-victim", cls = null, passages = ["RB-001"], root = target, confidence = 0.8, outcome = "diagnosed", proposal = false, cited = [] } = o;
  return [
    ["detect", "enter"], ["detect", "exit", { matched: true, class: cls }],
    ["evidence_pack", "enter"], ["evidence_pack", "exit", { items: 2 }],
    ["recall", "enter"], ["recall", "exit", { similar_incidents: 1, passages }],
    ["investigate", "enter"], ["investigate", "exit", { decision: "use_read_tools", decided_by: "rule" }],
    ["act", "enter"],
    ["act", "step", { capability: "get_container_status", target, status: "ok", evidence_id: evId(id, 1) }],
    ["act", "step", { capability: "get_memory_history", target, status: "ok", evidence_id: evId(id, 2) }],
    ["act", "exit"],
    ["investigate", "enter"], ["investigate", "exit", { decision: "conclude", decided_by: "rule", root_cause_target: root, confidence }],
    ...(proposal ? [["propose_action", "enter"], ["propose_action", "exit", { action: "restart_container" }]] : []),
    ["record", "enter"], ["record", "exit", { outcome, cited }],
  ];
};

const ID = { A: "01K7Z3M5Q8R2T4V6W9X1Y0B7CD", B: "01K7Z2H4N7P1S3U5V8W0X2Y9AE", C: "01K7Z0G3M6N9P2R4T7V1W8X5BF", D: "01K7YXF2K5M8N1Q3S6U9V4W7CG",
  E: "01K7YWE1J4K7M0P2R5T8U3V6DH", F: "01K7YTD0H3J6K9N1Q4S7T2U5EJ", G: "01K7YQC9G2H5J8M0P3R6S1T4FK", H: "01K7YNB8F1G4H7K9N2Q5R0S3GM" };

const A_RUNNING = make({
  id: ID.A, target: "lab-victim", reason: "Alert: container restarted 4 times in 10 minutes", trigger_id: "alert-7f3a",
  incident_class: "oom_restart_loop", strategy: "runbook", status: "running", opened_at: ago(1),
  evidence: [evidence(ID.A, 1, "container_status", "get_container_status", "lab-victim", 1, "`OOMKilled=true`, restart count 4, exit code 137."),
             evidence(ID.A, 2, "memory_history", "get_memory_history", "lab-victim", 1, "Memory climbed to the **512 MiB** limit within 90 s of each start.")],
  audit: [audit(1, "capability_allowed", "get_container_status", `ev_${ID.A.slice(-4).toLowerCase()}_1`, "Read-only capability allowed."),
          audit(1, "capability_allowed", "get_memory_history", `ev_${ID.A.slice(-4).toLowerCase()}_2`, "Read-only capability allowed.")],
});
const A_FINAL = { ...A_RUNNING, status: "closed", outcome: "diagnosed", closed_at: ago(0), root_cause_target: "lab-victim", confidence: 0.86,
  recommendation: "Raise the memory limit of **lab-victim** (512 MiB today) or fix the leak, then watch the restart count.",
  model_calls: 0, cited_evidence: [evId(ID.A, 1), evId(ID.A, 2)], ruled_out: ["Host memory pressure: host-t shows no matching spike"],
  diagnosis: "The container **lab-victim** is killed by the kernel OOM killer after reaching its memory limit.\n\n- Limit: 512 MiB\n- Restarts: 4 in 10 minutes\n- Pattern: memory grows until the kill, every start",
  findings: ["OOMKilled=true on the last 4 exits", "Memory reaches the limit about 90 seconds after start", "No similar spike on host-t, so it is not host pressure"] };
const LIVE_EVENTS = events(ID.A, 0.9, run(ID.A, { cls: "oom_restart_loop", confidence: 0.86, cited: [evId(ID.A, 1), evId(ID.A, 2)] }));

const B = make({ id: ID.B, target: "lab-victim", reason: "Alert: container restarted 3 times", trigger_id: "alert-6c21", incident_class: "oom_restart_loop",
  strategy: "runbook", outcome: "diagnosed", opened_at: ago(14), closed_at: ago(13), root_cause_target: "lab-victim", confidence: 0.91,
  recommendation: "Review the memory limit of lab-victim: the workload needs more than it is given.",
  model_calls: 0, cited_evidence: [evId(ID.B, 1)],
  diagnosis: "Memory limit too low for the workload. The process is OOM-killed shortly after start.",
  findings: ["OOMKilled=true", "Peak usage equals the configured limit"],
  evidence: [evidence(ID.B, 1, "container_status", "get_container_status", "lab-victim", 14, "OOMKilled=true, exit code 137."),
             evidence(ID.B, 2, "memory_history", "get_memory_history", "lab-victim", 14, "Usage hits the limit within two minutes of start.")],
  audit: [audit(14, "capability_allowed", "get_container_status", `ev_${ID.B.slice(-4).toLowerCase()}_1`, "Read-only capability allowed."),
          audit(13, "diagnosis_recorded", null, null, "Outcome: diagnosed.")] });
const C = make({ id: ID.C, target: "app-db", trigger_kind: "manual", request_kind: "report", reason: "Check intermittent connection timeouts", principal: "ana@argus.dev",
  incident_class: "connection_timeout", strategy: "triage", status: "escalated", outcome: "unsupported_escalated", opened_at: ago(55), closed_at: ago(53),
  findings: ["No runbook covers connection timeouts yet"] });
const D = make({ id: ID.D, target: "host-t", trigger_kind: "scheduled", principal: "argus-scheduler", reason: "Scheduled health check", outcome: "no_incident",
  opened_at: ago(180), closed_at: ago(179), diagnosis: "All checks passed. No incident detected." });
const E = make({ id: ID.E, target: "lab-victim", reason: "Alert: health check failed", trigger_id: "alert-5b10", incident_class: "health_check_failed", strategy: "runbook",
  status: "escalated", outcome: "no_action_escalated", opened_at: ago(300), closed_at: ago(297), root_cause_target: "app-db", confidence: 0.72,
  diagnosis: "The health check fails because **app-db** refuses connections. Restarting lab-victim would not help; an operator must act on app-db.",
  recommendation: "An operator should restore **app-db**; restarting lab-victim would not help.",
  model_calls: 0, cited_evidence: [evId(ID.E, 1)], ruled_out: ["lab-victim crash loop: the process is healthy", "Host pressure: no spike on host-t"],
  findings: ["Dependency app-db is unreachable", "lab-victim process is healthy"],
  evidence: [evidence(ID.E, 1, "connectivity", "check_connectivity", "lab-victim", 300, "TCP to app-db:5432 refused.")],
  audit: [audit(298, "action_proposed", "restart_container", null, "Restart blocked: dependency failure.")] });
const F = make({ id: ID.F, target: "host-t", trigger_kind: "scheduled", principal: "argus-scheduler", incident_class: "high_disk_usage", strategy: "triage",
  outcome: "undiagnosable", opened_at: ago(600), closed_at: ago(598), findings: ["Disk usage is high but the growing path could not be identified"] });
const G = make({ id: ID.G, target: "lab-victim", trigger_kind: "manual", request_kind: "check", principal: "sam@argus.dev", reason: "Restart lab-victim now",
  outcome: "refused", opened_at: ago(1500), closed_at: ago(1499), findings: ["Argus is read-only and cannot restart containers"] });
const H = make({ id: ID.H, target: "host-t", trigger_kind: "manual", principal: "ana@argus.dev", reason: "Check memory on host-t", status: "queued", opened_at: ago(0, 10) });

const EVENTS = { [ID.B]: events(ID.B, 14, run(ID.B, { cls: "oom_restart_loop", confidence: 0.91, cited: [evId(ID.B, 1)] })),
  [ID.C]: events(ID.C, 55, run(ID.C, { target: "app-db", cls: "connection_timeout", passages: [] }).slice(0, 6)), [ID.D]: events(ID.D, 180, [["detect", "enter"], ["detect", "exit", { matched: false }], ["record", "enter"], ["record", "exit"]]),
  [ID.E]: events(ID.E, 300, run(ID.E, { cls: "health_check_failed", passages: ["RB-002"], root: "app-db", confidence: 0.72, proposal: true, outcome: "no_action_escalated", cited: [evId(ID.E, 1)] })),
  [ID.F]: events(ID.F, 600, run(ID.F, { target: "host-t", cls: "high_disk_usage", passages: ["RB-004"], outcome: "undiagnosable" })), [ID.G]: events(ID.G, 1500, [["detect", "enter"], ["record", "enter"], ["record", "exit"]]), [ID.H]: [] };
const STATIC = { [ID.B]: B, [ID.C]: C, [ID.D]: D, [ID.E]: E, [ID.F]: F, [ID.G]: G, [ID.H]: H };
const ORDER = [ID.H, ID.A, ID.B, ID.C, ID.D, ID.E, ID.F, ID.G]; // newest first

let liveStart = null; // starts when someone opens the running incident's timeline
const liveCount = () => (liveStart === null ? 0 : Math.min(LIVE_EVENTS.length, Math.floor((Date.now() - liveStart) / 3000) + 1));

export const demoIncident = (id) => (id === ID.A ? (liveCount() === LIVE_EVENTS.length ? A_FINAL : A_RUNNING) : STATIC[id] ?? null);
export const demoEvents = (id) => {
  if (id !== ID.A) return EVENTS[id] ?? null;
  liveStart ??= Date.now();
  return LIVE_EVENTS.slice(0, liveCount());
};
export const demoList = () =>
  ORDER.map((id) => demoIncident(id)).map((i) => ({
    id: i.id, target: i.target, status: i.status, outcome: i.outcome, class: i.incident_class, strategy: i.strategy,
    opened_at: i.opened_at, root_cause_target: i.root_cause_target,
  }));

// The notifications the agent raises when it cannot conclude on its own, shaped exactly like
// GET /api/v1/escalations: { key, at, payload: { incident_id, target, outcome, route, diagnosis } }.
const escalation = (i) => ({
  key: `${i.id}:escalation`, at: i.closed_at ?? i.opened_at,
  payload: { incident_id: i.id, target: i.target, outcome: i.outcome, route: "channel:operators",
             diagnosis: i.diagnosis ?? "evidence pack collected; no diagnosis is claimed" },
});
export const demoEscalations = () =>
  ORDER.map((id) => demoIncident(id)).filter((i) => i.status === "escalated").map(escalation);

// One evidence record by id, shaped exactly like GET /api/v1/evidence/{id}.
export const demoEvidence = (evidence_id) =>
  ORDER.map((id) => demoIncident(id)).flatMap((i) => i.evidence ?? []).find((e) => e.evidence_id === evidence_id) ?? null;

// ---- Map and metrics (phases 4 and 5), demo only. Shaped like the proposed GET /api/v1/topology and
// GET /api/v1/incidents/{id}/metrics (see BACKEND-REQUESTS.md). `target` matches the demo incidents' targets.
export const demoTopology = () => ({
  hosts: [{ id: "host-a", label: "Host A · Argus", role: "argus" }, { id: "host-t", label: "Host T · monitored", role: "monitored" }],
  nodes: [
    { id: "argus-agent", host: "host-a", label: "argus-agent", sub: "agent", kind: "argus" },
    { id: "prometheus", host: "host-a", label: "prometheus", sub: "metrics", kind: "argus", info: [{ label: "Role", value: "Metrics source for Argus" }] },
    { id: "lab-victim", host: "host-t", label: "lab-victim", sub: "app container", target: "lab-victim", status: "restarting",
      info: [{ label: "Memory limit", value: "512 MiB" }, { label: "Depends on", value: "app-db" }] },
    { id: "app-db", host: "host-t", label: "app-db", sub: "database", target: "app-db", status: "refusing connections", info: [{ label: "Port", value: "5432" }] },
    { id: "host-t-node", host: "host-t", label: "host-t", sub: "host", target: "host-t" },
  ],
  edges: [
    { from: "lab-victim", to: "app-db", state: "broken", label: "connection refused" },
    { from: "argus-agent", to: "lab-victim", state: "read" },
    { from: "argus-agent", to: "host-t-node", state: "read" },
    { from: "argus-agent", to: "prometheus", state: "ok" },
  ],
});

const RANGE_MS = { "15m": 15 * 60000, "30m": 30 * 60000, "1h": 60 * 60000 };
export function demoMetrics(id, range = "30m") {
  const inc = demoIncident(id);
  if (!inc) return null;
  const span = RANGE_MS[range] ?? RANGE_MS["30m"];
  const to = (inc.closed_at ? Date.parse(inc.closed_at) : Date.now()) + 30000;
  const from = to - span;
  const opened = Date.parse(inc.opened_at);
  const n = Math.floor(span / 30000) + 1;
  const after = (t) => t >= opened;
  const series = (key, title, unit, f, extra = {}) => ({
    key, title, unit, ...extra,
    points: Array.from({ length: n }, (_, i) => { const t = from + i * 30000; return [new Date(t).toISOString(), f(t, i)]; }),
  });
  const wave = (i, base, amp) => Number((base + Math.sin(i / 3) * amp).toFixed(1));
  const cpu = series("cpu", "CPU busy", "%", (t, i) => (i % 17 === 5 ? null : wave(i, 22, 6))); // one gap: a missing sample is not zero
  let list;
  if (inc.target === "host-t") {
    const disk = inc.incident_class === "high_disk_usage";
    list = [cpu, series("mem", "Memory used", "%", (t, i) => wave(i, 58, 3)),
      series("disk", "Disk /", "%", (t) => (disk && after(t) ? 91 : 70), { fired: disk })];
  } else if (inc.incident_class === "oom_restart_loop") {
    list = [series("mem", "Memory (of limit)", "%", (t, i) => (after(t) ? 100 : wave(i, 45, 4)), { max: 100, fired: true }),
      series("restarts", "Restarts", "", (t) => (after(t) ? 4 : 0)), cpu];
  } else {
    list = [series("probe", "TCP to app-db", "", (t) => (after(t) ? 0 : 1), { max: 1, fired: true }),
      series("health", "Health check", "", (t) => (after(t) ? 0 : 1), { max: 1 }), cpu];
  }
  return { from: new Date(from).toISOString(), to: new Date(to).toISOString(), series: list };
}
