// The one-use WebAuthn assertion is bound to the exact frozen object the server will validate.
export async function answerFrozenApproval({ approval, decision, confirmation, reason = "", secondFactor, argus }) {
  const digest = approval.proposal.digest;
  const { token } = await secondFactor.stepUp(`approval:${approval.id}:${digest}`);
  return argus.answerApproval(approval.id, {
    decision, proposalDigest: digest, stepUpToken: token,
    confirmationTarget: decision === "approved" && approval.judge.risk === "red" ? confirmation : null,
    reason: decision === "denied" ? reason.trim() : null,
  });
}
