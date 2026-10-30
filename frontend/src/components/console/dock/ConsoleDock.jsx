import { useEffect, useRef, useState } from "react";
import { useAuth } from "../../../context/AuthContext.jsx";
import { Pill, Server } from "../../ui.jsx";
import { clock, DOCK_HOSTS, maxDockWidth, MIN_WIDTH, timeLeft } from "./consoleDock.js";
import DockSession from "./DockSession.jsx";
import { Close } from "../../ui.jsx";
import { Maximize, Minimize, Minus, Plus, Power, TerminalIcon } from "./icons.jsx";

// T-0016: the operator console's side panel, like an editor's: on the right, wider by dragging its edge (or the arrow
// keys on it), minimized to a small bar, full screen and back to the width it had. No "x": a session ends with
// Disconnect. One tab per incident; "+" offers the lab hosts. Each session shows its 30-minute limit and ends at it.
const STEP = 24;
const WARN_MS = 2 * 60_000;
const iconButton = "grid size-8 cursor-pointer place-items-center rounded-lg text-muted transition hover:bg-ink/5 hover:text-ink focus-visible:outline-2 focus-visible:outline-accent-hover";
const clampWidth = (w) => Math.round(Math.max(MIN_WIDTH, Math.min(w, maxDockWidth(window.innerWidth))));
const shortId = (id) => id.replace(/^inc_/, "").slice(0, 6);

export default function ConsoleDock({ tabs, activeId, onSelect, mode, onMode, onAdd, onClose, full }) {
  const { user } = useAuth();
  const [width, setWidth] = useState(() => clampWidth(Math.min(680, window.innerWidth * 0.45)));
  const [now, setNow] = useState(() => Date.now());
  const plus = useRef(null);
  const active = tabs.find((t) => t.incidentId === activeId) ?? tabs[0];

  // A smaller window keeps the panel within its limit; a click outside the "+" menu closes it.
  useEffect(() => {
    const fit = () => setWidth((w) => clampWidth(w));
    const outside = (e) => { if (plus.current?.open && !plus.current.contains(e.target)) plus.current.removeAttribute("open"); };
    window.addEventListener("resize", fit);
    document.addEventListener("pointerdown", outside);
    return () => { window.removeEventListener("resize", fit); document.removeEventListener("pointerdown", outside); };
  }, []);

  // A docked panel takes the right side on wide screens; the page shrinks beside it instead of hiding under it.
  useEffect(() => {
    const root = document.documentElement;
    root.style.setProperty("--console-w", mode === "docked" ? `${width}px` : "0px");
    return () => root.style.setProperty("--console-w", "0px");
  }, [mode, width]);

  // The countdown, and the end of a session at its limit (the API also records it).
  useEffect(() => {
    const id = setInterval(() => {
      const t = Date.now();
      setNow(t);
      for (const tab of tabs) {
        if (timeLeft(tab.expiresAt, t) === 0) {
          onClose(tab.incidentId, "time_limit", `The console on ${tab.host} closed: its 30-minute limit was reached.`);
        }
      }
    }, 1000);
    return () => clearInterval(id);
  }, [tabs, onClose]);

  const left = active ? timeLeft(active.expiresAt, now) : 0;

  const drag = (e) => {
    e.preventDefault();
    const grip = e.currentTarget;
    grip.setPointerCapture(e.pointerId);
    const move = (ev) => setWidth(clampWidth(window.innerWidth - ev.clientX));
    const up = () => { grip.removeEventListener("pointermove", move); grip.removeEventListener("pointerup", up); };
    grip.addEventListener("pointermove", move);
    grip.addEventListener("pointerup", up);
  };
  const keyResize = (e) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    setWidth((w) => clampWidth(w + (e.key === "ArrowLeft" ? STEP : -STEP)));
  };

  const place = mode === "fullscreen" ? "inset-0"
    : "inset-y-0 right-0 w-full border-l border-line shadow-[-16px_0_48px_-24px_rgb(0_0_0/0.45)] sm:w-[var(--dock-w)]";

  return (
    <>
      <aside aria-label="Operator console" style={{ "--dock-w": `${width}px` }}
        className={`fixed z-40 flex flex-col overflow-hidden bg-card text-body ${place} ${mode === "minimized" ? "hidden" : ""}`}>
        {mode === "docked" && (
          <div role="separator" aria-orientation="vertical" aria-label="Resize the console" tabIndex={0} aria-valuenow={width}
            aria-valuemin={MIN_WIDTH} aria-valuemax={Math.round(maxDockWidth(window.innerWidth))} onPointerDown={drag} onKeyDown={keyResize}
            className="absolute inset-y-0 -left-1 z-10 hidden w-2 cursor-col-resize touch-none hover:bg-accent/30 focus-visible:bg-accent/40 focus-visible:outline-none sm:block" />
        )}

        <div className="flex items-center gap-1 border-b border-line px-2 py-1.5">
          <div className="flex min-w-0 flex-1 items-center gap-1">
            <div role="tablist" aria-label="Console sessions" className="flex min-w-0 items-center gap-1 overflow-x-auto">
              {tabs.map((t) => {
                const on = t.incidentId === active?.incidentId;
                return (
                  <div key={t.incidentId} className={`flex shrink-0 items-center rounded-lg border transition ${on ? "border-line bg-ink/5 text-ink" : "border-transparent text-muted hover:text-ink"}`}>
                    <button type="button" role="tab" id={`dock-tab-${t.incidentId}`} aria-selected={on}
                      aria-controls={`dock-panel-${t.incidentId}`} onClick={() => onSelect(t.incidentId)} title={`${t.target} · ${t.incidentId}`}
                      className="flex cursor-pointer items-center gap-1.5 py-1.5 pl-2.5 pr-2 text-sm">
                      <TerminalIcon width="14" height="14" />
                      <span className="font-mono">{t.host}</span>
                      <span className="font-mono text-xs text-muted">{shortId(t.incidentId)}</span>
                    </button>
                    {/* with two or more sessions each tab closes on its own; the last one ends with Disconnect */}
                    {tabs.length > 1 && (
                      <button type="button" onClick={() => onClose(t.incidentId, "disconnect", `Closed the console on ${t.host} (${t.incidentId}).`)}
                        aria-label={`Close the console on ${t.host} (${t.incidentId})`} title="Close this console"
                        className="mr-1 grid size-5 cursor-pointer place-items-center rounded text-muted hover:bg-ink/10 hover:text-ink">
                        <Close width="12" height="12" />
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
            <details ref={plus} className="relative shrink-0">
              <summary aria-label="Open the console on a host" title="Another console" aria-disabled={full}
                className={`${iconButton} list-none [&::-webkit-details-marker]:hidden ${full ? "pointer-events-none opacity-40" : ""}`}>
                <Plus width="16" height="16" />
              </summary>
              <div className="absolute left-0 z-20 mt-1 min-w-48 rounded-xl border border-line bg-card p-1.5 shadow-2xl">
                <p className="px-3 pb-1 pt-1.5 text-xs text-muted">Open a console on</p>
                {DOCK_HOSTS.map((h) => (
                  <button key={h} type="button" onClick={() => { plus.current?.removeAttribute("open"); onAdd(h); }}
                    className="flex w-full cursor-pointer items-center gap-2 rounded-lg px-3 py-2 text-left text-sm hover:bg-ink/5">
                    <Server width="14" height="14" /> <span className="font-mono">{h}</span>
                  </button>
                ))}
              </div>
            </details>
          </div>
          <button type="button" onClick={() => onMode("minimized")} aria-label="Minimize the console" title="Minimize" className={iconButton}>
            <Minus width="16" height="16" />
          </button>
          <button type="button" onClick={() => onMode(mode === "fullscreen" ? "docked" : "fullscreen")}
            aria-label={mode === "fullscreen" ? "Exit full screen" : "Full screen"} title={mode === "fullscreen" ? "Exit full screen" : "Full screen"}
            className={iconButton}>
            {mode === "fullscreen" ? <Minimize width="16" height="16" /> : <Maximize width="16" height="16" />}
          </button>
          {active && (
            <button type="button" onClick={() => onClose(active.incidentId, "disconnect", `Disconnected from the console on ${active.host}.`)}
              className="ml-1 flex h-8 cursor-pointer items-center gap-1.5 rounded-lg border border-line px-2.5 text-sm text-danger transition hover:bg-ink/5">
              <Power width="14" height="14" /> <span className="hidden min-[420px]:inline">Disconnect</span>
              <span className="sr-only min-[420px]:hidden">Disconnect</span>
            </button>
          )}
        </div>

        {active && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line px-4 py-2 text-xs text-muted">
            <span className="flex items-center gap-1.5 font-mono text-[13px] text-ink"><Server width="14" height="14" />{active.host}</span>
            <span className="min-w-0 truncate font-mono" title={active.target}>{active.target.split("/").slice(1).join("/")}</span>
            <span>as <span className="text-ink">{user?.name}</span></span>
            <span className="ml-auto flex items-center gap-2">
              <Pill tone="blue">Private session</Pill>
              <span role="timer" aria-label="Time left in this console session" title="A console session lasts 30 minutes"
                className={`font-mono text-[13px] tabular-nums ${left <= WARN_MS ? "text-danger" : "text-ink"}`}>{clock(left)}</span>
            </span>
            <span className="w-full truncate" title={active.reason}>Reason: {active.reason}</span>
          </div>
        )}
        {active && left <= WARN_MS && (
          <p role="status" className="border-b border-line bg-amber-400/10 px-4 py-1.5 text-xs text-ink">
            This console session ends in {clock(left)}. Open it again afterwards if you still need it.
          </p>
        )}

        <div className="relative min-h-0 flex-1">
          {tabs.map((t) => (
            <div key={t.incidentId} role="tabpanel" id={`dock-panel-${t.incidentId}`} aria-labelledby={`dock-tab-${t.incidentId}`}
              className={`absolute inset-0 ${t.incidentId === active?.incidentId ? "" : "invisible"}`}>
              <DockSession incidentId={t.incidentId} active={t.incidentId === active?.incidentId && mode !== "minimized"} />
            </div>
          ))}
        </div>
      </aside>

      {mode === "minimized" && active && (
        <button type="button" onClick={() => onMode("docked")} aria-label={`Restore the console (${tabs.length} open)`}
          className="toast-in fixed bottom-4 right-4 z-40 flex cursor-pointer items-center gap-2 rounded-xl border border-line bg-card px-3 py-2 text-sm text-ink shadow-[0_16px_48px_-12px_rgb(0_0_0/0.35)] hover:bg-field">
          <TerminalIcon width="16" height="16" />
          <span>Console</span>
          <span className="font-mono text-muted">{active.host}</span>
          <span className={`font-mono tabular-nums ${left <= WARN_MS ? "text-danger" : "text-muted"}`}>{clock(left)}</span>
          {tabs.length > 1 && <span className="rounded-md bg-ink/5 px-1.5 text-xs text-muted">{tabs.length}</span>}
        </button>
      )}
    </>
  );
}
