# ACR-0027 — Write down what is built: the policy profile, observation provenance, unknown is never healthy

Settles three gaps of [OP-002](../../OPEN_PROBLEMS.md) (G-001, G-003, G-007) that the code already implements as
"lab additions" (`argus/domain/model.py`, `argus/policy/engine.py`) but the architecture never states. Found by the
OP-002 review (#212).

| Field | Value |
|---|---|
| Status | `proposed`; applied in the same pull request (§6), accepted with its approval |
| Proposed by | conantkd (+ agent) · 2026-10-20 |
| Accepted by | — |
| Second approval (safety principle only) | not required: no rule changes, the text now says what the code does (§4) |
| Architecture version | 1.8.21 → 1.8.23 (1.8.22 is ACR-0026, #210; whichever merges second orders the changelog rows) |
| Task / PR | OP-002 · `task/ACR-0027-built-gaps` |

## 1. Detect and explain

- **G-001, profiles.** `config/policy.yaml` declares `profile: production`; `PolicyEngine` refuses to start unless it
  is `lab` or `production` (`argus/policy/engine.py:23`). §13.1 shows neither the field nor the rule. ACR-0018 makes
  separation of duties depend on the profile, so the text must say what a profile is.
- **G-003, provenance.** `Observation` and `EvidenceRecord` carry `source_time` (when the source measured, `None` if
  unknown) and `collected_at` (when Argus received it), and an observation also `units`, `partial`, `coverage` and
  `identities` (`argus/domain/model.py:115–157`). The model sees `source_time` and `partial` in each `<evidence>`
  tag (`argus/orchestration/runner.py:322`). §5.4 and §12.3 still show one `observed_at` and none of the rest.
- **G-007, unknown is never healthy.** A missing metric is `None`, never 0 (`MetricSnapshot`, `model.py:174`); a blind
  host is a finding, not a healthy host (`argus/detectors/classes.py`); four tests hold it
  (`test_t0027_blind_spot`, `test_t0032_prometheus_down`, `test_sc04_pg_connections`, `test_e2e2_evidence_gaps`). §5.4
  types `MetricSnapshot.values` as `float | int | bool`, and the rule is never stated once.

## 2. Why the current architecture is insufficient

The architecture is the source of truth (AGENT_PROTOCOL). A reader of §5.4 or §12.3 who "fixes" the code to match
the text would drop the provenance the model relies on, or coerce a missing value to 0, which is exactly the failure
G-007 forbids. SUMMARY.md's "Known differences" does not list them either.

## 3. Smallest reasonable change

- **§5.4** `MetricSnapshot`: `observed_at: datetime | None` (None = no sample at all) and `values: dict[str, float |
  int | bool | None]` (None = missing, never 0). `EvidenceRecord`: `observed_at` becomes `source_time: datetime |
  None` and `collected_at: datetime`; `partial` joins `truncated` and `redactions`.
- **§12.3** `Observation`: the same two times, plus `units`, `partial`, `coverage`, `identities`. A new rule under
  "Rules for every capability implementation": **unknown is never healthy** (a value that could not be read is
  `None`, never 0 or a default; partial reads say so; no detector, summary, conclusion or UI state treats missing or
  partial data as healthy or as a root cause).
- **§10** (context budget and the `<evidence>` tag): `observed_at` becomes `source_time`, as the runner writes it.
- **§13.1**: `profile: lab | production` in the policy file, required, fail closed. It names the kind of deployment;
  the rules that differ by kind refer to it (separation of duties, ACR-0018). Which profile a deployment runs is
  decided in that deployment's records.

**Not changed here:** `config/policy.yaml` keeps `profile: production`. Today the profile changes nothing but an error
message. Whether the lab runs `lab` (allowing a recorded self-approval) or keeps `production` (stricter) is decided
in the phase 16 pull request that applies ACR-0018, where it starts to matter.

**Alternatives considered:**
- A: **record them in SUMMARY.md's "Known differences" only.** Rejected: they are not differences to resolve, they
  are the intended design.
- B: **one ACR per gap.** Rejected: three small text changes with no behaviour change; one review is enough.
- C: **switch the lab to `profile: lab` now.** Deferred: it is a policy decision with no effect yet (above).

## 4. Consequences

- **Code:** none. **Tests:** `tests/test_acr0027_built_gaps.py` pins the text to the code: a missing or unknown
  profile refuses startup, both profiles load, the deployed policy names one; the provenance fields exist; a missing
  metric stays `None`.
- **Other sections:** §5.4, §10, §12.3, §13.1. SUMMARY.md unchanged (no difference left to list).
- **Risk:** none at run time.
- **How to reverse it:** revert the text; the code is unchanged either way.
- **Safety principles touched:** no rule changes. The evidence record's fields are now described as built (evidence
  integrity is unchanged: the same fields, the same hash). No second approval needed.

## 5. Decision

Proposed. Accepted with a teammate's approval of `task/ACR-0027-built-gaps`.

## 6. Applied

- [x] `ARCHITECTURE.md` updated (§5.4, §10, §12.3, §13.1), version 1.8.23, changelog line
- [x] journal entry (`2026-10-20-ACR-0027-built-gaps.md`)
- [x] the ACR, the architecture change and its tests in the same pull request
