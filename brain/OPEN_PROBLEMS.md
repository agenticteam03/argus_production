# Open problems and pending team decisions

When a problem is fixed, set its status to `fixed` with the date, and add a journal entry if it is significant.
**Status:** `open` · `in progress` · `fixed` · `dropped` (with reason) · decisions: `pending` · `decided`

| ID | Item | Status | Opened |
|---|---|---|---|
| **D-001** | Cross-host path and alert direction: architecture text vs the running system | **pending team decision** | 2026-10-02 |
| **D-002** | Move the runbook library into this repository (the architecture expects it there) | **decided and done** 2026-10-02 | 2026-10-02 |
| OP-001 | Runbook `detector` metadata uses old or empty class names | open | 2026-09-30 |
| OP-002 | P0 safety gaps of the runbook library not yet reconciled with architecture v1.8 | open | 2026-09-30 |
| OP-003 | Runbook safety classes not mapped to `CapabilitySpec.risk` | open | 2026-09-30 |
| **OP-005** | The `restarts_10m` signal undercounts restarts of a container younger than its window | **proposed — awaiting approval (conantkd)** | 2026-10-05 |

---

## D-001 — Cross-host path and alert direction (pending team decision)

**Status:** pending · **Opened:** 2026-10-02 · **Decided by:** the whole team (including `conantkd`)

**The difference.** Architecture §3.6 (reference values) says the two hosts talk over the **private network with no
tunnel**, and that alerts are **pushed** (Alertmanager on vm-166 → webhook on vm-095). The running system uses a
**restricted SSH tunnel** over port 22 (the only port open between the VMs) and **pulls** alerts through it
(`ReconcileFiringAlerts`), because the cloud network rules cannot be changed by the team.

**Options.**
- **A. Keep the architecture text; change the deployment later.** If someone with access to the cloud console opens
  the needed ports between the private addresses, switch to the private network and push alerts. Only the inventory
  URLs, the compose port bindings and the alert route change; the tunnel is removed.
- **B. Change the architecture to match the running system** through an ACR (§3.6: SSH tunnel, pulled alerts).
- **C. Use the existing WireGuard tunnel** — only with `conantkd`'s agreement, since it belongs to the protected
  deployment.

**Until decided:** the running system stays as it is (tunnel + pull). Nobody changes the architecture text or the
transport alone.

**Done when.** The team has chosen; the result is either an accepted ACR (B) or a planned task (A or C), recorded in
the journal.

---

## D-002 — Move the runbook library into this repository

**Status:** decided and done (2026-10-02, owner: deploy keys are disabled in the organization, so CI could not read
the separate repository; moving the library removes the need) · **Opened:** 2026-10-02

**The difference.** Architecture §2.4 places the runbooks in the code repository (`argus/runbooks/`, "reviewed copy
of the runbook library v1.1.0" + `RUNBOOK-CONVENTIONS.md`). The running system reads them from a separate private
repository (`agenticteam03/runbooks`, pinned in `config/runbooks.lock`). That came from an implementation choice on
2026-09-30 ("read in place, never copied") and the shared-Brain plan decision D2, not from the architecture. It costs
a deploy key for CI, a deploy key per VM, and a pin bump plus a second repository for every runbook change.

**Done.** Moved (without history: the old repository keeps it; provenance in `argus/runbooks/README.md`) the reviewed runbooks (RB-001…RB-021, `RUNBOOK-CONVENTIONS.md`, `RUNBOOK-INDEX.md`) into
`argus/runbooks/` with their history (`git subtree`), keep each runbook's own `version` in its metadata (already
recorded in the recall audit), deploy them with the code, retire `config/runbooks.lock` and the CI deploy key, and
leave the research material (books, assessments, gap backlog) in the old repository as history. OP-001 is then fixed
in this repository.

**Alternative.** Keep the separate repository (works today; costs as above).

**Done when.** Decided; if yes, done as one task (tests: recall finds every class's runbooks from `argus/runbooks/`;
deployment no longer mounts `/opt/argus-runbooks`) and the journal records it.

---

## OP-001 — Runbook `detector` metadata uses old or empty class names

**Status:** open · **Opened:** 2026-09-30

**Problem.** Each runbook in the library (`agenticteam03/runbooks`, `runbooks/RB-*.md`) has a `detector:` field. It
still uses v1.7 names or is empty: RB-001 `oom_restart_loop` (v1.8: `container_restart_loop`, shared with RB-008);
RB-002 `health_check_failed` and RB-003 `dependency_unavailable` already match; RB-004…RB-021 `null`. Architecture
§15.3 requires that "a runbook's `detector` metadata names the class that uses it".

**Fix.** In the runbooks repository: set `detector:` in every runbook to its v1.8 class (§1.3); bump `version` and
`last_reviewed`; update `RUNBOOK-INDEX.md`. Now done in this repository (`argus/runbooks/`), through a pull request.

**Done when.** All 21 runbooks name a class that exists in §1.3, and a check shows no class without a runbook and no
runbook without a class.

---

## OP-002 — P0 safety gaps not yet reconciled with architecture v1.8

**Status:** open · **Opened:** 2026-09-30

**Problem.** The library's `ARGUS-CAPABILITY-GAPS.md` lists eight **P0** gaps written against an older code base.
Each must be settled in the architecture (ACR) before the related implementation. First assessment — to be verified:

| Gap | Asks for | Against v1.8 | Likely change |
|---|---|---|---|
| G-001 Deployment profiles | named, versioned profiles (production / lab); missing profile fails closed | partial: per-(capability, target) write gate, no profile | `profile` in the policy file; write gate evaluated per profile |
| G-002 Typed prerequisites | preconditions as typed predicates on fresh, identity-bound evidence | **missing**: §13.1 uses free-text `preconditions` | typed predicates evaluated at `propose_action` and `precheck_action` |
| G-003 Observation provenance | source vs collection time, coverage, units, partial state, identities | partial | add the fields to `Observation` / `EvidenceRecord`; missing is never zero or healthy |
| G-004 Approval binding | immutable proposal bound to what it acts on, previews | mostly covered | extend `identity()`; preview in the approval view |
| G-005 Verification windows | stability windows, provisional vs final recovery | partial | `stability_window` per class; provisional/final states |
| G-006 Data minimization | per-source field allowlists, literal redaction | partial | `allowed_fields` per `CapabilitySpec` |
| G-007 Helper semantics | missing/partial data never becomes healthy or root cause | principle missing (implemented for metrics freshness) | state the rule in §12.3; contract fixtures |
| G-008 Corpus/dispatcher separation | runbook IDs from metadata, bounded passages, tools never from runbook text | covered by §15.3 | verify that writes are offered only for registered classes |

**Done when.** Each gap is covered, changed through an ACR, or dropped with a reason.

---

## OP-003 — Runbook safety classes not mapped to `CapabilitySpec.risk`

**Status:** open · **Opened:** 2026-09-30

**Problem.** The library's conventions classify operations as `READ_ONLY_SAFE`, `READ_ONLY_SENSITIVE`,
`MUTATING_LOW_RISK`, `MUTATING_HIGH_RISK`, `FORBIDDEN`; architecture §12.3 uses `risk: low | medium | high | very_high`
plus `permission: read | write_hitl`. They do not map cleanly (sensitive reads need allowlists; `FORBIDDEN` has no
equivalent).

**Fix (to discuss, ACR).** Adopt the five classes as `safety_class`, derive `permission` from it; sensitive reads get
mandatory field allowlists (ties to G-006); `FORBIDDEN` operations are never registered; classify every capability in §12.2.

**Done when.** §12.3 has one scheme; every capability has a class; policy and redaction rules refer to it.

---

## OP-005 — `restarts_10m` undercounts young containers (proposal, awaiting approval)

**Status:** proposed · **Opened:** 2026-10-05 · **Found by:** `conantkd` (T-0013 review) · **Approval:** this PR

**Problem.** `config/signals.yaml` computes `restarts_10m` as `max_over_time(count[10m]) - min_over_time(count[10m])`.
For a container that has existed for less than 10 minutes, the first sample Prometheus has is often already above 0
(the container restarted before the first scrape, every 15 s), and those restarts are lost. Observed in T-0013 step 5:
Docker counted 3 restarts while the signal said 1 (first run) and 2 (the reviewer's run), so the restart-loop class
(threshold 3) did not match and SC-01 was escalated as unsupported until enough time passed. The observed metric did
not match what really happened.

**Proposed solution — an improved calculation:** count from zero when the series is younger than the window.

```text
restarts_10m = clamp_min(
    count - (count offset 10m  or  count * 0),
  0)
where count = argus_container_restart_count{argus_host="$host",container="$name"}
```

- the series existed 10 minutes ago: the restarts of the last 10 minutes (same as today);
- the container is younger than 10 minutes (`offset 10m` has no value): all its restarts, which all happened inside
  the window — the value then equals Docker's own counter;
- `clamp_min(..., 0)` keeps the value at 0 when a container is recreated and its counter starts again from 0.

The S5.6 readiness gate in `code.bash` (T-0013) uses the same expression and changes with it.

**Alternatives.** Wait longer before diagnosing (a workaround, not a fix: the value stays wrong) · let the exporter
publish restarts-since-creation directly (moves the logic out of the signal catalogue, where every signal lives).

**Done when.** Approved here; then a task changes `config/signals.yaml` (+ a test that the signal text is the approved
one) and verifies on vm-166 with SC-01: right after the third restart the signal shows 3, the same as Docker, and
SC-01 is diagnosed without extra waiting.
