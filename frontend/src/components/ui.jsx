import { Children, useCallback, useEffect, useId, useRef, useState } from "react";
import { clockZone, liveLabel } from "../utils/format.js";
import { countFrame, motionMs } from "../utils/motion.js";
import { runRefresh } from "../utils/refresh.js";

const icon = (paths) => (props) => (
  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths}</svg>
);
export const Bell = icon(<><path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10.3 21a1.9 1.9 0 0 0 3.4 0" /></>);
// The Argus mark (traced from argus-logo.png) as an inline SVG. It is filled with `currentColor`, so it follows the
// theme: white on dark, dark on light. The viewBox is cropped to the mark.
export const Logo = (props) => (
  <svg viewBox="26 52 176 162" fill="currentColor" aria-hidden="true" {...props}>
    <path d="M27 84.5H180.5L200.5 52.5H47Z" />
    <path d="M26.5 101.5 98 213.5 119.5 180 89 133.5H148.5L169.5 101.5Z" />
  </svg>
);
export const Box = icon(<><path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" /><path d="m3.3 7 8.7 5 8.7-5M12 22V12" /></>);
export const Database = icon(<><ellipse cx="12" cy="5" rx="9" ry="3" /><path d="M3 5v14a9 3 0 0 0 18 0V5M3 12a9 3 0 0 0 18 0" /></>);
export const Server = icon(<><rect width="20" height="8" x="2" y="2" rx="2" /><rect width="20" height="8" x="2" y="14" rx="2" /><path d="M6 6h.01M6 18h.01" /></>);
export const Chevron = icon(<path d="m6 9 6 6 6-6" />);
export const Refresh = icon(<><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" /><path d="M21 3v5h-5" /><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" /><path d="M8 16H3v5" /></>);
export const Sun = icon(<><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" /></>);
export const Moon = icon(<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />);
export const CircleCheck = icon(<><circle cx="12" cy="12" r="10" /><path d="m9 12 2 2 4-4" /></>);
export const CircleAlert = icon(<><circle cx="12" cy="12" r="10" /><path d="M12 8v4m0 4h.01" /></>);
export const Radio = icon(<><circle cx="12" cy="12" r="2" /><path d="M4.9 19.1C1 15.2 1 8.8 4.9 4.9M7.8 16.2c-2.3-2.3-2.3-6.1 0-8.5m8.4 0c2.3 2.3 2.3 6.1 0 8.5M19.1 4.9C23 8.8 23 15.1 19.1 19" /></>);
export const Check = icon(<path d="m5 12.5 4.5 4.5L19 7.5" />);
export const Send = icon(<path d="m22 2-7 20-4-9-9-4Zm0 0L11 13" />);
export const Arrow = icon(<path d="M5 12h14m-6-6 6 6-6 6" />);
export const Inbox = icon(<path d="M22 12h-6l-2 3h-4l-2-3H2M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.7 4H7.3a2 2 0 0 0-1.8 1.1Z" />);
export const Shield = icon(<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />);
export const Crosshair = icon(<><circle cx="12" cy="12" r="9" /><path d="M22 12h-4M6 12H2M12 6V2m0 20v-4" /></>);
export const ZoomIn = icon(<><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3M11 8v6M8 11h6" /></>);
export const ZoomOut = icon(<><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3M8 11h6" /></>);
export const Scan = icon(<path d="M3 7V5a2 2 0 0 1 2-2h2m10 0h2a2 2 0 0 1 2 2v2m0 10v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2" />);
export const Info = icon(<><circle cx="12" cy="12" r="10" /><path d="M12 16v-4m0-4h.01" /></>);

export const Card = ({ title, count, right, className = "", children }) => (
  <section className={`rounded-2xl border border-line bg-card/80 p-4 ${className}`}>
    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 className="flex items-center gap-2 text-[15px] font-medium">
        {title}
        {/* keyed on the value, so a new count pops in (T-0016) */}
        {count != null && <span key={count} className="animate-pop rounded-md bg-ink/5 px-1.5 py-0.5 text-xs text-muted">{count}</span>}
      </h2>
      {right}
    </div>
    {children}
  </section>
);

export const Empty = ({ icon: Icon, title, text }) => (
  <div className="grid place-items-center rounded-xl border border-dashed border-line px-4 py-8 text-center">
    <Icon width="22" height="22" className="mb-2 text-muted" />
    <p className="text-sm font-medium">{title}</p>
    <p className="mt-1 max-w-xs text-[13px] text-muted">{text}</p>
  </div>
);

const STATUS = {
  open: ["Open", "bg-sky-400/10 text-sky-300"],
  in_progress: ["In progress", "bg-blue-400/10 text-blue-300"],
  awaiting_approval: ["Awaiting approval", "bg-amber-400/10 text-amber-300"],
  resolved: ["Resolved", "bg-emerald-400/10 text-emerald-300"],
  escalated: ["Escalated", "bg-red-400/10 text-red-300"],
  budget_exceeded: ["Budget exceeded", "bg-red-400/10 text-red-300"],
};
export const Badge = ({ status }) => {
  const [label, tone] = STATUS[status] ?? [status, "bg-ink/5 text-muted"];
  return <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${tone}`}>{label}</span>;
};

export const Book = icon(<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5v14ZM4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5" />);
export const Search = icon(<><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></>);
export const Warning = icon(<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0ZM12 9v4m0 4h.01" />);
export const Close = icon(<path d="M18 6 6 18M6 6l12 12" />);

// `source` ("demo"/"api") and `at` (the last successful refresh, ms) make the pill honest: demo data is
// labelled, and the clock next to "Live" ticks with each poll, so it is visibly live rather than decorative.
// The time is in the browser's zone, named (COT, EST, GMT+1...). With `onRefresh` a "Refresh" button sits next to the pill: it reads again right
// now instead of waiting for the next 30 s poll, spins for at least a moment (utils/refresh.js) and then says in a
// toast whether the data was refreshed or not.
export function LivePill({ live, source, at, onRefresh }) {
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState(null);
  const hideToast = useCallback(() => setToast(null), []);
  const demo = source === "demo";
  const dot = demo ? "bg-amber-400" : live ? "animate-pulse bg-emerald-400 motion-reduce:animate-none" : "bg-amber-400";
  const pill = (
    <span className="inline-flex items-center gap-2 rounded-full border border-line bg-card px-3 py-1.5 text-xs text-muted">
      <span className={`size-2 rounded-full ${dot}`} />
      {liveLabel(live, source)}
      {at != null && <span className="text-muted">· updated {clockZone(at)}</span>}
    </span>
  );
  if (!onRefresh) return pill;
  const refresh = async () => {
    setBusy(true);
    setToast(null);
    const ok = await runRefresh(onRefresh);
    setBusy(false);
    setToast(ok
      ? { tone: "ok", text: `Data refreshed · ${clockZone(Date.now())}` }
      : { tone: "error", text: "Couldn't refresh. Showing the last data; it retries on its own." });
  };
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      {pill}
      <button type="button" onClick={refresh} disabled={busy} aria-label="Refresh now"
        className="inline-flex cursor-pointer items-center gap-1.5 rounded-full border border-line bg-card px-3 py-1.5 text-xs text-muted transition hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-hover disabled:cursor-wait motion-reduce:transition-none">
        <Refresh width="13" height="13" className={busy ? "animate-spin motion-reduce:animate-none" : ""} />
        {busy ? "Refreshing…" : "Refresh"}
      </button>
      {toast && <Toast key={toast.text} tone={toast.tone} onDone={hideToast}>{toast.text}</Toast>}
    </span>
  );
}

// A short message at the bottom of the screen that goes away by itself (as in the ui-graphs prototype). T-0016: it
// slides back down just before it goes (motion.css .toast-out; instant with reduced motion).
const TOAST_OUT_MS = 160;
export function Toast({ tone = "ok", onDone, ms = 4000, children }) {
  const [leaving, setLeaving] = useState(false);
  useEffect(() => {
    const out = setTimeout(() => setLeaving(true), Math.max(0, ms - TOAST_OUT_MS));
    const timer = setTimeout(onDone, ms);
    return () => { clearTimeout(out); clearTimeout(timer); };
  }, [onDone, ms]);
  const Icon = tone === "ok" ? CircleCheck : CircleAlert;
  return (
    <div role="status" aria-live="polite"
      className={`${leaving ? "toast-out" : "toast-in"} fixed bottom-6 left-1/2 z-50 flex max-w-[calc(100vw-32px)] -translate-x-1/2 items-center gap-2.5 rounded-xl border border-line bg-card px-4 py-3 text-sm text-ink shadow-[0_16px_48px_-12px_rgb(0_0_0/0.35)]`}>
      <Icon width="16" height="16" className={`shrink-0 ${tone === "ok" ? "text-emerald-400" : "text-red-400"}`} />
      {children}
    </div>
  );
}

// A term with an explanation: the help cursor (the arrow with the small "?") on hover, and the text in a tooltip on
// hover or keyboard focus. Text only, never HTML. The tooltip is `hidden` (not just transparent) until shown, so near
// the edge of the screen it never widens the page.
export function Hint({ text, children, align = "right", className = "" }) {
  const id = useId();
  return (
    <span tabIndex={0} aria-describedby={id}
      className={`group/hint relative inline-flex cursor-help rounded-full focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent-hover ${className}`}>
      {children}
      <span role="tooltip" id={id}
        className={`pointer-events-none absolute bottom-full z-40 mb-2 hidden w-64 max-w-[calc(100vw-2rem)] rounded-xl border border-line bg-card px-3 py-2.5 text-left text-[13px] font-normal normal-case leading-relaxed tracking-normal text-ink shadow-[0_16px_48px_-12px_rgb(0_0_0/0.35)] animate-fade-in group-hover/hint:block group-focus-visible/hint:block ${align === "right" ? "right-0" : "left-0"}`}>
        {text}
      </span>
    </span>
  );
}

export const Lock = icon(<><rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></>);

const TONES = {
  neutral: "border-line bg-ink/[0.03] text-muted",
  blue: "border-accent/30 bg-accent/10 text-accent-hover",
  green: "border-emerald-400/20 bg-emerald-400/10 text-emerald-300",
  amber: "border-amber-400/20 bg-amber-400/10 text-amber-300",
  red: "border-red-400/20 bg-red-400/10 text-red-300",
};
export const Pill = ({ tone = "neutral", pulse = false, children }) => (
  <span className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${TONES[tone]}`}>
    <span className={`size-1.5 rounded-full bg-current ${pulse ? "animate-pulse motion-reduce:animate-none" : ""}`} />
    {children}
  </span>
);

// Labels and tones derived from the documented status / outcome values.
export const STATUS_META = { queued: ["Queued", "neutral"], running: ["Running", "blue"], closed: ["Closed", "green"], escalated: ["Escalated", "amber"] };
export const OUTCOME_META = {
  diagnosed: ["Diagnosed", "green"],
  no_incident: ["No incident", "green"],
  undiagnosable: ["Undiagnosable", "amber"],
  unsupported_escalated: ["Unsupported (escalated)", "amber"],
  no_action_escalated: ["No action (escalated)", "amber"],
  refused: ["Refused", "red"],
};
export const StatusBadge = ({ status }) => {
  const [label, tone] = STATUS_META[status] ?? [status ?? "Unknown", "neutral"];
  return <Pill tone={tone} pulse={status === "running"}>{label}</Pill>;
};
export const OutcomeBadge = ({ outcome }) => {
  const [label, tone] = outcome == null ? ["No outcome yet", "neutral"] : OUTCOME_META[outcome] ?? [outcome, "neutral"];
  return <Pill tone={tone}>{label}</Pill>;
};

// A placeholder where content is loading: a calm block with a light sweeping across it (motion.css .skeleton). Hidden
// from screen readers: the busy region around it says "Loading …" in words.
export const Skeleton = ({ className = "" }) => <div aria-hidden="true" className={`skeleton rounded-xl ${className}`} />;

// Rows of skeletons in a busy region, while a list's first read is on its way (T-0016); `label` says it in words.
export const SkeletonList = ({ label, rows = 3, className = "h-[72px]", grid = "space-y-2" }) => (
  <div aria-busy="true" className={grid}>
    <span className="sr-only">{label}</span>
    {Array.from({ length: rows }, (_, n) => <Skeleton key={n} className={className} />)}
  </div>
);

// T-0016: a number that counts up to its value when it first shows and whenever it changes, over --motion-count
// (0 with reduced motion, and without a browser, so a server render and a test show the final value at once).
export function CountUp({ value, className = "" }) {
  const animated = Number.isFinite(value) && motionMs("count") > 0;
  const [shown, setShown] = useState(animated ? 0 : value);
  const from = useRef(shown);
  useEffect(() => {
    const ms = motionMs("count");
    if (!Number.isFinite(value) || !Number.isFinite(from.current) || ms <= 0 || from.current === value) {
      from.current = value;
      setShown(value);
      return undefined;
    }
    const start = from.current, t0 = performance.now();
    let frame;
    const tick = (t) => {
      const p = (t - t0) / ms;
      from.current = countFrame(start, value, p);
      setShown(from.current);
      if (p < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value]);
  return <span className={`tabular-nums ${className}`}>{shown}</span>;
}

export const ErrorCard = ({ title, text, onRetry, as: Heading = "h2", headingRef }) => (
  <div role="alert" className="animate-rise rounded-2xl border border-red-400/20 bg-red-400/5 p-5">
    <Heading ref={headingRef} tabIndex={-1} className="text-base font-semibold outline-none">{title}</Heading>
    <p className="mt-1 text-sm text-muted">{text}</p>
    {onRetry && (
      <button onClick={onRetry} className="mt-3 cursor-pointer rounded-lg border border-line px-3.5 py-2 text-sm transition hover:bg-ink/5">Retry</button>
    )}
  </div>
);

export const fieldClass =
  "h-11 rounded-[10px] border border-field-line bg-field px-3.5 text-sm outline-none transition placeholder:text-faint focus:border-accent focus:ring-[3px] focus:ring-accent/20";

export const textareaClass =
  "w-full resize-none overflow-y-auto rounded-[10px] border border-field-line bg-field px-3.5 py-2.5 text-sm leading-relaxed outline-none transition placeholder:text-faint focus:border-accent focus:ring-[3px] focus:ring-accent/20";

// Themed replacement for the native <select>, whose open list is drawn by the browser and cannot be styled.
// Same API as before: <option> children, `value`, and `onChange` called with { target: { value } }.
export function Select({ children, value, onChange, className = "", required, ...rest }) {
  const options = Children.toArray(children)
    .filter((c) => c?.props)
    .map((c) => ({ value: String(c.props.value ?? ""), label: Children.toArray(c.props.children).join("") }));
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const root = useRef(null);
  const button = useRef(null);
  const list = useRef(null);
  const listId = useId();
  const selected = options.findIndex((o) => o.value === String(value ?? ""));
  const current = options[selected] ?? options[0];

  useEffect(() => {
    if (!open) return undefined;
    const close = (e) => !root.current?.contains(e.target) && setOpen(false);
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  useEffect(() => {
    if (open) list.current?.children[active]?.scrollIntoView({ block: "nearest" });
  }, [open, active]);

  const show = () => { setActive(Math.max(selected, 0)); setOpen(true); };
  const choose = (i) => {
    onChange?.({ target: { value: options[i].value } });
    setOpen(false);
    button.current?.focus();
  };
  const move = (next) => setActive(Math.min(options.length - 1, Math.max(0, next)));

  const onKeyDown = (e) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!open) show();
      else move(active + (e.key === "ArrowDown" ? 1 : -1));
    } else if (open && (e.key === "Home" || e.key === "End")) {
      e.preventDefault();
      move(e.key === "Home" ? 0 : options.length - 1);
    } else if (open && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      choose(active);
    } else if (open && e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
    } else if (e.key === "Tab") {
      setOpen(false);
    }
  };

  return (
    <div ref={root} onBlur={(e) => open && !root.current?.contains(e.relatedTarget) && setOpen(false)} className={`relative inline-block max-w-full ${className}`}>
      <button
        {...rest}
        ref={button}
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        aria-activedescendant={open ? `${listId}-${active}` : undefined}
        aria-required={required || undefined}
        onClick={() => (open ? setOpen(false) : show())}
        onKeyDown={onKeyDown}
        className={`${fieldClass} inline-flex w-full min-w-44 cursor-pointer items-center justify-between gap-3 text-left disabled:cursor-not-allowed disabled:opacity-50 ${open ? "border-accent ring-[3px] ring-accent/20" : "hover:border-field-hover"}`}
      >
        <span className="truncate">{current?.label}</span>
        <Chevron width="14" height="14" className={`shrink-0 text-muted transition-transform motion-reduce:transition-none ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <ul
          ref={list}
          id={listId}
          role="listbox"
          aria-label={rest["aria-label"]}
          onMouseDown={(e) => e.preventDefault()}
          className="absolute left-0 z-20 mt-2 max-h-64 w-max min-w-full origin-top animate-drop max-w-[min(22rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-line bg-card p-1.5 shadow-2xl"
        >
          {options.map((o, i) => (
            <li
              key={o.value}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === selected}
              onMouseEnter={() => setActive(i)}
              onClick={() => choose(i)}
              className={`flex cursor-pointer items-center justify-between gap-4 rounded-lg px-3 py-2 text-sm ${i === active ? "bg-ink/5" : ""} ${i === selected ? "font-medium text-ink" : "text-body"}`}
            >
              <span className="truncate">{o.label}</span>
              {i === selected && <Check width="15" height="15" className="shrink-0 text-accent-hover" />}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---- Primitives for the incident page (tabs, disclosure, segmented control, dialog, inset row, fact) ----

export const Fact = ({ label, children }) => (
  <div className="min-w-0">
    <dt className="text-xs text-muted">{label}</dt>
    <dd className="mt-0.5 break-words text-sm leading-snug text-body">{children ?? "—"}</dd>
  </div>
);

export const InsetRow = ({ as: Tag = "div", className = "", ...props }) => (
  <Tag className={`rounded-xl bg-field px-3 py-2 ${className}`} {...props} />
);

// Small pressed/unpressed button group (filters, ranges, Report/Check).
export function Segmented({ options, value, onChange, label, className = "" }) {
  return (
    <div role="group" aria-label={label} className={`inline-flex shrink-0 overflow-hidden rounded-lg border border-line ${className}`}>
      {options.map((o, i) => {
        const on = value === o.value;
        return (
          <button key={o.value} type="button" title={o.hint} aria-pressed={on} onClick={() => onChange(o.value)}
            className={`cursor-pointer px-2.5 py-1 text-xs transition focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent-hover motion-reduce:transition-none ${i > 0 ? "border-l border-line" : ""} ${on ? "bg-ink/5 text-ink" : "text-muted hover:text-ink"}`}>
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export const Disclosure = ({ summary, className = "", children }) => (
  <details className={`group ${className}`}>
    <summary className="flex w-fit cursor-pointer list-none items-center gap-1.5 text-[13px] text-muted hover:text-ink [&::-webkit-details-marker]:hidden">
      <Chevron width="14" height="14" className="-rotate-90 transition-transform group-open:rotate-0 motion-reduce:transition-none" />
      {summary}
    </summary>
    <div className="mt-2 group-open:animate-rise">{children}</div>
  </details>
);

// WAI-ARIA tabs: roving tabindex, Left/Right/Home/End. The caller owns the selected id (the URL on the incident page).
export function TabList({ tabs, value, onChange, label }) {
  const refs = useRef({});
  const onKeyDown = (e) => {
    const i = tabs.findIndex((t) => t.id === value);
    const next = { ArrowRight: (i + 1) % tabs.length, ArrowLeft: (i - 1 + tabs.length) % tabs.length, Home: 0, End: tabs.length - 1 }[e.key];
    if (next == null) return;
    e.preventDefault();
    onChange(tabs[next].id);
    refs.current[tabs[next].id]?.focus();
  };
  return (
    <div role="tablist" aria-label={label} onKeyDown={onKeyDown} className="flex gap-1 overflow-x-auto overflow-y-hidden border-b border-line [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      {tabs.map((t) => {
        const on = t.id === value;
        return (
          <button key={t.id} ref={(el) => { refs.current[t.id] = el; }} id={`tab-${t.id}`} role="tab" type="button" aria-selected={on} aria-controls={`panel-${t.id}`} tabIndex={on ? 0 : -1} onClick={() => onChange(t.id)}
            className={`flex shrink-0 cursor-pointer items-center gap-2 rounded-t-lg border-b-2 px-4 py-2.5 text-sm font-medium transition focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent-hover motion-reduce:transition-none ${on ? "border-accent bg-ink/[0.03] text-accent-hover" : "border-transparent text-muted hover:text-ink"}`}>
            {t.label}
            {t.count != null && <span key={t.count} className="animate-pop rounded-md bg-ink/5 px-1.5 py-0.5 text-xs font-normal text-muted">{t.count}</span>}
          </button>
        );
      })}
    </div>
  );
}

// A chosen panel fades in (T-0016): it is mounted only while its tab is selected, so each switch plays it again.
export const TabPanel = ({ id, value, className = "", children }) =>
  value === id ? <div role="tabpanel" id={`panel-${id}`} aria-labelledby={`tab-${id}`} className={`animate-fade-in ${className}`}>{children}</div> : null;

// Native <dialog>: the browser traps focus, handles Escape and gives focus back to the opener.
export function Dialog({ open, onClose, title, actions, children }) {
  const ref = useRef(null);
  const titleId = useId();
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog ref={ref} aria-labelledby={titleId} onClose={onClose} onClick={(e) => e.target === ref.current && onClose()}
      className="m-auto h-[min(80vh,52rem)] w-[min(62rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-line bg-card p-0 text-body backdrop:bg-scrim open:flex open:flex-col">
      <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
        <h2 id={titleId} className="text-[15px] font-medium text-ink">{title}</h2>
        {actions}
      </div>
      <div className="min-h-0 flex-1">{children}</div>
    </dialog>
  );
}
