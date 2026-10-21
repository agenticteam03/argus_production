# ACR-0024 — Explicit hypotheses and a transparent cause ranking

Area C of the next-phase plan ("statistical reasoning, past cases and cause ranking"). The NEXT-PHASE proposal (#170)
left it as a separate track; this ACR is that track. **Reads and records only:** nothing here writes to a target,
proposes an action or adds an outbound path.

| Field | Value |
|---|---|
| Status | `accepted` with the two approvals of `task/ACR-0024-accepted` (§5); it merges only with both. Not applied: that is T-0047 H1 |
| Proposed by | juanbetancurm (+ agent) · 2026-10-20 |
| Accepted by | a teammate approving `task/ACR-0024-accepted` (`conantkd` approved the proposal as recorded in #202, 2026-10-20) |
| Second approval (safety principle only) | **required**: evidence integrity (a new insert-only table that cites evidence, and a stricter check of the evidence a conclusion cites). A second teammate approving the same pull request |
| Architecture version | the next free version when applied |
| Task / PR | [T-0047](../../tasks/current/T-0047-hypotheses-cause-ranking.md) · #202 (proposed) · `task/ACR-0024-accepted` (accepted) |

## 1. Detect and explain

Argus ends an investigation with **one** answer: `Conclude(diagnosis, evidence_refs, confidence, root_cause_target)`.
What it does not record:
- **The alternatives.** SC-03 (the cache stops, `argus-lab-api` fails) is diagnosed correctly today, but nothing says
  "API crash: ruled out, because its process is up and its probe to the cache fails". The operator sees one sentence and
  must trust it. The UI already has the slot: `GET /api/v1/incidents/{id}` returns `"hypotheses": []` for every incident
  (`argus/application/incident_view.py`, "until the … decision schema exist[s]", ACR-0021 / T-0045 out of scope).
- **Why one cause beats another.** `confidence` is the model's own word (`low` / `medium` / `high`). No number comes
  from the evidence itself, and the evaluation cannot tell a right answer reached by luck from one the evidence
  supports.
- **What the evidence says about each cause.** A conclusion may cite a runbook passage and nothing observed on the
  target it blames. Today that passes: §11.3 only checks that the cited references exist.

Five reads that help compare causes are built and deployed but **offered to no class**: `metrics.cpu_history` (T-0036),
`metrics.compare_baseline` (T-0038), `knowledge.prior_incidents` (T-0039), `analysis.trace_request_path` (T-0040) and
`analysis.diagnostic_snapshot` (T-0034) (`config/policy.yaml`: "offered to no class yet"). EVAL-offers (2026-10-19, 61
cases × 5 trials, one batch per offer) measured several of them: offered alone they are used and change little
(`request_path` 0.72 → 0.74; `baseline` called in 1 of 25 cpu runs), so none was offered. The model reaches for a
comparison read only when it has a competing explanation to test, which is what this ACR adds.

## 2. Why the current architecture is insufficient

- §5.5 `Conclude` and `Escalate` carry no hypotheses; `UseReadTools` carries no statement of what a read is meant to test.
- §11.3: "`evidence_refs` not stored for this incident → `InvalidDecision(malformed)`" is the only evidence rule. A
  root cause backed only by a passage, or a cause blamed on a target never observed, is accepted.
- §10.6 has no slot for the hypotheses under test, so each step starts again from the observations.
- §16.1 stores no hypothesis; §7.1 documents `hypotheses` as empty.
- §21.2 grades "diagnosis accuracy" and "evidence support (rubric-scored)", but not whether the wrong causes were
  ruled out.

## 3. Smallest reasonable change

### 3.1 The decision schema (§5.5)

Before:
```python
class Conclude(BaseModel):
    kind: Literal["conclude"]; diagnosis: str; evidence_refs: list[EvidenceRef]
    confidence: Literal["low", "medium", "high"]
    root_cause_target: TargetRef | None = None

class Escalate(BaseModel):
    kind: Literal["escalate"]; reason: str; evidence_refs: list[EvidenceRef]
```
After:
```python
class Hypothesis(BaseModel):                # ACR-0024: one candidate explanation
    id: str                                 # "h1".."h5", stable across the steps of one incident
    statement: str                          # ≤ 200 chars
    cause_class: str                        # an incident class name, or "other"
    target: TargetRef | None                # in the incident's scope
    relation: Literal["self", "dependency", "host", "external"]
    status: Literal["supported", "ruled_out", "untested"]
    support: list[str] = []                 # evidence ids for it
    against: list[str] = []                 # evidence ids against it

class Conclude(BaseModel):
    kind: Literal["conclude"]; diagnosis: str; evidence_refs: list[EvidenceRef]
    confidence: Literal["low", "medium", "high"]
    root_cause_target: TargetRef | None = None
    hypotheses: list[Hypothesis] = []       # ≤ 5; required by model_loop strategies (§10.3)
    chosen: str | None = None               # the hypothesis id the diagnosis is

class Escalate(BaseModel):
    kind: Literal["escalate"]; reason: str; evidence_refs: list[EvidenceRef]
    hypotheses: list[Hypothesis] = []       # what was considered before giving up

class UseReadTools(BaseModel):
    kind: Literal["use_read_tools"]
    calls: list[ReadCall]
    hypotheses: list[Hypothesis] = []       # optional: the list as it stands, so the next step continues it
```
Deterministic strategies (`evidence_pack`, the §21.2 baseline) keep producing decisions without hypotheses; the field
is optional in the schema and required by the harness for `model_loop` / `plan_then_reason` / `confirm_then_reason`
conclusions (§11.3 below).

### 3.2 Validation in the harness (§11.3, new rows)

| `ModelReply` | Result |
|---|---|
| a hypothesis cites an evidence id not stored for this incident, or the same id both for and against | `InvalidDecision(malformed)` |
| a `supported` hypothesis without an observation or metric snapshot **of its own target** (for `relation: host`, of that host) among `support`; or a `ruled_out` one without an `against` | `InvalidDecision(malformed)` |
| a model-strategy `conclude` with a `root_cause_target` but no `chosen`, or a `chosen` that is not `supported` or whose target is not the `root_cause_target` | `InvalidDecision(malformed)` |
| a hypothesis with `target: null` whose `relation` is not `external` | `InvalidDecision(malformed)` |
| an `external` hypothesis that is `supported` without an observation or metric snapshot of a target **in scope** (the effect Argus saw) among `support`; or an `external` hypothesis as `chosen` | `InvalidDecision(malformed)` |
| more than 5 hypotheses | `InvalidDecision(malformed)` |

A runbook passage or a prior incident is never evidence for a hypothesis (they are not `EvidenceRecord`s, §5.4); they
stay in `evidence_refs` as today. The retry bound of §11.3 applies unchanged.

**An external cause** (`relation: external`, the only relation that may have `target: null`: a provider outage, a
network outside the inventory) is something Argus cannot observe directly. It may be `supported` by what Argus saw on a
target in scope, and it is ranked like any other hypothesis, but it can never be `chosen`: a conclusion needs a
`root_cause_target` Argus observed. When the evidence favours an external cause, the run ends in `escalate` with the
hypotheses, and the operator sees the external one ranked first.

### 3.3 The support score (new, `application/ranking.py`; weights in `config/ranking.yaml`)

Per hypothesis, computed in Python after validation, never by the model:

`score = Σ weight(each counted supporting record) − Σ weight(each counted record against) − untested_penalty`

- Initial weights (data, reviewed like the policy; `config/ranking.yaml` is added to `SELF_MERGE_PROTECTED`):
  an observation of the hypothesis's own target 3; a metric snapshot of it 2; an observation of another target in
  scope 1; an alert 1; a peer finding 1; a reported symptom 0.5; `untested_penalty` 0.5.
- **Citing more does not score more.** Per hypothesis and side (for, against), the **generic kinds** (an alert, a peer
  finding, a reported symptom, an observation of another target) count **once per kind**, however many records of that
  kind are cited. Observations and snapshots of the hypothesis's own target count once per distinct record, up to
  `max_target_records` (3). So a hypothesis cannot climb by citing every alert of the incident.
- The hypotheses are ranked by score. Ties: more distinct supporting records that **no other hypothesis cites** (a
  record shared by several hypotheses tells them apart from nothing), then the order given.
- Shown as **"supported by N, contradicted by M"** with the rank and a bar, **never as a percentage or a probability**.
- The ranking never changes the conclusion, the outcome or the routing. When the chosen hypothesis is not ranked
  first, the incident records `ranking_disagrees: true` and the UI says so ("the evidence favours h2"); the operator
  decides. Calibration of the weights waits for confirmed outcomes (T-0048).

### 3.4 Working memory (§10.6, a new slot)

| Slot | Bound *(default)* | Rule |
|---|---|---|
| Hypotheses under test | ≤ 300 tokens | the latest decision's list (statement, status, cited ids); never dropped once present |

### 3.5 Storage (§16.1 row 2; a new migration, `<next free number>_incident_hypothesis.sql`)

`incident_hypothesis`: one row per hypothesis per decision step (`incident_id`, `step`, `hypothesis_id`, `statement`,
`cause_class`, `target`, `relation`, `status`, `support_ids`, `against_ids`, `score`, `rank`, `chosen`, `at`).
Insert-only for the runtime role (SELECT, INSERT), like evidence and audit; `db-check` proves it. SQLite gets the same
table with insert-only triggers.

### 3.6 The incident answer (§7.1, `GET /api/v1/incidents/{id}`; no new route)

`hypotheses` is filled from the final decision's rows: `[{id, statement, cause_class, target, relation, status, rank,
chosen, support: {score, for, against}}]`, plus `ranking_disagrees`. Operators and approvers also get the cited
`evidence_id`s (`support_ids`, `against_ids`); a viewer gets the counts only, as for `evidence_highlights`.

### 3.7 Deterministic facts: `analysis.anomaly_summary` (§12.2, a new Level 3 row)

| Tool | Capability | Executor | Notes |
|---|---|---|---|
| `summarize_anomalies` | `analysis.anomaly_summary` | `prometheus` | the class's signals (`config/ui-incident-signals.yaml`) on the target and its declared dependencies, incident's host only: onset (first two consecutive points past the warning line), deviation from the B7 baseline (p95), and which onset came first; facts with numbers, never a conclusion; `max_per_incident` 1; tag `anomaly` |

### 3.8 Evaluation (§21.2)

- Case labels gain `expected_hypotheses: {supported: [...], ruled_out: [...]}` (cause classes or targets).
- New metrics: top-1 and top-3 root-cause accuracy over the ranking; ruled-out recall; `ranking_disagrees` rate.
- New hard check: `unsupported_root_cause` = 0 (a conclusion whose root cause has no observation of its target).
- The built reads of §1 are measured again **with** hypotheses (H4): an untested hypothesis is exactly what a
  comparison read tests. A read is offered to a class only when that batch improves it (T-0047 H4; offering itself
  needs no ACR, they are §12 Level 3 rows already).

### 3.9 Not in this ACR

Case similarity over **confirmed** past incidents and a prior from them (needs reviewed outcomes: T-0048); external
knowledge (ACR-0022 §3.4–3.5); actions (ACR-0019); a fully deterministic `hypothesis_checklist` strategy (§10.3, later,
once runbooks carry machine-readable hypothesis lists).

**Alternatives considered:**
- A — keep one diagnosis and let the UI list the runbook's other causes as "hypotheses": no evidence links, so it would
  look like reasoning without being any.
- B — ask the model for a probability per cause: uncalibrated, and shown as a percentage it would be read as a
  measurement.
- C — a Bayesian network over the classes: needs labelled frequencies we do not have (a handful of real incidents).
- D — hypotheses only in `conclude`: the next step could not continue the list; the optional field on `UseReadTools`
  costs nothing for strategies that ignore it.

## 4. Consequences

- **Code:** `domain/decisions` (the models), `tooling/model_harness.py` (decision tool schemas, the §3.2 checks),
  `orchestration/context.py` (the slot), `application/ranking.py` (new), `application/incident_view.py` (fill
  `hypotheses`), the stores (the new migration), `capabilities/catalog.py` (`analysis.anomaly_summary`), `config/ranking.yaml`
  (new), `brain/tools/brain.py` (`SELF_MERGE_PROTECTED`), the system prompt (how to state hypotheses).
- **Tests:** harness refusals (fabricated id, a root cause without a target observation, ruled out without against,
  chosen not supported, `target: null` that is not external, an external hypothesis chosen); an external cause ranked
  first ends in `escalate`; two hypotheses, one citing every alert, ranked by the target observation and not by the
  alerts; ranking determinism and weights; insert-only table; viewer redaction; `anomaly_summary`
  onset and order on fixtures; evaluation SC-03 (cache supported, API crash ruled out), SC-07 (network
  misconfiguration supported, backend down ruled out), SC-05 (the alerted mount, not `/`). Accuracy not below today's
  and every hard check at 0.
- **Contract:** `contracts/ui-api.json` and the incident sample (additive fields).
- **Deployment:** the new migration before the new image on vm-095; nothing on vm-166.
- **Risk:** more `InvalidDecision(malformed)` retries while the prompt learns the format (measured in the evaluation
  before the harness rule is enforced; until then the rule logs only). Longer replies (≤ 5 short hypotheses).
- **Reverse:** the field is optional; turning the harness rule to log-only and hiding the UI tab restores today's
  behaviour; the table stays (insert-only, forward-only migrations).
- **Safety principle:** evidence integrity — **yes** (it adds a stored record that cites evidence and makes the
  evidence rule stricter; it never edits evidence). Read-only, write gate, host isolation, secrets: no change.

## 5. Decision

Proposed in #202, where `conantkd`'s review asked for changes (`target: null` only for an external cause, which is
never chosen; generic evidence counted once per kind so citing more does not score more; ties on records no other
hypothesis cites; the next free migration number; ARCHITECTURE applied with the first code; a class-registry change
never self-merged) and approved the text as recorded. **Accepted as written** with the two approvals of
`task/ACR-0024-accepted`: one teammate's, plus a second one for evidence integrity.

The harness checks of §3.2 start log-only (T-0047 H1) and are enforced only when the evaluation shows they do not
lower accuracy (H4).

Next: T-0047 H1 applies this ACR to `ARCHITECTURE.md` with its first code (§6).

## 6. Applied

- [ ] `ARCHITECTURE.md` updated (§5.5, §7.1, §10.6, §11.3, §12.2, §16.1, §21.2), version bumped, changelog line added
- [ ] journal entry
- [ ] the ACR, the architecture change and the first code that needs it are in the same pull request
