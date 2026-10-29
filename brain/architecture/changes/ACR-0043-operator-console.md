# ACR-0043 — Operator console, stage 1: a restricted command console over Argus's own tools

Replaces the first draft of this ACR (a real shell for the demo). Related: [ACR-0020](ACR-0020-operator-terminal.md) (the full
terminal, which stays the stage-2 path), [ACR-0019](ACR-0019-human-approved-remediation.md) (human-approved remediation).

| Field | Value |
|---|---|
| Status | `proposed` |
| Proposed by | juanbetancurm (+ agent) · 2026-10-29 |
| Accepted by | |
| Second approval (safety principle only) | **required**: write gate (a human-typed command starts an action) and read-only (new read entry point) |
| Architecture version | no change while `proposed`; the applying PR bumps it |
| Task / PR | [OPERATOR-CONSOLE](../../tasks/current/OPERATOR-CONSOLE.md) · the pull request that adds this file |

## 1. Detect and explain

For the next demonstration an operator should work the three scenarios (cache down, wrong network, stalled worker) from the incident
page, typing commands in a console while Argus explains what each result means. Today the operator has no console in the UI, and
Argus does not react to what the operator does.

## 2. Why the current architecture is insufficient

- Argus's tools are used only by the agent and the action path; there is no operator-facing command entry point.
- §1.2 / §4.6 / §4.7 forbid shell execution by Argus's tools. A real shell for people is ACR-0020 and is blocked by the phase-16
  exit proof. Stage 1 needs neither: it is a **command dispatcher**, not a shell.

## 3. Smallest reasonable change

- **Operator console** in the incident page: terminal on the left, Argus panel on the right (hypotheses, suggested commands with
  Insert and Copy, comments on each result).
- **A command registry in the backend.** Each allowed command maps to a capability or port Argus already has (capability catalogue,
  `MetricsPort`, the declared topology). No OS shell, PTY, exec, pipe or script. Unknown verbs, unknown services and shell syntax are
  rejected before anything runs. Service and network arguments are validated against the declared lab topology. Outputs are real.
- **Write commands use the existing safety path, with no second path:** a typed write command becomes the normal proposal for that
  action (same card, `policy.check`, audit, gateway, verification). Approval is the existing approval answer with the approver role
  and a fresh second factor; an operator who is not an approver cannot approve. Audit entries carry `source: operator_console`, the
  person and the command id. (Whether the second-opinion reviewer also applies to operator writes is an open question, see §5.)
- **A console command can never reach a (capability, target) pair outside `write_gate.open`.** Today that list names only
  `container.start` on the cache, `container.restart` on the jobworker and `network.restore` on the API. A write command maps to
  **exactly one** released pair: `cache restart` means `container.start` and is accepted only while the cache is stopped (on a
  running cache it is rejected, because `container.restart` on the cache is not released); `worker restart` means
  `container.restart` on the jobworker; `net reconnect api` means the existing `network.restore` on the API (ACR-0035), not a
  new action. A typed confirmation is never an approval.
- **Who may call the console.** One entry point under the private prefix (`/api/v1/ops/console/...`); the public edge answers 404.
  Read commands need `investigate` on the person's own session; write commands need `propose_action` (privileged: a session
  completed with a passkey) and, to approve, the `approver` role with a fresh second factor as today. Service and agent
  principals are refused. Read commands are rate-limited per person on the pattern of the ACR-0012 quotas (the numbers go in
  configuration, set in CON-2); write commands are bounded by the existing proposal and approval limits. Every call is audited.
- **Post-command analysis:** after each command Argus waits for the metrics to settle (at least two scrape intervals plus margin; the
  scrape interval is 15 s), samples twice, compares before and after, and records structured evidence with references. The
  deterministic ranking recomputes; the model does not rank. A comment may state only what the output or metrics show.
- **Argus never types in the console.** Suggestions only fill the input line; the person presses Enter.
- UI wording: **Operator console**. Stage 1 is described as a restricted console over Argus's tools; the full shell is stage 2.

Alternatives considered:
- A: a real shell on the lab host (the first draft of this ACR) — a new privileged channel, much more to review and deploy.
- B: build all of ACR-0020 first — cannot be done in time.
- C: do nothing — the demo shows no operator action.

## 4. Consequences

- New: `argus/console/` (registry, parser, handlers, analysis, suggestions), console routes, a history table, UI components.
  The write path touches `argus/actions/` and the routes (protected: needs review by someone other than the author).
- Needs the lab VM for the scenario rehearsals, so the VM lease applies.
- Scenario 2 depends on the open card TASK-97 (the candidate builder in `argus/actions/incident.py` does not yet build a `network.restore` proposal).
- Risk: metric lag makes Argus say "no change" too early (settle delay and two samples); model latency (visible status line).
- Reverse: remove the console routes and the UI entry; no data outside the history table.
- Safety principle touched: **yes** (write gate, read-only).

## 5. Decision

Pending. Open questions for the reviewer: (1) does the second-opinion reviewer also apply to operator writes (proposed: yes); (2) the access split above (`investigate` for reads, `propose_action` for writes, private path only); (3) the read-command rate limits.

## 6. Applied

- [ ] accepted
- [ ] `ARCHITECTURE.md` updated, version bumped, changelog line added
- [ ] journal entry
