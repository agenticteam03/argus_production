// The "Refresh" button next to the Live pill. A refresh that answers in 30 ms would make the spinner flash too fast
// to see, so it keeps spinning for at least MIN_SPIN_MS. The refresh functions (useLiveOverview, useIncidentList, the
// Agent page) swallow their errors to keep the last data on screen, so they answer `false` on failure instead of
// throwing; a thrown error counts as a failure too.
export const MIN_SPIN_MS = 600;

export async function runRefresh(refresh, {
  minMs = MIN_SPIN_MS,
  now = () => Date.now(),
  wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
} = {}) {
  const start = now();
  let ok;
  try { ok = (await refresh()) !== false; } catch { ok = false; }
  const left = minMs - (now() - start);
  if (left > 0) await wait(left);
  return ok;
}
