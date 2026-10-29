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
