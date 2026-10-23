import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { copyText, downloadText } from "../utils/clipboard.js";
import { Dialog, Segmented } from "./ui.jsx";

const ghost = "cursor-pointer rounded-lg border border-line bg-field px-3 py-1.5 text-xs text-body transition hover:border-field-line hover:text-ink motion-reduce:transition-none";
const TOKEN = /("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g;

// Colours the pretty-printed JSON as React nodes (never as HTML), using the theme's own shades.
function highlight(text) {
  const out = [];
  let at = 0;
  let m;
  TOKEN.lastIndex = 0;
  while ((m = TOKEN.exec(text))) {
    if (m.index > at) out.push(text.slice(at, m.index));
    const [all, str, colon, word, num] = m;
    const tone = str ? (colon ? "text-accent-hover" : "text-emerald-300") : word || num ? "text-amber-300" : "";
    out.push(<span key={m.index} className={tone}>{str && colon ? str : all.replace(colon ?? "", "")}</span>);
    if (str && colon) out.push(colon);
    at = m.index + all.length;
  }
  out.push(text.slice(at));
  return out.map((n, i) => <Fragment key={i}>{n}</Fragment>);
}

// Parts mirror the API: a viewer's incident has no evidence/audit key, so those parts do not exist for them.
export default function RawOutputDialog({ open, onClose, incident, events }) {
  const [part, setPart] = useState("incident");
  const [copied, setCopied] = useState(false);
  const timer = useRef(null);
  useEffect(() => () => clearTimeout(timer.current), []);

  const parts = useMemo(() => {
    const { evidence, audit, ...rest } = incident;
    const list = [{ value: "incident", label: "Incident", data: rest }, { value: "events", label: `Events ${events.length}`, data: events }];
    if ("evidence" in incident) list.push({ value: "evidence", label: `Evidence ${evidence.length}`, data: evidence });
    if ("audit" in incident) list.push({ value: "audit", label: `Audit ${audit.length}`, data: audit });
    return list;
  }, [incident, events]);

  const current = parts.find((p) => p.value === part) ?? parts[0];
  const text = useMemo(() => JSON.stringify(current.data, null, 2), [current]);
  const everything = () => JSON.stringify(Object.fromEntries(parts.map((p) => [p.value, p.data])), null, 2);
  const fileName = `${String(incident.id).startsWith("inc_") ? "" : "inc_"}${incident.id}.json`;

  const copy = async () => {
    setCopied(await copyText(text));
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Raw output"
      actions={
        <>
          <Segmented label="Part" options={parts} value={current.value} onChange={setPart} />
          <div className="ml-auto flex gap-2">
            <button type="button" onClick={copy} className={ghost}><span aria-live="polite">{copied ? "Copied" : "Copy"}</span></button>
            <button type="button" onClick={() => downloadText(fileName, everything())} className={ghost}>Download .json</button>
            <button type="button" onClick={onClose} className={ghost}>Close</button>
          </div>
        </>
      }
    >
      <pre tabIndex={0} className="h-full overflow-auto whitespace-pre p-4 font-mono text-[13px] leading-relaxed text-body outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent-hover">{highlight(text)}</pre>
    </Dialog>
  );
}
