# ACR-0043 — Demo profile of the operator terminal, focused on scenarios 1, 2 and 4

A short-lived, reduced profile of [ACR-0020](ACR-0020-operator-terminal.md) (accepted, owner conantkd). It is proposed as the
version of the terminal that can ship for the second demonstration. It does not replace ACR-0020: steps 21B-21E stay the
production path.

| Field | Value |
|---|---|
| Status | `proposed` |
| Proposed by | juanbetancurm (+ agent) · 2026-10-29 |
| Accepted by | |
| Second approval (safety principle only) | **required**: least privilege (a shell on a lab host) and secrets (a key held by a new service) |
| Architecture version | no change while `proposed`; the applying PR bumps it |
| Task / PR | to be set when the cards are queued · the pull request that adds this file |

## 1. Detect and explain

The second demonstration should show an operator fixing the three scenarios (cache down, network mismatch, stalled worker) from
the Argus page, not from a laptop. The full ACR-0020 path (SSH certificate authority, personal accounts, step-up, isolated broker,
off-host recording) is blocked by the ACR-0018 phase-16 exit proof and cannot be finished in time. Today the operator leaves the UI.

## 2. Why the current architecture is insufficient

ACR-0020 §17.4 allows a terminal only through its full control set. It has no reduced profile for an isolated lab host, and the
broker has no socket or SSH code yet (only the offline 21A core). Nothing shows an operator the diagnosis and the commands next to
a shell.

## 3. Smallest reasonable change

A **demo profile**, off by default, removed after the demonstration:

- **A real shell**, not a command filter. It runs on one fixed lab host, as one dedicated non-root account, through a small broker
  (the 21A core plus `websockets` and `asyncssh`). The key exists only in the broker. The browser uses xterm.js over a same-origin
  WebSocket on the private path; the public edge answers 404.
- **Who:** logged-in humans on a named allow-list who hold `open_terminal` for that host. A single-use ticket (60 s at most) is issued
  by the API and sent as the first WebSocket message, never in a URL. Agents and service principals are refused.
- **Limits and record:** 30 minutes, 2 sessions per person; open, close and refusal audit events through the existing sink; the byte
  stream recorded to a local file.
- **Argus never executes.** It has no network path to the broker and never reads or types in a session (a tested property).
- **Remediation panel:** a read-only incident field with the diagnosis, evidence, and commands built from the action-card catalogue
  with **validated** names; no command is built if a name cannot be validated. The panel only offers copy. Insufficient evidence gives
  "inspect first" read-only commands. Verification stays a separate read-only check: exit code 0 is never "resolved".
- **Switch:** `ARGUS_OPERATOR_TERMINAL=off` by default; the broker runs only from a demo compose overlay.

Alternatives considered:
- A: allow-listed command console through the action gateway (no shell) — rejected by the product owner: the demo needs a real shell.
- B: build all of ACR-0020 — not possible before the demo.
- C: SSH inside the API process — the key would sit next to the AI-facing code.

## 4. Consequences

- New code: broker server, API ticket and sessions routes, remediation view, two UI components, one demo compose overlay, one nginx
  WebSocket location (private only). Details and task cards: `_team/texts/OPERATOR-TERMINAL-PLAN.md`.
- Known demo risk: a member of the docker group on the lab host is root-equivalent there. Accepted only for an isolated lab VM with no
  production data and no real secrets, and only until the demo is over.
- Needs the VM lease of the host for the account and key setup and the rehearsal.
- Reverse: set the flag off, stop the overlay, remove the demo account and key from the host.
- Safety principle touched: **yes** (least privilege, secrets).

## 5. Decision

Pending. Conan is asked to accept, change or reject this profile, and to say which parts of ACR-0020 he wants kept even for the demo.

## 6. Applied

- [ ] accepted
- [ ] `ARCHITECTURE.md` updated, version bumped, changelog line added
- [ ] journal entry
- [ ] demo account, key and overlay removed after the demonstration
