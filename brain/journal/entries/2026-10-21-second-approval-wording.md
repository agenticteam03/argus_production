## 2026-10-21 — Softened: any team member's approval is the second approval for a safety-principle change

Type: decision
Who: conantkd (proposed), juanbetancurm (approved) (+ agent)
Context: a safety-principle change needs an ACR with a second approval (AGENT_PROTOCOL §4, SECURITY.md). ACR-0018 and
ACR-0024 read that as two teammates other than the author approving the same pull request, and ACR-0012 recorded the
same person approving twice as a conscious deviation. conantkd proposed on #209 to soften it.
Decision / result:
- Agreed: any team member's approval counts as the second approval, the author's included, and one person may give
  both approvals (accepting the ACR and approving the pull request); that is no longer a deviation.
- Unchanged: a safety-principle change still needs an ACR, and every protected path (every ACR is under
  `brain/architecture/`) still needs a teammate's approval on the last push (REVIEW_PROTOCOL).
- AGENT_PROTOCOL §4, REVIEW_PROTOCOL (checklist and protected paths), SECURITY.md and ACR-TEMPLATE.md say so.
Consequences: ACR-0012, #209 (ACR-0018), #215 (ACR-0024) and #218 (ACR-0028) meet the softened rule; #222 rewrites
the ACR-0018 and ACR-0024 tables to match.
References: [AGENT_PROTOCOL §4](../../agents/AGENT_PROTOCOL.md), #209, #215, #218, #222.
