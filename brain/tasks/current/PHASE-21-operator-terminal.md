# PHASE-21 — Recorded operator terminal

| Field | Value |
|---|---|
| Status | 21A merged; 21B authorization contract in draft, no terminal access enabled |
| Architecture | [ACR-0020](../../architecture/changes/ACR-0020-operator-terminal.md), accepted 2026-10-23; [ACR-0033 draft PR #327](https://github.com/agenticteam03/argus_production/pull/327), proposed for browser origin and ticket handoff |
| Branch | `task/T-0054-operator-terminal` (21A was merged from `task/ACR-0020-decision`) |
| Owner | conantkd (+ agent) |
| Needs the VM lease | no for 21A; yes for 21D and the 21E drill |

## Goal

Give an authenticated human operator a full shell in the UI under their own identity, with the entire byte stream
recorded and tied to an incident and a VM lease. Argus may suggest an allowed command for insertion but never opens,
reads or types in the session.

## Steps

| Step | Scope | State | Exit proof |
|---|---|---|---|
| **21A** | Offline ticket, fixed account mapping, session state machine, recording and fake adapters | merged | focused unit suite green; no network, route, credential or deployment |
| **21B** | Privileged ticket, list and kill API with step-up and authorization matrix | offline launch policy in this draft; routes still pending | public 404, permission and replay suites green |
| **21C** | Browser terminal, permanent context banner, paste confirmation and card-limited Insert | blocked by 21B | browser contract and origin checks green |
| **21D** | Isolated broker, SSH CA, personal accounts, sshd/sudo/auditd and off-host recording | blocked by phase-16 exit; VM lease required | deployment and network-isolation proofs green |
| **21E** | Revoke, kill, expiry, recording-loss, public-edge and break-glass drill | blocked by 21D; VM lease required | drill evidence reviewed; only then may `open_terminal:<host>` be granted |

## 21A boundaries

- `services/terminal_broker/core.py` has no socket, SSH, API, database or object-store dependency.
- A ticket is single use, valid for at most the issued interval, and bound to principal, session, fixed host/account,
  incident and lease.
- A frame counts as accepted only after the recorder persists it. Any append or finalization failure closes the
  session and reports `RecordingFailed`.
- Open, close, refusal and recording-failure events go through a required audit sink; an audit failure prevents a
  session from opening.
- At most two sessions for one principal may be open at once.
- A session closes at its 30-minute absolute limit; continuing requires a new step-up and ticket.
- No permission is granted and no runtime path can invoke this package in 21A.

## STEP 21B.1 — Authorize a launch before ticket issuance

- **Goal:** validate the human, host-specific permission, WebAuthn-ready session, personal account, incident host,
  reason and current host lease before a ticket-bound step-up is consumed.
- **Why:** the future API must not mint a ticket from browser-supplied host, account, incident or lease claims.
- **Where:** laptop, Phase 21 branch. **Changes:** an offline application service and tests only; reversible by
  reverting this branch. No API route, credential, SSH or VM change.
- **Command:** `python -m pytest -q tests/test_phase21_terminal_launch_policy.py tests/test_acr0020_terminal_broker.py`.
- **Expected:** the grant uses a fixed personal account; every refusal precedes step-up consumption; the existing
  broker core remains green.
- **If it fails:** inspect which verified fact was supplied to the policy and whether the ticket ID matches the
  object of the step-up ceremony.

`TerminalLaunchPolicy` receives verified facts from future adapters; it does not trust a browser-provided lease or
permission, issue a ticket, or open a session. The public API and deployment have no terminal route in this draft.

## Next exact step

Resolve ACR-0033's isolated-origin ticket flow before 21C. Verify the ACR-0018 phase-16 exit proof and ACR-0020
safety approval before adding the privileged 21B API routes. Next implement durable single-use ticket issuance and
consumption, list/kill authorization and the public-edge 404 contract, without SSH connectivity.
