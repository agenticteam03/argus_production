const icon = (paths) => (props) => (
  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>{paths}</svg>
);
export const Bell = icon(<><path d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" /><path d="M10.3 21a1.9 1.9 0 0 0 3.4 0" /></>);
export const Chevron = icon(<path d="m6 9 6 6 6-6" />);
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

export const LivePill = ({ live }) => (
  <span className="inline-flex items-center gap-2 rounded-full border border-line bg-card px-3 py-1.5 text-xs text-muted">
    <span className={`size-2 rounded-full ${live ? "animate-pulse bg-emerald-400" : "bg-amber-400"}`} />
    {live ? "Live" : "Reconnecting…"}
  </span>
);

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

export const Select = ({ children, ...props }) => (
  <div className="relative">
    <select {...props} className={`${fieldClass} cursor-pointer appearance-none pr-10`}>{children}</select>
    <Chevron width="14" height="14" className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-muted" />
  </div>
);
