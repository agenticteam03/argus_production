## 2026-10-22 - PHASE-16 step 3: D1-D4 decided; the UI served by a DNS name (WebAuthn's relying party id)

Type: decision
Who: conantkd (+ agent)
Context: step 3 (WebAuthn and step-up) was blocked by D2: the public UI was served on an IPv4 address, which browsers
refuse as a relying party id (#243).
Decision / result:
- D1: `webauthn==3.0.1`, as proposed. D3: two credentials per privileged person, recovery by the other administrator
  (audited CLI, sessions revoked), as proposed.
- D4 (new: the first credential): an enrolment ticket from the other administrator (`argus webauthn allow-enrol`,
  single-use, 24 h by default, audited); the second credential with a step-up of the first. A password alone never
  binds a key.
- D2 (a): the team's subdomain, in `vm-095.env` only (never in Git), resolved straight to vm-095 without a CDN proxy
  (a proxy ends TLS and sees passwords and tokens). The edge took its own Let's Encrypt certificate for the name (90
  days); the address redirects to the name. The `localhost` interim (b) is not needed, so no re-enrolment later.
Consequences: step 3's code reads the relying party id and the expected origin from the VM's environment. A login from the address now lands on the name.
References: [PHASE-16](../../tasks/current/PHASE-16-operator-access.md),
[evidence](../../execution/history/D2-ui-domain/step-01/evidence.md), #243, ACR-0018.
