// T-0016 motion for the few things CSS cannot animate (a number counting up). The durations are the --motion-* tokens
// of src/motion.css, so prefers-reduced-motion (which sets them to 0) stops these too, with no second check here.

// A --motion-<name> token in milliseconds ("700ms", "0.32s"); 0 when it is off, missing or there is no browser.
export function motionMs(name, style = globalThis.document ? getComputedStyle(globalThis.document.documentElement) : null) {
  const raw = style?.getPropertyValue(`--motion-${name}`).trim() ?? "";
  const m = /^([\d.]+)(ms|s)$/.exec(raw);
  return m ? Number(m[1]) * (m[2] === "s" ? 1000 : 1) : 0;
}

// The whole number shown at `progress` (0..1) of a count from `from` to `to`, eased out: quick first, settling last.
export function countFrame(from, to, progress) {
  const p = Math.min(1, Math.max(0, progress));
  const eased = 1 - (1 - p) ** 3;
  return p === 1 ? to : Math.round(from + (to - from) * eased);
}
