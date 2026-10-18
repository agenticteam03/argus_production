import { useEffect, useRef, useState } from "react";
import { copyText } from "../utils/clipboard.js";
import { summaryText } from "../utils/incidentView.js";

// Copies a plain-text summary (id, target, outcome, root cause, cited evidence) ready to paste in chat or a ticket.
export default function CopySummary({ incident, cited, className = "" }) {
  const [state, setState] = useState("idle");
  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);

  const copy = async () => {
    setState((await copyText(summaryText(incident, cited))) ? "done" : "failed");
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setState("idle"), 2000);
  };

  return (
    <button type="button" onClick={copy} className={className}>
      <span aria-live="polite">{state === "done" ? "Copied" : state === "failed" ? "Couldn't copy" : "Copy summary"}</span>
    </button>
  );
}
