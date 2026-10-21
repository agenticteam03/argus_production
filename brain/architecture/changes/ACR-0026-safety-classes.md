# ACR-0026 — One scheme of safety classes for every capability

Fixes [OP-003](../../OPEN_PROBLEMS.md) (runbook safety classes not mapped to `CapabilitySpec.risk`). It is the base
that phase 17 builds on ([NEXT-PHASE](../../tasks/current/NEXT-PHASE-supervised-remediation.md): `config/risk.yaml`,
the action cards, ACR-0019 §3.7).

| Field | Value |
|---|---|
| Status | `proposed`; applied in the same pull request (§6), accepted with its approvals |
| Proposed by | conantkd (+ agent) · 2026-10-20 |
| Accepted by | — |
| Second approval (safety principle only) | **required**: read-only (which operations may ever write, and that `FORBIDDEN` is never registered) |
| Architecture version | 1.8.20 → 1.8.22 (1.8.21 is #207's, OP-015) |
| Task / PR | OP-003 · `task/ACR-0026-safety-classes` |

## 1. Detect and explain

Three schemes describe the same thing and disagree:

- **§12.3** gives `CapabilitySpec` a `risk: low | medium | high | very_high` and a free `permission: read |
  write_hitl` and `side_effect: none | write`. Nothing in the code reads `risk`; nothing ties `permission` to
  `side_effect`.
- **The code** (`argus/capabilities/spec.py`) has a `safety_class` of two values, `READ_ONLY_SAFE` and
  `READ_ONLY_SENSITIVE`, which the policy checks (`argus/policy/engine.py`, `allowed_safety_classes` in
  `config/policy.yaml`). §12.3 does not mention it.
- **The runbooks** (`argus/runbooks/RB-*.md`, "Safety class" column) use the library's five classes, mostly
  `READ_ONLY_SENSITIVE` for every read and `MUTATING_HIGH_RISK` for every write: 83 of their 141 rows disagree with
  the catalog (a different class, or a tool name the catalog does not register).

And the catalog contradicts itself: `container.logs` is `READ_ONLY_SENSITIVE`, but `container.detailed_logs` (up to
500 lines of the same log) and `container.search_logs` (up to 50 matching lines) were `READ_ONLY_SAFE`; so was
`analysis.diagnostic_snapshot`, which reads `container.logs` (30 lines) and copies up to 400 characters of each
sub-read into its result (found by `juanbetancurm` in review), and `host.directory_sizes`, which returns the names of
the entries under a mount.

## 2. Why the current architecture is insufficient

§12.3's `risk` cannot say "never", which `FORBIDDEN` can; it cannot say "may return secrets", which decides whether a
read needs a field allowlist (G-006); and it is a second risk scale beside the per-target colours that ACR-0019 §3.7
adds in `config/risk.yaml`. Phase 17 needs one answer to "what kind of operation is this" before it writes the risk
table and the action cards.

## 3. Smallest reasonable change

**§12.3**, `CapabilitySpec`, before: `risk: Literal["low", "medium", "high", "very_high"]`; `side_effect` and
`permission` set freely. After: `safety_class` of four registrable classes; `side_effect` and `permission` derived
from it, never set by hand. A **Safety classes** table follows the contract:

| Class | Meaning | `permission` / `side_effect` | Use |
|---|---|---|---|
| `READ_ONLY_SAFE` | a read that returns no secret and no personal data | `read` / `none` | offered to the model by level and class tags |
| `READ_ONLY_SENSITIVE` | a read that **may** return secrets, paths, command lines or client names; every read of the target's own text or of names found on the host; a combined read with such a sub-read | `read` / `none` | offered to the model; field allowlist and redaction (G-006); audited with full arguments |
| `MUTATING_LOW_RISK` | a reversible change, no data at risk | `write_hitl` / `write` | never a model tool; §14's path; minimum colour green |
| `MUTATING_HIGH_RISK` | a change hard to reverse, or with a data risk | `write_hitl` / `write` | as above; always red; two reviewers to release |
| `FORBIDDEN` | never done | — | never registered; named only by `config/risk.yaml` and runbooks |

Rules: the class is the operation's, fixed in code; a combined capability (§12.7) is as sensitive as its most
sensitive sub-read; the colour is the operation's **on a target**, and may only raise
the class's minimum; if `config/risk.yaml` marks a pair forbidden, forbidden wins. The policy profile lists the
classes it allows (**§13.1** gains `allowed_safety_classes`, as the code already has).

**Alternatives considered:**
- A: **keep `risk` and add a `sensitive` flag.** Rejected: still no "never", and two risk scales beside `risk.yaml`.
- B: **put the colour in the class** (`MUTATING_GREEN`…). Rejected: the same restart is green on a cache and red on
  a database; the colour belongs to the target, the class to the operation.
- C: **keep the architecture and let the code differ.** Rejected: that is OP-003.

## 4. Consequences

- **Code (this pull request):** `SAFETY_CLASSES` in `argus/capabilities/spec.py`; `container.detailed_logs`,
  `container.search_logs`, `analysis.diagnostic_snapshot` and `host.directory_sizes` become `READ_ONLY_SENSITIVE`;
  `SUBREADS` in `catalog.py` names each combined capability's sub-reads (`TRACE_READS` for the request path).
  No runtime change: the lab profile already allows both read
  classes, and nothing else branches on the class yet.
- **Tests:** `tests/test_acr0026_safety_classes.py`: every registered class is one of the five and never
  `FORBIDDEN`; every read of the target's own text is sensitive; a combined read declares its sub-reads, calls only
  those, and is sensitive when one of them is; the policy allows nothing outside the scheme (red
  seen: the old catalog fails it). `tests/test_t0037_docker_read_verbs.py` expects the new classes.
- **Later:**
  - phase 17 adds the two `MUTATING_*` values to `CapabilitySpec`, derives `permission` / `side_effect` in code, and
    writes the colour rule into `config/risk.yaml`'s validation;
  - G-006 gives every `READ_ONLY_SENSITIVE` capability its field allowlist;
  - the runbooks' "Safety class" column is rewritten from the catalog, with a test that keeps them equal (a
    follow-up: 54 rows in 19 runbooks still differ after this change, and runbooks get a teammate's review under
    OP-014 step 8). Until then the catalog
    wins; the column is guidance for the reader.
- **Risk:** none at run time today. A capability classed too low would skip its allowlist once G-006 exists; the
  raw-text list in the test is where a new one is caught.
- **How to reverse it:** revert this pull request; the two log reads go back to `READ_ONLY_SAFE`.
- **Safety principles touched:** read-only (which classes may ever write, and the never-registered `FORBIDDEN`).
  Second approval required.

## 5. Decision

Proposed. Accepted with the approvals of `task/ACR-0026-safety-classes`: a teammate's, plus a second one for
read-only.

## 6. Applied

- [x] `ARCHITECTURE.md` updated (§12.3, §13.1), version 1.8.22, changelog line
- [x] journal entry (`2026-10-20-ACR-0026-safety-classes.md`)
- [x] the ACR, the architecture change and the code in the same pull request
