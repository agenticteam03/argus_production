import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext.jsx";
import { ROLES, ROLE_INFO } from "../routes.js";
import { argus } from "../services/index.js";
import { parseInvestigationRequest } from "../services/metricQuestion.js";
import { Card, Send } from "./ui.jsx";

const SUGGESTIONS = ["Check Host T memory usage", "Investigate Host T"];

export default function AgentChat() {
  const { user } = useAuth();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState("");
  const listRef = useRef(null);

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, status]);

  async function send(text = input) {
    const question = text.trim();
    if (!question || status) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: question }]);
    setStatus(parseInvestigationRequest(question) ? "Starting investigation…" : "Reading host metrics…");
    try {
      const reply = await argus.askAgent(question, user.actions?.includes("start_investigation") ?? false);
      setMessages((m) => [...m, { role: "agent", ...reply }]);
    } catch (err) {
      const text = err?.status === 429 ? "Investigation limit reached. Please try again later."
        : err?.status === 403 ? "Your account cannot start that investigation."
          : "Could not load the result. Please try again.";
      setMessages((m) => [...m, { role: "agent", text, error: true }]);
    } finally {
      setStatus("");
    }
  }

  return (
    <Card
      title="Argus Agent"
      right={
        <span title={ROLE_INFO[user.role]} className="rounded-full border border-accent/30 bg-accent/10 px-2.5 py-1 text-xs text-accent-hover">
          Role: {ROLES[user.role]}
        </span>
      }
    >
      <div ref={listRef} className="h-64 space-y-3 overflow-y-auto rounded-xl bg-field p-3">
        {messages.length === 0 && !status ? (
          <div className="grid h-full place-items-center text-center">
            <div>
              <p className="text-sm font-medium">Ask for a host metric or start an investigation</p>
              <div className="mt-3 flex flex-wrap justify-center gap-2">
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => setInput(s)} className="cursor-pointer rounded-full border border-line px-3 py-1.5 text-xs text-muted transition hover:border-accent/50 hover:text-white">
                    {s}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          messages.map((m, i) => (
            <div key={i} className={m.role === "user" ? "flex justify-end" : ""}>
              <div className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${m.role === "user" ? "bg-white/5" : m.error ? "text-danger" : "text-[#d6dbe6]"}`}>
                <p>{m.text}</p>
                {m.incidentId && <Link className="mt-1 block text-accent-hover underline" to={`/incidents/${encodeURIComponent(m.incidentId)}`}>Open incident</Link>}
              </div>
            </div>
          ))
        )}
        {status && (
          <p role="status" className="flex items-center gap-2 px-1 text-sm text-muted">
            <span className="flex gap-1" aria-hidden="true">
              {[0, 150, 300].map((d) => <span key={d} style={{ animationDelay: `${d}ms` }} className="size-1.5 animate-bounce rounded-full bg-accent motion-reduce:animate-none" />)}
            </span>
            {status}
          </p>
        )}
      </div>

      <form onSubmit={(e) => { e.preventDefault(); send(); }} className="mt-3 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Check Host T memory usage…"
          aria-label="Message for the agent"
          className="h-11 min-w-0 flex-1 rounded-[10px] border border-field-line bg-field px-3.5 text-sm outline-none transition placeholder:text-[#4b5363] focus:border-accent focus:ring-[3px] focus:ring-accent/20"
        />
        <button type="submit" disabled={!input.trim() || !!status} className="inline-flex h-11 cursor-pointer items-center gap-2 rounded-[10px] bg-accent-solid px-4 text-sm font-medium text-white transition enabled:hover:bg-accent-solid-hover disabled:cursor-not-allowed disabled:bg-[#10141b] disabled:text-[#4b5363]">
          Send <Send width="16" height="16" />
        </button>
      </form>
      <p className="mt-2 text-xs text-muted">{ROLE_INFO[user.role]}</p>
    </Card>
  );
}
