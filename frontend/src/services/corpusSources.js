// ACR-0034, the local tier (ACR-0040: an approver too): an administrator approves or rejects a staged bundle of
// reference sources. Argus decides every grant (ACR-0001); the screen shows the decisions only when /me lists
// manage_corpus. Each decision needs a one-use WebAuthn step-up bound to the exact staged bundle
// (`corpus:<name>:<sha256>`), so a newer bundle needs a new touch.
export const corpusObject = (source) => `corpus:${source.name}:${source.sha256}`;

// The API lists one row per source: an installed one under its own name, a staged one under its bundle's name (a
// bundle such as `base` carries several sources). A decision is about a whole bundle, so the screen groups them.
export function bundles(sources) {
  const out = new Map();
  for (const s of sources) {
    const key = s.status === "installed" ? "installed" : `staged:${s.name}`;
    if (!out.has(key)) out.set(key, { key, name: s.name, status: s.status, at: s.at ?? null, sha256: s.sha256, sources: [] });
    out.get(key).sources.push(s);
  }
  return [...out.values()];
}

export const canManageCorpus = (user) =>
  ["full", "ops"].includes(user?.access) && !!user?.actions?.includes("manage_corpus");

export async function decideCorpusSource({ source, decision, reason = "", secondFactor, argus }) {
  if (source.status !== "staged") throw new Error("Only a staged source can be approved or rejected.");
  if (decision === "reject" && !reason.trim()) throw new Error("A rejection needs a reason.");
  const { token } = await secondFactor.stepUp(corpusObject(source));
  return decision === "approve"
    ? argus.approveCorpusSource(source.name, { stepUpToken: token })
    : argus.rejectCorpusSource(source.name, { reason: reason.trim(), stepUpToken: token });
}
