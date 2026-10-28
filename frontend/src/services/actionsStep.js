// ACR-0032: where a person stands before a privileged screen. Argus decides every grant (ACR-0001); this only picks
// the next step to show: the private login (a full token works only on the private path), the security key that
// completes that session, then the decisions /me now lists.
export function privateStep(user, action, roles) {
  if (!user) return "not-granted";
  if (user.actions?.includes(action)) return "ready";
  if (!roles.includes(user.role)) return "not-granted";
  if (user.access !== "ops") return "private-login";
  if (!user.secondFactor?.verified) return "second-factor";
  return "not-granted";
}

// Approvals: an approver's (ACR-0019).
export const actionsStep = (user) => privateStep(user, "approve_action", ["approver"]);

// Reference sources: an approver's or an administrator's (ACR-0034, ACR-0040).
export const corpusStep = (user) => privateStep(user, "manage_corpus", ["approver", "admin"]);
