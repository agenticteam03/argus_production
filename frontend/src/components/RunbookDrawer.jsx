import { useEffect, useRef, useState } from "react";
import SafeMarkdown from "./SafeMarkdown.jsx";
import { Book, Close, Warning } from "./ui.jsx";

export default function RunbookDrawer({ runbook: rb, onClose }) {
  const [shown, setShown] = useState(false);
  const closeRef = useRef(null);

  useEffect(() => {
    const raf = requestAnimationFrame(() => setShown(true));
    closeRef.current?.focus();
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-40">
      <div onClick={onClose} className={`absolute inset-0 bg-scrim backdrop-blur-sm transition-opacity duration-(--motion-slow) motion-reduce:transition-none ${shown ? "opacity-100" : "opacity-0"}`} />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label={`${rb.id} ${rb.title}`}
        className={`absolute inset-y-0 right-0 flex w-full flex-col border-l border-line bg-card shadow-2xl transition-transform duration-(--motion-slow) ease-out-soft motion-reduce:transition-none md:w-[68%] md:max-w-[1000px] ${shown ? "translate-x-0" : "translate-x-full"}`}
      >
        <header className="flex items-start justify-between gap-4 border-b border-line p-5">
          <div className="min-w-0">
            <p className="flex flex-wrap items-center gap-2 text-xs">
              <span className="font-mono text-accent-hover">{rb.id}</span>
              {rb.version && <span className="rounded-md border border-line bg-ink/[0.03] px-2 py-0.5 text-muted">v{rb.version}</span>}
              <span className="rounded-md border border-line bg-ink/[0.03] px-2 py-0.5 capitalize text-muted">{rb.status}</span>
              {rb.missing > 0 && (
                <span className="inline-flex items-center gap-1 rounded-full border border-amber-400/20 bg-amber-400/10 px-2 py-0.5 text-amber-300">
                  <Warning width="12" height="12" /> {rb.missing} missing tools
                </span>
              )}
            </p>
            <h2 className="mt-1.5 text-xl font-semibold tracking-tight">{rb.title}</h2>
            <p className="mt-1 text-xs text-muted">Owner: {rb.owner ?? "—"} · Last reviewed: {rb.lastReviewed ?? "—"} · Detector: {rb.detector ?? "—"}</p>
          </div>
          <button ref={closeRef} onClick={onClose} aria-label="Close runbook" className="grid size-10 shrink-0 cursor-pointer place-items-center rounded-xl border border-line bg-field text-muted hover:text-ink">
            <Close />
          </button>
        </header>

        <div className="overflow-y-auto p-4 sm:p-6">
          {/* GitHub-style file viewer */}
          <div className="mx-auto max-w-[920px] overflow-hidden rounded-md border border-md-line bg-md-bg">
            <div className="flex items-center gap-2 border-b border-md-line bg-md-head px-4 py-2.5 text-[13px] text-md-muted">
              <Book width="15" height="15" />
              <span className="truncate font-mono">{rb.file}</span>
            </div>
            <article className="markdown-body p-5 sm:p-8">
              <SafeMarkdown>{rb.markdown.replace(/^# .*\n/, "")}</SafeMarkdown>
            </article>
          </div>
        </div>
      </aside>
    </div>
  );
}
