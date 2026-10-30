# The Operator console

A guide for the person who types in it and for the person who reviews it. It describes what is **merged on `main`**.
Anything still in review is marked **(in review: PR #NNN)** and is not claimed to work. The decisions behind it are in
[ACR-0043](../brain/architecture/changes/ACR-0043-operator-console.md); the routes are in [API-FOR-UI.md](API-FOR-UI.md).

## What it is, and what it is not

The Operator console is a small terminal for one incident, in a side panel on the right of the page. It opens from
**Tools → Console**, or from **Open console on <host>** on an incident. You type a command, Argus runs it through the
tools it already has and shows the real output. Next to it, Argus keeps its own view of the incident and comments on
what each command showed.

Opening it takes a reason, which is recorded. The panel then shows a 30-minute countdown that ends the session.
**Disconnect** ends it earlier. Each incident gets its own tab, and the panel can be widened, minimized or shown full
screen.

- It **is** a restricted command console over Argus's own tools. Every command is in a fixed list, and each one maps to
  a capability or a port Argus already has (a container status, a metric, the declared topology).
- It is **not** a shell. There is no operating-system shell, no pipe, no redirect, no script, no `ls`, no variables.
  Input such as `status; rm` is refused before anything runs.
- The full shell is **stage 2**, a separate decision. This guide is only about stage 1.
- Argus never types in the console. A suggestion can only fill the input line; the person presses Enter.

## The commands

`help` prints this list from the registry (`argus/console/registry.py`). Commands are typed in lower case; `--since`
takes a time as `HH:MM` (UTC, at most 120 minutes back; without it a read looks back 30 minutes). `<service>` is one of
`api`, `cache`, `worker`.

| Command | Class | Scenario | What it shows | Where the answer comes from |
|---|---|---|---|---|
| `help` | meta | all | The command list | The registry |
| `clear` | meta | all | Clears your screen only; the stored history stays | Nothing is read |
| `history` | meta | all | The commands typed in this incident | The stored history |
| `status` | read | all | State and health of the three lab services | `container.status` for each |
| `map <service>` | read | all | The service's dependency edges, their state and when they changed | The live map (topology) |
| `cache status` | read | 1 | State, health, restarts, and since when (when it stopped, or started) | `container.status` |
| `api errors [--since HH:MM]` | read | 1 | How many log lines match `error`, `timeout`, `refused`, and the last of each | `container.search_logs` |
| `api cpu [--since HH:MM]` | read | 1 | The API's CPU history, when it started to rise, and the latest value | `metrics.cpu_history`; the onset is computed from its points |
| `host metrics` | read | 1 | CPU, memory and disk of the lab host | `host.cpu`, `host.memory`, `host.disk_usage` |
| `worker status` | read | 4 | State and health of the job worker | `container.status` |
| `worker heartbeat` | read | 4 | Time since the worker last processed a job | The metric `worker_last_processed_age_s` |
| `worker throughput` | read | 4 | Jobs a minute now, against ten minutes ago | The metric `jobs_processed_rate` and its history |
| `queue depth` | read | 4 | Queue depth and its trend over three minutes | The metric `queue_depth` and its history |
| `net inspect <service>` | read | 2 | The networks a service is attached to | `container.status` |
| `net expected <service>` | read | 2 | The networks it should be on, from the declared inventory | The inventory, as the status read reports it |
| `net diff <service>` | read | 2 | Expected against actual networks | Both of the above |
| `cache restart` | write | 1 | Brings the cache back; accepted only while the cache is stopped | Action `container.start` on the cache |
| `worker restart` | write | 4 | Restarts the job worker | Action `container.restart` on the job worker |
| `net reconnect api` | write | 2 | Puts the API back on its expected network | Action `network.restore` on the API |

Output is always read from the source in the last column. A command that cannot read its source says so, with a reason,
and does not make up an answer.

## How a write works

A write never runs because you typed it.

1. You type the write command, for example `cache restart`.
2. The console does not run it. It answers `needs_confirmation` with a prompt, and the prompt changes to `confirm>`.
3. You type `yes`. The console resends the same input with a confirmation. This creates the **normal proposal** for that
   action (the same card, policy check and audit as a proposal Argus makes itself), or reuses the pending one for the same
   action. A typed `yes` confirms your intent. It is **never an approval**.
4. The second-opinion reviewer (the judge) looks at the proposal as for any proposal. Its verdict and wait time are
   shown in the console. A `doubt` reaches the approver; only a `disagree` stops it (ACR-0039).
5. An **approver** answers the proposal in the existing approvals screen, with the approver role and a fresh passkey
   step-up.
6. The worker executes the released action through the action gateway, and the normal verification runs.

Limits that hold at every step:

- A write command maps to exactly **one** released (capability, target) pair. The console can never reach a pair outside
  the release list (`write_gate.open`).
- `cache restart` means `container.start` and works **only while the cache is stopped**. On a running cache it is
  rejected, because a restart of the cache is not a released action.
- A write needs an open incident and the permission `propose_action` (a session completed with a passkey). A reader
  cannot type a write.
- Proposals for one incident are made one at a time, and an incident has **one active proposal**. A write for another
  action is refused while one is pending.
- Every refusal (no `propose_action`, a pair outside `write_gate.open`, a closed incident, `cache restart` on a running
  cache) is stored in the history and audited.

## What Argus does after a command

Each read that answered `ok`, and each write whose action has run, gets Argus's comment, shown under the command in
the Argus panel. The analysis runs in the background: the command's answer never waits for it.

In order:

1. When the command starts, Argus records the related metrics and the incident's hypotheses.
2. It waits for the metrics to settle. For a read there is no wait. For a write the wait is **45 seconds after its
   action has run** (two scrape intervals of 15 s plus margin). A write that has only created a proposal is not
   analysed: it waits, with no comment, until the approved action has run. If that action failed or is
   indeterminate, it gets an `error` that cannot be retried ("The action did not complete, so there is nothing to
   compare").
3. It takes two metric samples 15 s apart (within 60 s), and gives the model the command, its output and the before
   and after.
4. The model returns structured evidence (for or against a hypothesis, each citing the output or a metric), a comment of
   two or three sentences, and maybe a suggested next command. Anything that does not cite a real source is dropped.
5. The evidence is added to the incident, and the **deterministic ranking recomputes**. The model never ranks.

The panel shows one of four statuses under each command:

| Status | You see |
|---|---|
| `waiting` | "Waiting for metrics to settle", with a countdown |
| `analyzing` | "Argus is analysing the result" |
| `done` | The comment |
| `error` | "Analysis unavailable" and the reason, and **Re-check** when it can be retried |

The rule for every comment: **it may only state what the output or the metrics show.** If the data is missing or
inconclusive, Argus says so. A failing model or missing metrics give an `error`, never an invented comment, and the
command's own result is never changed by the analysis. **Re-check** runs a retryable analysis again, one at a time per
command: a second click while it runs, or a re-check of an analysis that cannot be retried, is refused (409). A
suggestion card offers **Insert** (it fills the input line) and **Copy**.

## Who may use it

- A **person**, on their **own session**, through the **private path** (the same private route as the approvals
  screen). The public edge answers 404.
- **Reads** need the permission `investigate`: the roles `operator` and `approver`. A `viewer` is refused. The UI
  offers the side panel to an **approver** only, after the security-key checks.
- **Writes** need `propose_action` (the `approver` role in a passkey session); an operator who is not an approver cannot
  type one. Approving needs the approver role and a fresh second factor, as for any proposal.
- Service and agent principals are refused, and so is a token limited to `read` or `investigate` scope.

The switches (all off or default as listed):

| Setting | Where | Meaning |
|---|---|---|
| `ARGUS_OPERATOR_CONSOLE=1` | `hosts.env` on vm-095 | Turns on both the API's console routes and the UI build (`deploy/ui/compose.ui.yml` passes it as `VITE_ARGUS_CONSOLE`). **Off by default**: the routes answer 404 and the UI makes no console call |
| `ARGUS_CONSOLE_ANALYSIS` | The API | On by default; `0` switches the analysis off |
| `ARGUS_CONSOLE_ANALYSIS_WORKERS` | The API | 2: analyses sampling or calling the model at the same time (a waiting analysis holds no slot) |
| `ARGUS_CONSOLE_READS_PER_MINUTE` | The API | 20 reads a minute per person |
| `ARGUS_CONSOLE_READS_PER_HOUR` | The API | 200 reads an hour per person |
| `ARGUS_CONSOLE_INCIDENT_READS` | The API | 60 console reads for one incident, separate from the investigation's own budget |

`help`, `history` and `clear` are not counted. The console reads only the lab host (`ARGUS_CONSOLE_HOST`).

## How it is recorded

- **History**, per incident: every command with its input, the command id and class, the status, the output (stored
  cut at 4 KB, with a flag when cut), the person and the times. A refused input is stored too, with status `rejected`
  and the refusal as its output. The `history` command and the history route read it back.
- **Audit**, for every call, with `source: operator_console`, the person, the incident and the command id: `console.command`,
  `console.refused`, `console.quota_refused`, `console.budget_refused`. For a write the audit records who **proposed**
  and who **approved**, so a review can see when they are the same person.
- **Sessions**: `console.session_opened` (the person and the reason) and `console.session_closed` (disconnect, time
  limit or sign-out) are audit rows of the incident, shown in its Audit tab. They are a record, not a gate.
- **Refused use**: when a signed-in viewer, service, agent or narrowed token tries the console, the attempt is audited
  as `security.console_refused`, which is sent to the team's Telegram route.
- **The analysis** is stored per command, and its evidence becomes part of the incident.

## Known limits

- Stage 1 only: a restricted console, not a shell.
- **One person may type a write and approve it.** An approver can both propose and answer. That is a deliberate,
  recorded reduction of control for the lab console, written down in ACR-0043 section 5.4; the
  audit shows when it happened, and a two-person rule is to be built before the console is enabled outside the lab.
- Metrics lag. A scrape is 15 s apart, so Argus waits and samples twice; a comment made too early can say "no change".
- Reads are allowed on any existing incident, closed ones included, so a demo is not blocked when Argus closes an
  incident quickly. Writes need an open one.
- **Not verified on the lab.** The console has been tested with fakes. Not yet checked on the real lab: that the API
  process can run a read with its production wiring, the metric names and timing, the model credential in the API
  process, the passkey approval, and the end-to-end scenarios. The rehearsal plan lists each as unconfirmed. The
  database migrations for the history and the analysis run for real only in CI.

## Troubleshooting

- **No Console entry in Tools.** Check, in order:
  1. `ARGUS_OPERATOR_CONSOLE=1` is set, and the API and the UI image were rebuilt or recreated with it.
  2. Your role is `approver`.
  3. The access dialog's checks pass (two security keys, then a confirmed private session).
- **A 429 (too many requests).** You passed 20 reads a minute or 200 an hour. The answer carries `Retry-After`: wait
  that long.
- **"read budget for this incident reached (60)".** This is a `rejected` answer, not a 429: the incident's own console
  read budget is used up (`console.budget_refused` in the audit).
- **"Metrics not available yet".** Two metric samples did not arrive within 60 seconds after the settle delay (the metric
  store is down or stale). The command's own result is unaffected. Use **Re-check** once the metrics are back.
- **A refused input.** The console prints why and nothing ran. `command not found: ...` means the verb is not in the
  list; `syntax not allowed: ...` means the input held shell syntax; `unknown service: ...` lists the known services.
  Type `help` for the list.
