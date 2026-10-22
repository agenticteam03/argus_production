## 2026-10-21 — Phase 16 step 3: WebAuthn needs a DNS name; three decisions proposed

Type: decision proposal
Who: conantkd (+ agent)
Context: preparing step 3 (WebAuthn and step-up, ACR-0018) before any code.
Decision / result:
- **Blocker found:** the lab's public UI is served on an IPv4 address (Let's Encrypt's IP certificate). WebAuthn's
  relying party id must be a domain, so step 3 cannot run on the public edge as it is.
- Proposed (PHASE-16 task, "Step 3 — proposed decisions"): D1 `webauthn==3.0.1`; D2 a real DNS name for anything past
  the lab, `localhost` through the SSH tunnel as the lab's interim; D3 two credentials per privileged person and a
  recovery by the other administrator (audited CLI, sessions revoked).
Consequences: the team decides D2 (a name may mean a purchase) before step 3's code; D1 and D3 can be approved on the
pull request.
References: [PHASE-16](../../tasks/current/PHASE-16-operator-access.md),
[ACR-0018](../../architecture/changes/ACR-0018-operator-access-and-audit.md).
