// ACR-0032: where an approver stands on the Actions screen. Argus decides every grant (ACR-0001); this only picks
// the next step to show: the private login (a full token works only on the private path), the security key that
// completes that session, then the decisions /me now lists.
export function actionsStep(user) {
  if (!user) return "not-granted";
  if (user.actions?.includes("approve_action")) return "ready";
  if (user.role !== "approver") return "not-granted";
  if (user.access !== "ops") return "private-login";
  if (!user.secondFactor?.verified) return "second-factor";
  return "not-granted";
}
