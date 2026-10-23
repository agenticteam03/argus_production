# PHASE-21 — Recorded operator terminal

| Field | Value |
|---|---|
| Status | 21A implemented; independent safety review pending |
| Architecture | [ACR-0020](../../architecture/changes/ACR-0020-operator-terminal.md), accepted 2026-10-23 |
| Branch | `task/ACR-0020-decision` |
| Owner | conantkd (+ agent) |
| Needs the VM lease | no for 21A; yes for 21D and the 21E drill |

## Goal

Give an authenticated human operator a full shell in the UI under their own identity, with the entire byte stream
recorded and tied to an incident and a VM lease. Argus may suggest an allowed command for insertion but never opens,
reads or types in the session.

## Steps

| Step | Scope | State | Exit proof |
|---|---|---|---|
| **21A** | Offline ticket, fixed account mapping, session state machine, recording and fake adapters | implemented on the task branch | focused unit suite green; no network, route, credential or deployment |
| **21B** | Privileged ticket, list and kill API with step-up and authorization matrix | blocked by phase-16 exit | public 404, permission and replay suites green |
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

## Next exact step

Obtain the independent safety review on the 21A pull request. Finish the ACR-0018 phase-16 exit proof before starting
21B; then add the privileged API contract without introducing SSH connectivity.
