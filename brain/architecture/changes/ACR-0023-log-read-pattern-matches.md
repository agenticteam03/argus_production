# ACR-0023 — A log read also brings the pattern matches outside its tail

| Field | Value |
|---|---|
| Status | `proposed` |
| Proposed by | conantkd (+ agent) · 2026-10-19 |
| Accepted by | — |
| Second approval (safety principle only) | not needed (no safety principle touched, §4) |
| Architecture version | 1.8.16 → 1.8.17 |
| Task / PR | EVAL-offers · PR #179 |

## 1. Detect and explain

EVAL-offers added six health cases whose container log has about 250 lines, with the cause once and outside the
tail that `container.logs` returns (50 lines by default). On `main`'s behaviour (G0, `eval-20261019-101505.jsonl`)
the model misses causes it never sees: `health-api-vm166-01-longlog` 1/5, `health-api-vm095-01-longlog` 0/5.

The tool that finds such a line exists (`container.search_logs`, T-0037), but offered to `health_check_failed` the
model called it in 4 of 50 health runs (F4). An agent that must find the cause without a runbook telling it to search
does not get there by being offered one more tool.

Measured (H1, `eval-20261019-121648.jsonl`, 61 cases × 5 trials, compared with G0): the change alters the evidence of 3
cases, the three whose cause matches a named pattern outside the tail:

| case | G0 | H1 | the model's diagnosis in H1 |
|---|---|---|---|
| `health-api-vm166-01-longlog` | 1/5 | 5/5 | all 5 cite `KeyError: 'FEATURE_FLAGS'`, the line outside the tail |
| `health-api-vm095-02-longlog` | 5/5 | 3/5 | all 5 name the real cause, `address already in use` (G0's passes never saw it); 2 escalated with it |
| `health-db-vm166-01-longlog` | 5/5 | 5/5 | — |

The other 58 cases read exactly the same evidence; their changes (for example `restart-exit0-job-01` 5/5 → 2/5 with
identical reads) are the run-to-run noise of 5 trials. Hard checks 0 0 0.

## 2. Why the current architecture is insufficient

§12.2, the catalogue: `get_container_logs` | `container.logs` | `docker_read` | "tail-bounded, redacted". A read bounded
to the tail cannot show a cause that the process logged once and then buried under repeated symptoms, which is the
usual shape of a real incident's log.

## 3. Smallest reasonable change

§12.2: "tail-bounded, redacted" → "tail-bounded, redacted; plus the lines of the last 30 min (at most the gateway's 500)
that match a named failure pattern (`error`, `timeout`, `refused`, `oom`, `disk_full`, `auth`) and are not in the tail:
counts per pattern and the last 6 lines (ACR-0023)".

The capability calls the gateway's existing `search` route once per pattern; no new route, no new permission, no
gateway change. The lines go into the read's text, which the model always sees (a read's values reach the model only for
the last four reads, cut at 1800 characters). A failed search leaves the tail read as it was.

**Alternatives considered:**
- A: keep the architecture and offer `search_logs` to the classes. Measured: the model rarely calls it (4 of 50).
- B: tell the model to search in a runbook or the prompt. It works only for classes with that text, and the aim is an
  agent that does not depend on runbooks to look in the right place.
- C: one new gateway route answering tail and matches together (one call instead of seven). Cleaner on the wire, but a
  gateway change that needs an AFTER-MERGE on both VMs and was not the measured version. It can replace this later
  without changing what the model sees.

## 4. Consequences

- Code: `argus/capabilities/catalog.py` (`container_logs`, `LOG_SCAN`); tests `tests/test_acr0023_log_matches.py`;
  `tests/test_core.py`'s fake records parameters (a log read searches one path per pattern).
- Each `container.logs` read makes up to 6 more gateway requests (the search of a ≤ 500-line window). The budget is
  per capability (`max_per_incident`), unchanged.
- More log text reaches the model: up to 6 lines of 200 characters, through the same redaction as every read.
- Risk: a matching line that is not the cause can lead the model to the wrong cause. `ambiguous-health-no-cause` and
  its long-log twin measure it (no lower than G0's noise band in H1).
- Reverse: restore the old `container_logs` (one function); nothing is stored differently.
- Safety principle touched? **No.** Read-only, the same container on the same host, redacted like every read.

## 5. Decision

Pending: the team's review in PR #179.

## 6. Applied

- [x] `ARCHITECTURE.md` updated (§12.2), version 1.8.17, changelog line
- [x] journal entry (`2026-10-19-EVAL-offers.md`)
- [x] the ACR, the architecture change and the code in the same pull request
