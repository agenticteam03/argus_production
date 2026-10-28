# ACR-0037 — Private path: the client certificate alone

| Field | Value |
|---|---|
| Status | `accepted` |
| Proposed by | `conantkd` · 2026-10-28 |
| Accepted by | `conantkd` · 2026-10-28 |
| Second approval (safety principle only) | not required |
| Architecture version | proposed: `1.8.43` → `1.8.44` |
| Task / PR | private path access · PR to be numbered on opening |

## 1. Problem

The private path (`/api/v1/ops/`, ACR-0018 phase 16 step 4, and the private login of ACR-0032) passes only when the client's certificate verifies against the team's CA, is not revoked, AND the client's address is in vm-095's allowlist. A team member with a valid certificate in the browser and a registered passkey still gets "The private login is reachable only on the private path" (the edge's 404) whenever their address changed, the entry expired, or they come over IPv6, which `ops/edge-allow.sh` cannot register. Each such change needs a lease on vm-095 to fix, and it blocks the Actions tab during the demo window.

## 2. Why the current architecture is insufficient

The address is the least stable of the two conditions and adds no identity: the certificate is per person, made from the person's own key, expires in 90 days and can be revoked in the CRL. The human is proven by the login, the second factor and the step-up (ACR-0018, ACR-0032); mTLS is defence in depth.

## 3. Smallest reasonable change

The edge's `$argus_ops_ok` depends on `$ssl_client_verify` alone: `SUCCESS` is 1, anything else 0. The `geo` block over the allowlist is removed from `deploy/ui/nginx/http.conf`. Everything else stays: the CA and CRL, `ARGUS_OPS_PATH=off` by default, the 404 for no, revoked or foreign certificates, `X-Argus-Ops` set only by the edge, and the API's refusal of an `ops` token without it.

**Alternatives considered:**

- Keep the allowlist and widen entries: rejected; a wider prefix is a provider's range, which `edge-allow.sh` refuses for good reason.
- Add IPv6 to `edge-allow.sh`: rejected for now; it fixes one of three failure causes and keeps the lease-per-change cost.

## 4. Consequences

- Code and tests: `deploy/ui/nginx/http.conf`; `tests/test_phase16_private_path.py` now expects a valid certificate to reach the API from any address.
- Left in place, now unused by the edge: `ops/edge-allow.sh`, its daily prune timer, the `allow.conf` mount and `ops-allow.conf`. Removing them is a separate clean-up.
- Deployment: vm-095's edge picks up the new `http.conf` on the next UI deploy (lease).
- Risk: a stolen certificate plus its key now works from any network; it still needs a valid login, the second factor and the step-up for any privileged action. Revoking the certificate in the CRL closes it.
- Reversal: restore the `geo` block and the two-key `map` in a reviewed change.
- Safety principle changed: no. Read-only phase, write gate and human approval are unchanged; one defence-in-depth layer of the operator path is removed.

## 5. Decision

`conantkd` asked for the change on 2026-10-28: the browser certificate is enough for the private path.

## 6. Applied

- [x] `ARCHITECTURE.md` updated, version bumped to 1.8.44, changelog line added with this ACR's link
- [x] journal entry
- [x] the ACR, the architecture change and the code that needs it are in the same pull request
