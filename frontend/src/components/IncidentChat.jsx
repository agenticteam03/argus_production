import { useEffect, useRef, useState } from "react";
import { answerAboutIncident, SUGGESTIONS } from "../utils/incidentAnswer.js";
import { Card, Send } from "./ui.jsx";

// A small "ask about this incident" box. Answers come from the incident's own data (utils/incidentAnswer.js): no model,
// no request, nothing sent anywhere. Key it on the incident id so a new incident starts a fresh conversation.
export default function IncidentChat({ incident, events, cited }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const listRef = useRef(null);

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const ask = (text) => {
    const question = text.trim();
    if (!question) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: question }, { role: "agent", text: answerAboutIncident(question, { incident, events, cited }) }]);
  };

  return (
    <Card title="Ask about this incident" right={<span className="text-xs text-muted">Answers from this incident's data</span>}>
      <div ref={listRef} aria-live="polite" className="h-44 space-y-2 overflow-y-auto rounded-xl bg-field p-3">
        {messages.length === 0 ? (
          <div className="grid h-full place-items-center">
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" onClick={() => ask(s)} className="cursor-pointer rounded-full border border-line px-3 py-1.5 text-xs text-muted transition hover:border-accent/50 hover:text-ink motion-reduce:transition-none">{s}</button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m, i) => (
            <div key={i} className={m.role === "user" ? "flex justify-end" : ""}>
              <p className={`max-w-[90%] whitespace-pre-line rounded-xl px-3 py-2 text-sm ${m.role === "user" ? "bg-ink/5" : "text-body"}`}>{m.text}</p>
            </div>
          ))
        )}
      </div>
      <form onSubmit={(e) => { e.preventDefault(); ask(input); }} className="mt-2 flex gap-2">
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about this incident…" aria-label="Question about this incident"
          className="h-10 min-w-0 flex-1 rounded-[10px] border border-field-line bg-field px-3 text-sm outline-none transition placeholder:text-faint focus:border-accent focus:ring-[3px] focus:ring-accent/20" />
        <button type="submit" disabled={!input.trim()} aria-label="Send question"
          className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-[10px] bg-accent-solid px-3.5 text-sm font-medium text-white transition enabled:hover:bg-accent-solid-hover disabled:cursor-not-allowed disabled:bg-disabled disabled:text-faint">
          Send <Send width="15" height="15" />
        </button>
      </form>
      {messages.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {SUGGESTIONS.map((s) => (
            <button key={s} type="button" onClick={() => ask(s)} className="cursor-pointer rounded-full border border-line px-2.5 py-1 text-[11px] text-muted transition hover:text-ink motion-reduce:transition-none">{s}</button>
          ))}
        </div>
      )}
    </Card>
  );
}
