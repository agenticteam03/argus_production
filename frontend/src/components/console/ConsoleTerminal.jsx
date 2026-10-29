import { useEffect, useRef, useState } from "react";
import { CONFIRM_PROMPT, errorLine, historyInputs, MAX_INPUT, planInput, printable, PROMPT, resultLines, seedLines, stepHistory } from "../../utils/consoleSession.js";

const TONE = { input: "text-ink", out: "text-body", error: "text-red-300", prompt: "text-amber-300", info: "text-muted" };

// CON-3: the terminal half of the operator console. A plain monospace log and one input line: the API parses and runs
// every command; only `clear` and a cancelled confirmation stay local (utils/consoleSession.js).
export default function ConsoleTerminal({ incidentId, history = [], run }) {
  const [lines, setLines] = useState(() => seedLines(incidentId, history));
  const [seeded, setSeeded] = useState(history.length > 0);
  const [input, setInput] = useState("");
  const [typed, setTyped] = useState([]);
  const [cursor, setCursor] = useState(-1);
  const [pending, setPending] = useState(null);
  const [busy, setBusy] = useState(false);
  const logRef = useRef(null);
  const inputRef = useRef(null);

  // The history usually arrives after the first render: replay it once, if nothing was typed yet.
  useEffect(() => {
    if (seeded || !history.length) return;
    setSeeded(true);
    setLines((now) => (now.length === 1 ? seedLines(incidentId, history) : now));
  }, [seeded, history, incidentId]);

  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines, busy]);

  useEffect(() => { if (!busy) inputRef.current?.focus({ preventScroll: true }); }, [busy]);

  const print = (...more) => setLines((now) => [...now, ...more]);

  const submit = async (e) => {
    e.preventDefault();
    if (busy) return;
    const raw = input;
    setInput("");
    setCursor(-1);
    const plan = planInput(raw, pending);
    print({ kind: "input", text: printable(raw), prompt: pending ? CONFIRM_PROMPT : PROMPT });
    if (plan.kind === "empty") return;
    if (plan.kind === "clear") { setLines([]); return; }
    if (plan.kind === "cancel") { setPending(null); print({ kind: "info", text: "cancelled" }); return; }
    if (!pending) setTyped((t) => [...t, plan.input]);
    setPending(null);
    setBusy(true);
    try {
      const result = await run({ input: plan.input, confirmation: plan.confirmation });
      const { lines: out, pending: next } = resultLines({ ...result, input: result?.input ?? plan.input });
      print(...out);
      setPending(next);
    } catch (err) {
      print({ kind: "error", text: errorLine(err) });
    } finally {
      setBusy(false);
    }
  };

  const onKeyDown = (e) => {
    if (e.key !== "ArrowUp" && e.key !== "ArrowDown") return;
    e.preventDefault();
    const step = stepHistory(historyInputs(history, typed), cursor, e.key);
    setCursor(step.index);
    setInput(step.value);
  };

  const prompt = pending ? CONFIRM_PROMPT : PROMPT;
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-line bg-field font-mono text-[13px]"
      onClick={() => inputRef.current?.focus()}>
      <div ref={logRef} role="log" aria-live="polite" aria-label="Console output" className="min-h-0 flex-1 overflow-y-auto p-3 leading-relaxed">
        {lines.map((l, i) => (
          <p key={i} className={`whitespace-pre-wrap break-all ${TONE[l.kind] ?? "text-body"}`}>
            {l.kind === "input" && <span className="select-none text-accent-hover">{l.prompt ?? PROMPT} </span>}
            {l.text}
          </p>
        ))}
        {busy && <p className="text-muted">running…</p>}
      </div>
      <form onSubmit={submit} className="flex items-center gap-2 border-t border-line px-3 py-2">
        <label htmlFor={`console-input-${incidentId}`} className="shrink-0 select-none text-accent-hover">{prompt}</label>
        <input id={`console-input-${incidentId}`} ref={inputRef} value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={onKeyDown}
          disabled={busy} maxLength={MAX_INPUT} autoComplete="off" autoCapitalize="off" spellCheck={false} aria-label="Console command"
          placeholder={pending ? "yes to propose, anything else to cancel" : "type 'help'"}
          className="h-8 min-w-0 flex-1 bg-transparent text-ink outline-none placeholder:text-faint disabled:cursor-wait" />
        <button type="submit" disabled={busy}
          className="h-8 cursor-pointer rounded-lg bg-accent-solid px-3 font-sans text-xs font-medium text-white transition enabled:hover:bg-accent-solid-hover disabled:cursor-wait disabled:bg-disabled disabled:text-faint motion-reduce:transition-none">
          Run
        </button>
      </form>
    </div>
  );
}
