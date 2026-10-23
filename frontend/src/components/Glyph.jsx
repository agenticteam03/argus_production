import { Box, Database, Server } from "./ui.jsx";

// The hexagon is Argus's health glyph (ui-graphs prototype): its colour says how a component is, its icon what it is.
// The same glyph is used on the dashboard honeycomb, the system map and the mini map, so a state looks the same
// everywhere. Health values come from utils/fleetStatus.js nodeHealth: ok, degraded, failed, unknown, idle.
export const HEALTH_META = {
  ok: { label: "Healthy", word: "running", tone: "text-emerald-400", icon: "text-emerald-300", text: "text-emerald-300" },
  degraded: { label: "Degraded", word: "degraded", tone: "text-amber-400", icon: "text-amber-300", text: "text-amber-300" },
  failed: { label: "Failed", word: "failing", tone: "text-red-400", icon: "text-red-300", text: "text-red-300" },
  unknown: { label: "Unknown", word: "unknown", tone: "text-slate-500", icon: "text-muted", text: "text-muted" },
  idle: { label: "Idle", word: "idle", tone: "text-faint", icon: "text-faint", text: "text-muted" },   // text in muted: AA contrast
};
const KIND_ICON = { box: Box, database: Database, server: Server };
const HEX_POINTS = "20,1.5 38.2,12 38.2,32 20,42.5 1.8,32 1.8,12";

// `pulse`: a ring that grows and fades (the root cause, a failing component); it stops with reduced motion.
export function HexGlyph({ health = "unknown", icon = "box", pulse = health === "failed", size = 30, title, className = "" }) {
  const meta = HEALTH_META[health] ?? HEALTH_META.unknown;
  const Ico = KIND_ICON[icon] ?? Box;
  const dashed = health === "unknown" || health === "idle";
  return (
    <span title={title} aria-hidden={title ? undefined : "true"}
      className={`relative inline-grid shrink-0 place-items-center ${meta.tone} ${className}`} style={{ width: size, height: Math.round(size * 1.1) }}>
      <svg viewBox="0 0 40 44" aria-hidden="true" className="absolute inset-0 size-full overflow-visible">
        <polygon points={HEX_POINTS} strokeWidth="1.6" strokeDasharray={dashed ? "4 3" : undefined}
          className={`stroke-current ${health === "idle" ? "fill-none" : "fill-current/15"} ${health === "failed" ? "hex-glow" : ""}`} />
        {pulse && <polygon points={HEX_POINTS} strokeWidth="1.5" className="hex-pulse fill-none stroke-current" />}
      </svg>
      <Ico width={Math.round(size * 0.43)} height={Math.round(size * 0.43)} className={`relative ${meta.icon}`} />
    </span>
  );
}
