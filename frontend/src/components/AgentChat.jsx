import { useEffect, useRef, useState } from "react";
import { useAuth } from "../context/AuthContext.jsx";
import { ROLES, ROLE_INFO } from "../routes.js";
import { argus } from "../services/index.js";
import { Card, Send } from "./ui.jsx";

const SUGGESTIONS = ["Run a diagnostic on lab-victim", "Check Host T memory usage"];

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
    setStatus("Starting investigation…");
    try {
      const reply = await argus.askAgent(question, setStatus);
      setMessages((m) => [...m, { role: "agent", text: reply }]);
    } catch {
      setMessages((m) => [...m, { role: "agent", text: "Something went wrong. Please try again.", error: true }]);
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
              <p className="text-sm font-medium">Ask Argus to investigate a container or host</p>
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
              <p className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${m.role === "user" ? "bg-white/5" : m.error ? "text-danger" : "text-[#d6dbe6]"}`}>{m.text}</p>
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
          placeholder="Ask or instruct the agent…"
          aria-label="Message for the agent"
          className="h-11 min-w-0 flex-1 rounded-[10px] border border-field-line bg-field px-3.5 text-sm outline-none transition placeholder:text-[#4b5363] focus:border-accent focus:ring-[3px] focus:ring-accent/20"
        />
        <button type="submit" disabled={!input.trim() || !!status} className="inline-flex h-11 cursor-pointer items-center gap-2 rounded-[10px] bg-accent px-4 text-sm font-medium text-white transition enabled:hover:bg-accent-hover disabled:cursor-not-allowed disabled:bg-[#10141b] disabled:text-[#4b5363]">
          Send <Send width="16" height="16" />
        </button>
      </form>
      <p className="mt-2 text-xs text-muted">{ROLE_INFO[user.role]}</p>
    </Card>
  );
}
