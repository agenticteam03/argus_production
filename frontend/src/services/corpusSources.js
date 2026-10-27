// ACR-0034, the local tier: an administrator approves or rejects a staged reference source. Argus decides every grant
// (ACR-0001); the screen shows the decisions only when /me lists manage_corpus. Each decision needs a one-use
// WebAuthn step-up bound to the exact staged bundle (`corpus:<name>:<sha256>`), so a newer bundle needs a new touch.
export const corpusObject = (source) => `corpus:${source.name}:${source.sha256}`;

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
