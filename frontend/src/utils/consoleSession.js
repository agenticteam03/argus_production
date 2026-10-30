// CON-3 (ACR-0043): the operator console's terminal logic, outside the component so it is tested without a DOM.
// The API parses and runs commands (argus/console/); the UI only decides what stays local (`clear`, a cancelled
// confirmation) and how an answer is printed. Behaviour: brain/tasks/current/argus-console-mockup-spec.md §3-§4.

export const PROMPT = "argus$";
export const CONFIRM_PROMPT = "confirm>";
export const MAX_INPUT = 200;      // the parser's limit (argus/console/parser.py)

// Output is text only: a control character (ESC, BEL...) is shown as a replacement character, never interpreted.
// eslint-disable-next-line no-control-regex
export const printable = (text) => String(text ?? "").replace(/[\x00-\x1f\x7f]/g, "�");

// What Enter does with the input line. While a write waits for confirmation, only "yes" resends it with the
// confirmation; anything else cancels. A "yes" confirms the intent: the approval is the approvals route (ACR-0043).
export function planInput(raw, pending) {
  const text = String(raw ?? "").trim();
  if (pending) return text.toLowerCase() === "yes" ? { kind: "send", input: pending.input, confirmation: "yes" } : { kind: "cancel" };
  if (!text) return { kind: "empty" };
  if (text.toLowerCase() === "clear") return { kind: "clear" };
  return { kind: "send", input: text };
}

const FAILED = new Set(["rejected", "error"]);

// The lines an execute answer prints, and the pending confirmation it opens (or null).
export function resultLines(result) {
  const kind = FAILED.has(result?.status) ? "error" : "out";
  const lines = (result?.output ?? []).map((line) => ({ kind, text: printable(line) }));
  if (result?.status !== "needs_confirmation") return { lines, pending: null };
  if (result.prompt) lines.push({ kind: "prompt", text: printable(result.prompt) });
  return { lines, pending: { input: result.input } };
}

export function errorLine(err) {
  if (err?.status === 429) return err.retryAfter ? `too many commands, try again in ${err.retryAfter} s` : "too many commands, try again later";
  return `console unavailable: ${err?.message || "unknown error"}`;
}

// The screen when the console opens: a greeting and the incident's stored commands with their output.
export function seedLines(incidentId, entries = []) {
  const lines = [{ kind: "info", text: `Operator console for ${incidentId}. Type 'help' to see available commands.` }];
  for (const e of entries) lines.push({ kind: "input", text: printable(e.input) }, ...resultLines(e).lines);
  return lines;
}

// The inputs ↑/↓ walk through: this session's, then the stored ones, newest first, no repeat in a row.
export function historyInputs(entries = [], typed = []) {
  const all = [...entries.map((e) => e.input), ...typed].reverse();
  return all.filter((input, i) => input && input !== all[i - 1]);
}

// index -1 is the empty line below the newest input.
export function stepHistory(list, index, key) {
  if (!list.length) return { index: -1, value: "" };
  const next = key === "ArrowUp" ? Math.min(index + 1, list.length - 1) : Math.max(index - 1, -1);
  return { index: next, value: next === -1 ? "" : list[next] };
}

// Argus's analysis of a command, as the API sends it (CON-4). The UI never writes a comment of its own.
export function analysisView(analysis, now = Date.now()) {
  if (!analysis?.status) return null;
  switch (analysis.status) {
    case "waiting": {
      const left = Math.ceil((Date.parse(analysis.settle_until) - now) / 1000);
      return { tone: "neutral", text: left > 0 ? `Waiting for metrics to settle (${left} s)` : "Waiting for metrics to settle" };
    }
    case "analyzing":
      return { tone: "blue", text: "Argus is analysing the result" };
    case "done":
      return { tone: "green", text: printable(analysis.comment) };
    default:
      return { tone: "amber", text: `Analysis unavailable${analysis.reason ? `: ${printable(analysis.reason)}` : ""}` };
  }
}

export const STATUS_VIEW = {
  ok: ["OK", "green"],
  error: ["Error", "red"],
  rejected: ["Rejected", "amber"],
  needs_confirmation: ["Needs confirmation", "blue"],
};

// --- CON-5: Argus's suggestions -------------------------------------------------------------------------------------
// They come with Argus's analysis of a command (CON-4: `analysis.suggestion` = {command, command_id}, optional `id` and
// `rationale`). The UI shows only registry commands, never runs one, and tags a run of an unedited insert with its id.

// eslint-disable-next-line no-control-regex
const SHELL_SYNTAX = /[;&|<>$`(){}[\]\\"'*?!~#\x00-\x1f\x7f]|\.\.|\//;

// `text` is a command of the catalog with the argument shape its usage allows (`<service>`, `[--since HH:MM]`).
export function isRegistryCommand(text, commands = []) {
  const value = String(text ?? "").trim().toLowerCase();
  if (!value || SHELL_SYNTAX.test(value)) return false;
  const tokens = value.split(/\s+/);
  return commands.some((c) => {
    const [base, optional] = String(c.usage ?? "").split(" [");
    const words = base.split(" ").filter((w) => !w.startsWith("<"));
    if (!words.every((w, i) => tokens[i] === w)) return false;
    const rest = tokens.slice(words.length);
    const service = base.includes("<service>") ? rest.shift() : null;
    if (base.includes("<service>") && !/^[a-z]+$/.test(service ?? "")) return false;
    if (optional?.startsWith("--since") && rest[0] === "--since") return rest.length === 2 && /^\d{2}:\d{2}$/.test(rest[1]);
    return rest.length === 0;
  });
}

// One card per suggested command, the newest first; the id is the API's, or one made from the command it follows.
export function suggestionsFrom(history = [], commands = []) {
  const seen = new Set();
  const out = [];
  for (const e of [...(history ?? [])].reverse()) {
    const s = e?.analysis?.suggestion;
    const command = typeof s === "string" ? s.trim() : String(s?.command ?? "").trim();
    if (!command || seen.has(command) || !isRegistryCommand(command, commands)) continue;
    seen.add(command);
    out.push({ id: s?.id ?? `sug-${e.command_id}`, command, rationale: s?.rationale ? printable(s.rationale) : null,
      after: printable(e.input) });
  }
  return out;
}

export const appliedIds = (history = []) => new Set((history ?? []).map((e) => e.suggestion_id).filter(Boolean));

// The suggestion id to send with a run: only when the input is exactly the inserted command (an edit makes it the
// operator's own command).
export const suggestionIdFor = (input, inserted) =>
  inserted && String(input ?? "").trim() === inserted.command ? inserted.id : undefined;
