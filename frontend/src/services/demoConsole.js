// CON-3: the offline demo of the console routes (mockArgusAdapter), shapes as in
// brain/tasks/current/argus-console-mockup-spec.md §5. The catalog mirrors argus/console/registry.py (CON-1) and the
// checks mirror argus/console/parser.py; the real answers come from the API once CON-2 adds the routes.

const c = (id, usage, cls, scenario, summary) => ({ id, usage, class: cls, scenario, summary });

const COMMANDS = [
  c("help", "help", "meta", "all", "List the commands"),
  c("clear", "clear", "meta", "all", "Clear the screen"),
  c("history", "history", "meta", "all", "Show the commands of this incident"),
  c("status", "status", "read", "all", "State and health of the lab services"),
  c("map", "map <service>", "read", "all", "Edges of a service with state and change time"),
  c("cache.status", "cache status", "read", "1", "State, since and health of the cache"),
  c("api.errors", "api errors [--since HH:MM]", "read", "1", "API error rate and types"),
  c("api.cpu", "api cpu [--since HH:MM]", "read", "1", "API CPU with its onset"),
  c("host.metrics", "host metrics", "read", "1", "CPU, memory, disk and load of the host"),
  c("cache.restart", "cache restart", "write", "1", "Bring the cache back (start, only while it is stopped)"),
  c("worker.status", "worker status", "read", "4", "State and health of the job worker"),
  c("worker.heartbeat", "worker heartbeat", "read", "4", "Time since the worker last processed a job"),
  c("worker.throughput", "worker throughput", "read", "4", "Jobs per minute"),
  c("queue.depth", "queue depth", "read", "4", "Queue depth and trend"),
  c("worker.restart", "worker restart", "write", "4", "Restart the job worker"),
  c("net.inspect", "net inspect <service>", "read", "2", "Networks a service is attached to"),
  c("net.expected", "net expected <service>", "read", "2", "Networks a service should be on"),
  c("net.diff", "net diff <service>", "read", "2", "Expected against actual networks"),
  c("net.reconnect", "net reconnect api", "write", "2", "Reconnect the API to its expected network"),
];

const SERVICES = ["api", "cache", "worker"];
// eslint-disable-next-line no-control-regex
const SHELL_SYNTAX = /[;&|<>$`(){}[\]\\"'*?!~#\x00-\x1f\x7f]|\.\.|\//;
const words = (usage) => usage.split(" [")[0].split(" ").filter((w) => !w.startsWith("<"));

// Demo outputs for the lab of the demo incidents (a stopped cache). Writes only report the proposal they create.
const WRITE_PAIR = {
  "cache.restart": "container.start on vm-166/container:argus-lab-cache",
  "worker.restart": "container.restart on vm-166/container:argus-lab-jobworker",
  "net.reconnect": "network.restore on vm-166/container:argus-lab-api",
};
const OUTPUT = {
  status: () => ["api      running   healthy", "cache    exited    -", "worker   running   healthy"],
  map: (s) => [`${s} -> cache   broken   since 10:41:58`, `client -> ${s}   ok`],
  "cache.status": () => ["cache: exited (code 137) since 10:41:58", "health: none (not running)"],
  "api.errors": () => ["5xx rate: 0.42/s (was 0.00/s before 10:42)", "top error: cache connection refused"],
  "api.cpu": () => ["cpu: 31 % of quota (no change at 10:42)", "onset: none in the window"],
  "host.metrics": () => ["cpu 22 %   memory 61 %   disk 48 %   load 0.41"],
  "worker.status": () => ["worker: running, healthy"],
  "worker.heartbeat": () => ["last job processed 4 s ago"],
  "worker.throughput": () => ["38 jobs/min (normal 30-45)"],
  "queue.depth": () => ["depth 3, flat"],
  "net.inspect": (s) => [`${s}: argus-lab-app`],
  "net.expected": (s) => [`${s}: argus-lab-app`],
  "net.diff": () => ["no difference"],
};

// CON-5 demo: Argus's analysis of some reads, in CON-4's shape (`suggestion` = {command, command_id}), with a rationale.
const ANALYSIS = {
  "cache.status": { status: "done", comment: "The cache has no samples and the API's link to it is broken; the API errors follow from it.",
    suggestion: { command: "cache restart", command_id: "cache.restart", rationale: "The cache is stopped and the API depends on it." } },
  "api.cpu": { status: "done", comment: "The API's CPU did not change when its errors began, so CPU is not the cause.",
    suggestion: { command: "cache status", command_id: "cache.status", rationale: "Check the API's dependency instead." } },
};

// CON-9 demo: one read per analysis failure (spec §8), so each error state and the re-check can be seen offline. A
// function gives the stuck analysis a settle time in the past, measured when the command runs.
const FAILING = {
  "api.errors": () => ({ status: "error", countdown_s: null, message: "Metrics not available yet", retryable: true }),
  "host.metrics": () => ({ status: "analyzing", settle_until: new Date(Date.now() - 120_000).toISOString() }),
  "worker.throughput": () => ({ status: "error", error: "Analysis could not be completed", retryable: true }),
};
const RECHECKED = {
  "api.errors": "The API's errors began at 10:42, when its link to the cache broke; they are a symptom, not the cause.",
  "host.metrics": "The host has spare CPU, memory and disk, so the host is not the cause.",
  "worker.throughput": "The worker's throughput is normal, so the job queue is not involved.",
};
const analysisOf = (id) => ANALYSIS[id] ?? FAILING[id]?.();
const retryable = (a) => a?.retryable === true || a?.status === "analyzing";

const store = new Map();
let seq = 0;
export const resetDemoConsole = () => { store.clear(); seq = 0; };

export const demoConsoleCommands = () => ({ commands: COMMANDS.map((x) => ({ ...x })) });
export const demoConsoleHistory = (incidentId) => ({ entries: [...(store.get(incidentId) ?? [])] });

function parse(input) {
  const bad = SHELL_SYNTAX.exec(input);
  if (bad) return { error: `syntax not allowed: ${bad[0]}. Only plain console commands are accepted; type 'help'.` };
  const tokens = input.toLowerCase().split(/\s+/).filter(Boolean);
  const command = COMMANDS
    .filter((x) => words(x.usage).every((w, i) => tokens[i] === w))
    .sort((a, b) => words(b.usage).length - words(a.usage).length)[0];
  if (!command) return { error: `command not found: ${tokens[0]}. Type 'help' to see available commands.` };
  const rest = tokens.slice(words(command.usage).length).filter((t, i, all) => t !== "--since" && all[i - 1] !== "--since");
  const service = command.usage.includes("<service>") ? rest.shift() : undefined;
  if (command.usage.includes("<service>") && !SERVICES.includes(service)) return { error: `unknown service: ${service ?? ""}. Known services: ${SERVICES.join(", ")}.` };
  if (rest.length) return { error: `unexpected argument: ${rest[0]}. usage: ${command.usage}` };
  return { command, service };
}

export function demoConsoleExecute(incidentId, { input, confirmation, suggestion_id } = {}, by = "operator") {
  const started = new Date().toISOString();
  const text = String(input ?? "").trim();
  const { command, service, error } = parse(text);
  const result = { command_id: `cmd_${++seq}`, input: text, command: command?.id ?? null, class: command?.class ?? null,
    started_at: started, finished_at: started };
  if (error) Object.assign(result, { status: "rejected", output: [error] });
  else if (command.class === "write" && confirmation !== "yes") {
    Object.assign(result, { status: "needs_confirmation", output: [],
      prompt: `${text} needs approval. Type 'yes' to propose it, anything else to cancel.` });
  } else if (command.class === "write") {
    Object.assign(result, { status: "ok", output: [`proposal created: ${WRITE_PAIR[command.id]}`, "waiting for an approver with a fresh second factor (Actions)"] });
  } else if (command.id === "help") {
    Object.assign(result, { status: "ok", output: ["Available commands:", ...COMMANDS.map((x) => `  ${x.usage.padEnd(28)}${x.summary}`)] });
  } else if (command.id === "history") {
    Object.assign(result, { status: "ok", output: (store.get(incidentId) ?? []).map((e) => e.input) });
  } else {
    Object.assign(result, { status: "ok", output: OUTPUT[command.id]?.(service) ?? [] });
  }
  if (result.status !== "needs_confirmation") {
    const stored = { ...result, by, ...(suggestion_id ? { suggestion_id } : {}), ...(analysisOf(command?.id) ? { analysis: analysisOf(command.id) } : {}) };
    store.set(incidentId, [...(store.get(incidentId) ?? []), stored]);
  }
  return result;
}

// CON-9: a manual re-check of a retryable analysis; the next history read carries the result.
export function demoConsoleRecheck(incidentId, commandId) {
  const entries = store.get(incidentId) ?? [];
  const entry = entries.find((e) => e.command_id === commandId);
  if (!entry) throw Object.assign(new Error(`command not found: ${commandId}`), { status: 404 });
  if (!retryable(entry.analysis)) throw Object.assign(new Error("this analysis is not retryable"), { status: 409 });
  const analysis = { status: "done", comment: RECHECKED[entry.command] ?? "The command's output gives no new evidence." };
  store.set(incidentId, entries.map((e) => (e === entry ? { ...e, analysis } : e)));
  return { command_id: commandId, analysis };
}
