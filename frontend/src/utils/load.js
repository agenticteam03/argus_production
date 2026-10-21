// Simple load levels for a usage ratio (0..1): normal below 75 %, high from 75 %, critical from 90 % (the MVP's ticks).
// One set of thresholds for CPU, memory and disk; change the two numbers here to tune them.
export const LOAD_HIGH = 0.75;
export const LOAD_CRITICAL = 0.9;

export function loadLevel(ratio) {
  if (!Number.isFinite(ratio)) return null;
  return ratio >= LOAD_CRITICAL ? "critical" : ratio >= LOAD_HIGH ? "high" : "ok";
}

// The host's overall level is its worst metric. Null when there is no reading at all.
export const worstLevel = (levels) => ["critical", "high", "ok"].find((l) => levels.includes(l)) ?? null;
