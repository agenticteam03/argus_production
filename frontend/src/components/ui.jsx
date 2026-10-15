import { Children, useEffect, useId, useRef, useState } from "react";
import { clock, liveLabel } from "../utils/format.js";

const icon = (paths) => (props) => (
  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths}</svg>
);
export const Bell = icon(<><path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10.3 21a1.9 1.9 0 0 0 3.4 0" /></>);
export const Chevron = icon(<path d="m6 9 6 6 6-6" />);
export const Check = icon(<path d="m5 12.5 4.5 4.5L19 7.5" />);
export const Send = icon(<path d="m22 2-7 20-4-9-9-4Zm0 0L11 13" />);
export const Arrow = icon(<path d="M5 12h14m-6-6 6 6-6 6" />);
export const Inbox = icon(<path d="M22 12h-6l-2 3h-4l-2-3H2M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.7 4H7.3a2 2 0 0 0-1.8 1.1Z" />);
export const Shield = icon(<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z" />);

export const Card = ({ title, count, right, className = "", children }) => (
  <section className={`rounded-2xl border border-line bg-card/80 p-4 ${className}`}>
    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 className="flex items-center gap-2 text-[15px] font-medium">
        {title}
        {count != null && <span className="rounded-md bg-white/5 px-1.5 py-0.5 text-xs text-muted">{count}</span>}
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
  const [label, tone] = STATUS[status] ?? [status, "bg-white/5 text-muted"];
  return <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-medium ${tone}`}>{label}</span>;
};

export const Book = icon(<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5v14ZM4 19.5A2.5 2.5 0 0 0 6.5 22H20v-5" />);
export const Search = icon(<><circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" /></>);
export const Warning = icon(<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0ZM12 9v4m0 4h.01" />);
export const Close = icon(<path d="M18 6 6 18M6 6l12 12" />);

// `source` ("demo"/"api") and `at` (the last successful refresh, ms) make the pill honest: demo data is
// labelled, and the clock next to "Live" ticks with each poll, so it is visibly live rather than decorative.
export const LivePill = ({ live, source, at }) => {
  const demo = source === "demo";
  const dot = demo ? "bg-amber-400" : live ? "animate-pulse bg-emerald-400" : "bg-amber-400";
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-line bg-card px-3 py-1.5 text-xs text-muted">
      <span className={`size-2 rounded-full ${dot}`} />
      {liveLabel(live, source)}
      {at != null && <span className="text-muted/60">· updated {clock(at)}</span>}
    </span>
  );
};

export const Lock = icon(<><rect x="4" y="11" width="16" height="10" rx="2" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></>);

const TONES = {
  neutral: "border-line bg-white/[0.03] text-muted",
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

export const Skeleton = ({ className = "" }) => <div className={`animate-pulse rounded-xl bg-white/5 motion-reduce:animate-none ${className}`} />;

export const ErrorCard = ({ title, text, onRetry, as: Heading = "h2", headingRef }) => (
  <div role="alert" className="rounded-2xl border border-red-400/20 bg-red-400/5 p-5">
    <Heading ref={headingRef} tabIndex={-1} className="text-base font-semibold outline-none">{title}</Heading>
    <p className="mt-1 text-sm text-muted">{text}</p>
    {onRetry && (
      <button onClick={onRetry} className="mt-3 cursor-pointer rounded-lg border border-line px-3.5 py-2 text-sm transition hover:bg-white/5">Retry</button>
    )}
  </div>
);

export const fieldClass =
  "h-11 rounded-[10px] border border-field-line bg-field px-3.5 text-sm outline-none transition placeholder:text-[#4b5363] focus:border-accent focus:ring-[3px] focus:ring-accent/20";

export const textareaClass =
  "min-h-24 w-full resize-none overflow-y-auto rounded-[10px] border border-field-line bg-field px-3.5 py-3 text-sm leading-relaxed outline-none transition placeholder:text-[#4b5363] focus:border-accent focus:ring-[3px] focus:ring-accent/20";

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
        className={`${fieldClass} inline-flex w-full min-w-44 cursor-pointer items-center justify-between gap-3 text-left ${open ? "border-accent ring-[3px] ring-accent/20" : "hover:border-[#313a4b]"}`}
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
          className="absolute left-0 z-20 mt-2 max-h-64 w-max min-w-full max-w-[min(22rem,calc(100vw-2rem))] overflow-y-auto rounded-xl border border-line bg-card p-1.5 shadow-2xl"
        >
          {options.map((o, i) => (
            <li
              key={o.value}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === selected}
              onMouseEnter={() => setActive(i)}
              onClick={() => choose(i)}
              className={`flex cursor-pointer items-center justify-between gap-4 rounded-lg px-3 py-2 text-sm ${i === active ? "bg-white/5" : ""} ${i === selected ? "font-medium text-white" : "text-[#d6dbe6]"}`}
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
    <dd className="mt-0.5 break-words text-sm leading-snug text-[#d6dbe6]">{children ?? "—"}</dd>
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
            className={`cursor-pointer px-2.5 py-1 text-xs transition focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent-hover motion-reduce:transition-none ${i > 0 ? "border-l border-line" : ""} ${on ? "bg-white/5 text-white" : "text-muted hover:text-white"}`}>
            {o.label}
          </button>
        );
      })}
    </div>
  );
}

export const Disclosure = ({ summary, className = "", children }) => (
  <details className={`group ${className}`}>
    <summary className="flex w-fit cursor-pointer list-none items-center gap-1.5 text-[13px] text-muted hover:text-white [&::-webkit-details-marker]:hidden">
      <Chevron width="14" height="14" className="-rotate-90 transition-transform group-open:rotate-0 motion-reduce:transition-none" />
      {summary}
    </summary>
    <div className="mt-2">{children}</div>
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
            className={`flex shrink-0 cursor-pointer items-center gap-2 rounded-t-lg border-b-2 px-4 py-2.5 text-sm font-medium transition focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent-hover motion-reduce:transition-none ${on ? "border-accent bg-white/[0.03] text-accent-hover" : "border-transparent text-muted hover:text-white"}`}>
            {t.label}
            {t.count != null && <span className="rounded-md bg-white/5 px-1.5 py-0.5 text-xs font-normal text-muted">{t.count}</span>}
          </button>
        );
      })}
    </div>
  );
}

export const TabPanel = ({ id, value, className = "", children }) =>
  value === id ? <div role="tabpanel" id={`panel-${id}`} aria-labelledby={`tab-${id}`} className={className}>{children}</div> : null;

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
      className="m-auto h-[min(80vh,52rem)] w-[min(62rem,calc(100vw-2rem))] overflow-hidden rounded-2xl border border-line bg-card p-0 text-[#d6dbe6] backdrop:bg-black/70 open:flex open:flex-col">
      <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-3">
        <h2 id={titleId} className="text-[15px] font-medium text-white">{title}</h2>
        {actions}
      </div>
      <div className="min-h-0 flex-1">{children}</div>
    </dialog>
  );
}
