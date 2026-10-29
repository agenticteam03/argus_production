# OPERATOR-CONSOLE — task board (stage 1)

| Field | Value |
|---|---|
| Status | `proposed`, starts now; protected parts wait for the ACR |
| Architecture | [ACR-0043](../../architecture/changes/ACR-0043-operator-console.md) (proposed) |
| Spec | [OPERATOR-CONSOLE-spec](OPERATOR-CONSOLE-spec.md) |
| Needs the VM lease | only for the rehearsal and for confirming the worker metric names |

## How to work this board

- **Open pool.** Anyone may take any task, in any order that its dependencies allow. One developer may take all of them.
- **Claim:** put your handle in the Owner column in a small PR (or tell the team in the session notes). Release it the same way.
- A task is done when its acceptance line is true and its PR is merged. Protected paths (`argus/actions/`, `brain/architecture/`,
  `contracts/`, `deploy/`, `.github/`) need a review by someone other than the author.
- Demo minimum (spec §14): scenario 1 with read commands, `cache restart` through the safety path, and Argus commenting after
  each command. Cut lines are in the spec.

## Findings from the code (origin/main a60e3f91), they change the spec slightly

- Read commands map to the capability catalogue and `MetricsPort`; no new probe is needed.
- The approve endpoint in the spec (`POST /api/v1/incidents/{id}/approve`) does not exist. Approval is
  `POST /api/v1/ops/approvals/{id}/answer` with the approver role and a fresh second factor. A typed write command creates the normal
  proposal and the console asks for the approval there. No second approval path.
- The cache fix is `container.start` (the cache is stopped): `cache restart` maps to start when the container is stopped.
- The frontend refreshes by polling (`usePoll`); there is no WebSocket or SSE. The scrape interval is 15 s, so settle is 45 s.
- Scenario 2 is blocked by the open card TASK-97 (the candidate builder in `argus/actions/incident.py`, protected, builds no `network.restore` proposal yet).
- The mockup spec named in the spec (`argus-console-mockup-spec.md`) is not in the repo yet; whoever takes CON-3 adds it first.
- Write commands reach only the pairs in `write_gate.open` (start on the cache, restart on the jobworker, `network.restore` on the API); `cache restart` on a running cache is rejected. `net reconnect api` is the existing `network.restore`, not a new action. Access is described in the ACR.
- The spec is superseded by the ACR where they differ (§6 and §7.3 of the spec).
- Optional (cut first, not needed for the three scenarios): CON-5 suggestions beyond Insert and Copy, the Langfuse trace in CON-4, CON-9.

## Tasks

| ID | Task | Depends on | Protected | Owner | Acceptance |
|---|---|---|---|---|---|
| CON-1 | Registry, parser, allowlist (`argus/console/`) | none | no | | `help` lists commands; `ls` and `status; rm` are rejected |
| CON-2 | `GET /console/commands`, `POST /console/execute`, history table, scenario 1 read commands | CON-1 | routes and migration | | `cache status`, `api cpu`, `host metrics` return real lab data; each command stored with its incident |
| CON-3 | Split-view UI: terminal and Argus panel, history, polling | CON-1 contract, mockup spec | no | conantkd | works at 1280x720; no hardcoded output |
| CON-4 | Post-command analysis: settle, samples, before/after, evidence, comment, ranking refresh, Langfuse trace | CON-2 | no | | after `api cpu`, the red-herring hypothesis is demoted with a grounded comment |
| CON-5 | Suggestions with Insert and Copy, `suggestion_id`, "Applied" state | CON-3, CON-4 | no | | Insert fills the input and never runs it |
| CON-6 | Write path: confirmation, proposal, approval, audit `operator_console`, gateway, verify | ACR, CON-2 | yes | | `cache restart` asks, needs approval, restarts, appears in the audit log |
| CON-7 | Scenario 4 commands (worker status, heartbeat, throughput, queue depth, restart) | CON-2, CON-6, metric names confirmed | no | | frozen worker resolved from the console |
| CON-8 | Scenario 2 commands (net inspect, expected, diff, reconnect = existing `network.restore`) | CON-2, CON-6, TASK-97 | yes | | wrong network resolved from the console |
| CON-9 | Errors: timeouts, metrics unavailable, backend failures; manual re-check | CON-4 | no | | each failure shows a clear message; the UI recovers |
| CON-10 | Rehearsal, several runs per scenario, results recorded | all | no | | right ranking and comment on every run |

Suggested order: CON-1, then CON-2 and CON-3 in parallel, then CON-4, CON-5, CON-6, then CON-7, CON-8, CON-9, CON-10.
