# Argus operator console: implementation spec (stage 1)

> **Superseded where it differs from [ACR-0043](../../architecture/changes/ACR-0043-operator-console.md).** The ACR wins on: §6 (`net reconnect api` is the existing `network.restore`, not a new action), §7.3 (a typed confirmation is never an approval; a write command creates the normal proposal, approved through `POST /api/v1/ops/approvals/{id}/answer`), write commands only on the pairs in `write_gate.open`, and who may call the console.

For the project-manager agent: use this to compare against the current codebase, find what exists and what's missing, and plan the work for this stage.

## 1. Context

Argus is our incident-investigation agent. For the presentation, it resolves three staged scenarios end to end in the lab (API, cache, database, backend, worker, gateway):

1. Cache failure with a red herring (main scenario)
2. Wrong network
3. Frozen worker (called scenario 4 everywhere else; this is the same scenario)

The existing building blocks this feature should reuse: the live system map, hypothesis generation with evidence-based deterministic ranking, the second-opinion reviewer, `policy.check`, `NotificationPort`, the approve endpoint `POST /api/v1/incidents/{id}/approve`, `AuditSinkPort`, `MetricsPort`, the restricted Docker proxy (restart allowed, exec disabled), LangGraph checkpoints and interrupts, PostgreSQL, Langfuse and the React frontend.

## 2. Goal

Add an **operator console** to the Argus UI in a split view:

- **Left:** a terminal where the operator types commands.
- **Right:** the Argus panel, with hypotheses, suggested commands the operator can insert into the terminal, and Argus's comments on each result.

After every command, Argus automatically waits for metrics to settle, reads the command output and the fresh metrics, updates the evidence and ranking, and comments on what happened.

## 3. Stage 1 approach: command dispatch, not a shell

The console is a restricted command interpreter in our backend. Each allowed command maps to a function or port Argus already has. There is no OS shell, PTY or exec.

- Outputs are real. They come from the same ports and adapters Argus uses (Prometheus through `MetricsPort`, read-only Docker inspect, the live map). No output may be hardcoded.
- Stage 2 (later, out of scope): a full shell in a sandboxed container (xterm.js + WebSocket + PTY) with the same observation hook. See section 13.

**UI and presentation wording:** the feature is called **Operator console**. Do not label it "demo" or "mock" in the UI. The presentation explains that stage 1 is a restricted console over Argus's tools and that a full shell is planned for stage 2.

## 4. Scope

**In scope**

- Split-view UI with a terminal component and the Argus panel.
- A command registry, parser and allowlist covering the three scenarios.
- Read commands wired to existing functions.
- Write commands (`cache restart`, `worker restart`, `net reconnect api`) routed through the existing safety path.
- Suggestion cards with **Insert into console** and **Copy**.
- A post-command analysis loop: settle delay, fresh metrics, before/after comparison, evidence update, ranking refresh and comment.
- Command history stored per incident.

**Out of scope**

- A real shell, arbitrary commands, pipes or scripting.
- Multi-user sessions and authentication beyond what Argus already has.
- Scenario fault injection and reset from the console. These stay in the existing break and reset scripts.

## 5. Principles and constraints

1. **Reuse over new mechanisms.** Every command calls an existing port, adapter or action. A new mechanism is only allowed where the scenario plan already requires one (the network reconnect action).
2. **Keep the safety model.** Read commands stay read-only. Write commands go through policy → approval → audit → execution → verification, exactly like Argus-proposed actions.
3. **Staged faults, real investigation.** Argus's comments, evidence and ranking come from real output and metrics. Nothing is scripted per scenario. Any unavoidable shortcut must be flagged so we can disclose it.
4. **Strict allowlist.** Unknown verbs, unknown services and shell syntax (`;`, `&&`, `|`, `>`, `$(`, backticks) are rejected before anything runs.
5. **Lab only.** Service and network arguments are validated against the declared lab topology.

## 6. Command catalog

Proposed names. The "Calls" column is what each command should map to. The PM agent should confirm the actual function names in the codebase and flag anything missing.

| Command | Scenario | Class | Calls (confirm in code) | Output |
|---|---|---|---|---|
| `help` | all | meta | Command registry | List of commands |
| `clear`, `history` | all | meta | Frontend only / console history store | — |
| `status` | all | read | Read-only Docker inspect adapter | State and health per lab service |
| `map <service>` | all | read | Live map / system graph API | Edges for the service with state and change time |
| `cache status` | 1 | read | Docker inspect + `MetricsPort` | State, since, health |
| `api errors [--since HH:MM]` | 1 | read | `MetricsPort` (error rate, error types) | Time series summary |
| `api cpu [--since HH:MM]` | 1 | read | `MetricsPort` | Time series summary with onset |
| `host metrics` | 1 | read | `MetricsPort` (node metrics) | CPU, memory, disk, load |
| `cache restart` | 1 | write | Existing restart action via the restricted Docker proxy | Policy, audit and restart result |
| `worker status` | 4 | read | Docker inspect | State and health |
| `worker heartbeat` | 4 | read | `MetricsPort` (last-processed heartbeat) | Time since last job |
| `worker throughput` | 4 | read | `MetricsPort` (processed-jobs counter) | Jobs per minute |
| `queue depth` | 4 | read | `MetricsPort` (queue depth) | Depth and trend |
| `worker restart` | 4 | write | Existing restart action | Policy, audit and restart result |
| `net inspect <service>` | 2 | read | Read-only Docker inspect | Attached networks |
| `net expected <service>` | 2 | read | Declared expected topology (compose or config) | Expected networks |
| `net diff <service>` | 2 | read | Expected vs actual comparison | Mismatch, if any |
| `net reconnect api` | 2 | write | Existing `network.restore` on the API (ACR-0035; see the ACR) | Disconnect/connect result |

Dependencies:

- The frozen-worker commands need the worker's heartbeat, processed-jobs and queue-depth metrics. If those aren't instrumented yet, that's a blocking work item from the scenario plan.
- `net reconnect api` is the existing `network.restore` (ACR-0035); it also needs the open card TASK-97 so a proposal is built.

## 7. Backend design

### 7.1 Command registry and parser

- A registry entry holds the verb pattern, argument schema, class (`meta`, `read`, `write`), handler, timeout, and the hypotheses or components it relates to (used as context for the comment).
- The parser tokenizes on whitespace, matches against the registry, validates arguments against the lab topology, and rejects shell syntax.
- Errors return a terminal-style message, for example `command not found: ls. Type 'help' to see available commands.`

### 7.2 Endpoints (proposed)

- `GET /api/v1/console/commands`: the catalog, used for `help` and optional autocomplete.
- `POST /api/v1/console/execute`
  - Request: `{ "incident_id", "input", "suggestion_id"?: string, "confirmation"?: "yes" }`
  - Response: `{ "command_id", "status": "ok" | "error" | "needs_confirmation" | "rejected", "output": [lines], "started_at", "finished_at" }`
  - Write commands without a confirmation return `needs_confirmation` with the prompt text. The frontend shows it and resends with `"confirmation": "yes"`.
- Live updates to the Argus panel (analysis status, comments, ranking changes): reuse whatever channel the frontend already uses for incident and map updates (WebSocket, SSE or polling). Confirm which one exists.

Output streaming is optional in stage 1. Commands are short, so returning the full output and rendering it line by line in the frontend is enough.

### 7.3 Write commands and the safety path

1. The operator types a write command. The backend returns `needs_confirmation`.
2. The operator types `yes`. This only confirms the intent; it is **not** an approval. The backend maps the command to exactly one released (capability, target) pair in `write_gate.open` (otherwise it rejects), calls `policy.check`, and creates the normal proposal (or reuses a pending one for the same action).
3. Approval: an approver with a fresh second factor answers the proposal through `POST /api/v1/ops/approvals/{id}/answer`, the one approval path.
4. `AuditSinkPort` records before and after, with `source: "operator_console"`, the operator identity and the `command_id`.
5. The action runs through the existing executor (the restart proxy, or the existing `network.restore` action).
6. The verification step runs as usual. The post-command analysis (section 8) reuses its result.

Open questions on this path are in section 15.

### 7.4 Console event

When a command finishes (success or error), publish an internal event and store it in PostgreSQL:

```json
{
  "type": "console.command.completed",
  "command_id": "uuid",
  "incident_id": "INC-0142",
  "input": "cache restart",
  "command": "cache.restart",
  "args": {},
  "class": "write",
  "suggestion_id": "sug-07",
  "status": "ok",
  "output": ["policy: allowed", "audit: recorded", "restart: cache ok (3.1s)"],
  "output_truncated": false,
  "started_at": "2026-10-29T10:44:02Z",
  "finished_at": "2026-10-29T10:44:05Z"
}
```

- `suggestion_id` is set only when the operator ran an inserted suggestion without editing it. If the text was edited, it's treated as an operator-typed command.
- Output stored for the model is truncated, for example to 4 KB, with `output_truncated` set.

## 8. Post-command analysis loop

Triggered by every `console.command.completed` event, including commands Argus didn't suggest.

1. **Before snapshot.** At command start, record the latest values of the metrics relevant to the command and the active hypotheses.
2. **Settle delay.** Wait `settle_seconds` before sampling. It must respect the Prometheus scrape interval and the two-consecutive-points rule from the scenario plan: `settle_seconds ≥ 2 × scrape_interval + margin`. Configurable per command. Read commands that don't change state can use a short or zero delay.
3. **After samples.** Take two consecutive samples through `MetricsPort` and refresh the relevant map edges.
4. **Evidence.** The model receives the active hypotheses, the command and its output, the before/after metrics and the map changes. It returns structured evidence entries (`hypothesis_id`, `effect: supports | contradicts | neutral`, `reason`, references to the output or metric) plus a short comment of two or three sentences and an optional next suggestion.
5. **Ranking.** The existing deterministic ranking recomputes from the updated evidence. The model does not rank.
6. **Push to the UI.** Status (`waiting` with countdown → `analyzing` → `done` or `error`), the comment, ranking changes and any new suggestion.
7. **Tracing.** Each analysis is traced in Langfuse with the `command_id`.

Grounding rule: the comment may only state what the output or metrics show. If the data is missing or inconclusive, Argus says so.

Where this lives: a LangGraph node such as `observe_operator_action`, resumed by the console event, or a separate handler that writes into the incident state. The PM agent should pick whichever fits the current graph with the least change.

Timeouts: if metrics don't arrive within a set time (for example 60 s), show `Metrics not available yet` and allow a manual re-check.

## 9. Suggestions

Argus produces suggestions as structured data:

```json
{ "id": "sug-07", "command": "cache restart", "rationale": "Cache exited before API errors began", "hypothesis_id": "H1", "class": "write" }
```

Rules:

- Suggestions can only use commands in the registry. Validate them against the parser before showing them.
- **Insert into console** fills the input line and focuses it. It never runs the command automatically.
- **Copy** copies the command to the clipboard.
- Once applied, the card is marked "Applied" and linked to the resulting comment.

## 10. Frontend (React)

The visual spec and sample content are in `argus-console-mockup-spec.md`. Implementation notes:

- **Terminal component:** xterm.js, or a custom monospace input and output panel. Either is fine for stage 1. xterm.js eases the move to stage 2. It needs a prompt, history with up/down arrows, `clear`, the confirmation prompt for write commands, a disabled input while a command runs, and line-by-line rendering.
- **Argus panel:** a hypothesis card with rank transitions, an activity feed with suggestion, status and comment cards.
- **Layout:** about 55/45 split on desktop, stacked on narrow screens.
- **State sync:** the live map and hypothesis views elsewhere in the UI must reflect console actions. They should all read from the same incident state, never from console-local state.

## 11. Work items

Sizes: S ≤ half a day, M ≤ 2 days, L > 2 days.

| # | Item | Size | Depends on | Acceptance (observable in the presentation) |
|---|---|---|---|---|
| 1 | Command registry, parser and allowlist | S | — | `help` lists commands; `ls` and `status; rm` are rejected |
| 2 | Execute endpoint and read commands for scenario 1 | M | 1 | `cache status`, `api cpu`, `host metrics` return real lab data |
| 3 | Write path: confirmation, policy, approval, audit, execute, verify | M | 1 | `cache restart` asks for confirmation, restarts the cache and appears in the audit log |
| 4 | Console event and history persistence | S | 2 | Each command is stored with its output and linked to the incident |
| 5 | Post-command analysis: settle delay, samples, before/after | M | 4 | Status line counts down, then analysis starts after fresh samples exist |
| 6 | Evidence, comment and ranking refresh, with Langfuse tracing | M | 5 | After `api cpu`, H2 is demoted with a grounded comment |
| 7 | Suggestions with Insert and Copy, `suggestion_id` tagging | S | 1, 6 | Insert fills the input; running it marks the card "Applied" |
| 8 | Split-view UI: terminal and Argus panel | M | 2 | Matches the mockup spec; works at 1280×720 |
| 9 | Live updates to the panel through the existing channel | S | 6, 8 | Comment and ranking appear without a page reload |
| 10 | Scenario 4 commands (depends on worker instrumentation) | S | 2, 3 | Frozen worker resolved end to end from the console |
| 11 | Scenario 2 commands (depends on the open card TASK-97) | S | 2, 3 | Wrong network resolved end to end from the console |
| 12 | Error handling: timeouts, metrics unavailable, backend errors | S | 5 | Each failure shows a clear message and the UI recovers |
| 13 | Rehearsal: run each scenario several times and record the results | S per scenario | all | Argus reaches the right ranking and comment on every run |

## 12. Milestones and order

Same order as the scenario plan: scenario 1, then 4, then 2.

1. **M1:** read-only console for scenario 1, with Argus commenting after each command (items 1, 2, 4, 5, 6, 8).
2. **M2:** `cache restart` end to end through the safety path, with Insert and Copy suggestions (items 3, 7, 9). Scenario 1 is fully usable at this point.
3. **M3:** frozen worker from the console (item 10).
4. **M4:** wrong network from the console (item 11).
5. **M5:** hardening and rehearsal (items 12, 13).

## 13. Stage 2 (roadmap, not this stage)

- A real shell (xterm.js + WebSocket + PTY) inside a sandboxed, throwaway container with lab-only access.
- Argus commands stay available as scripts on its PATH that call the same ports.
- The observation hook needs command boundaries from the shell (shell-integration markers such as OSC 133), plus stripping of ANSI codes from the output before analysis.
- The safety model still applies: write operations go through the Argus action path, not raw Docker access.

## 14. Risks and cut lines

**Risks**

- Metrics lag makes Argus report "no change" too early. Mitigation: settle delay and two samples (section 8).
- Model latency creates dead air on stage. Mitigation: visible status line and short comments.
- Ungrounded comments. Mitigation: structured evidence with references, plus the grounding rule.
- Operator typos on stage. Mitigation: Insert button, history and the clear `help` output.

**Cut lines** (drop in this order if we fall behind)

1. Autocomplete, and output streaming (already optional).
2. Scenario 2 write command: fall back to Argus's normal proposal and approval flow for the reconnect.
3. Before/after metric line on the comment cards.

**Minimum version:** scenario 1 console with read commands, `cache restart` through the safety path, and Argus commenting after each command.

## 15. Open questions

1. Does the typed confirmation count as human approval directly, or must a pending Argus proposal exist first?
2. Should operator-initiated write commands also go through the second-opinion reviewer, or only Argus-proposed ones?
3. Which live-update channel does the frontend use today (WebSocket, SSE or polling)?
4. What is the actual Prometheus scrape interval in the lab? It sets the minimum settle delay.
5. Are the worker heartbeat, processed-jobs and queue-depth metrics already exposed?
6. Is the expected topology for scenario 2 read from the compose file or a separate config?
7. Should the console be tied to one incident or available globally with an incident selector?
