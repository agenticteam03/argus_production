// A deliberately small read-only grammar. The browser never sends free-form PromQL or an arbitrary host to Argus.
const HOSTS = [
  { pattern: /\b(?:host\s+a|vm[- ]?095)\b/i, host: "vm-095", label: "Host A" },
  { pattern: /\b(?:host\s+t|vm[- ]?166)\b/i, host: "vm-166", label: "Host T" },
];
const METRICS = [
  { pattern: /\b(?:memory|ram)\b/i, metric: "memory_used_ratio", label: "memory usage" },
  { pattern: /\bcpu\b/i, metric: "cpu_busy_ratio", label: "CPU usage" },
  { pattern: /\bdisk\b/i, metric: "disk_used_ratio", label: "disk usage" },
];

export function parseMetricQuestion(question) {
  if (/\b(?:investigate|diagnose|diagnostic)\b/i.test(question)) return null;
  const hosts = HOSTS.filter(({ pattern }) => pattern.test(question));
  const metrics = METRICS.filter(({ pattern }) => pattern.test(question));
  if (hosts.length !== 1 || metrics.length !== 1) return null;
  return { host: hosts[0].host, metric: metrics[0].metric, label: metrics[0].label };
}

export function parseInvestigationRequest(question) {
  if (!/^(?:investigate|diagnose)\s+(?:host\s+[at]|vm[- ]?(?:095|166))\.?$/i.test(question.trim())) return null;
  const hosts = HOSTS.filter(({ pattern }) => pattern.test(question));
  if (hosts.length !== 1) return null;
  return { target: `${hosts[0].host}/host:${hosts[0].host}`, label: hosts[0].label };
}

export function answerMetricQuestion(question, rows) {
  const parsed = parseMetricQuestion(question);
  if (!parsed) return "I can show current CPU, memory or disk usage for Host A or Host T. For a full diagnosis, use Start an investigation.";
  const row = rows.find(({ host }) => host === parsed.host);
  const value = row?.values?.[parsed.metric];
  const hostLabel = parsed.host === "vm-166" ? "Host T" : "Host A";
  if (!row?.available || !Number.isFinite(value)) return `No current ${parsed.label} data for ${hostLabel}. Try again when monitoring is available.`;
  return `${hostLabel} (${parsed.host}) ${parsed.label}: ${(value * 100).toFixed(1)}%. Sample: ${row.observed_at ?? "time unavailable"}.`;
}
