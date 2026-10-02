# ACR-NNNN — <short title>

Copy this file to `ACR-NNNN-<slug>.md` (next free number). An Architecture Change Record is the **only** way to change
`brain/architecture/ARCHITECTURE.md`. A developer is never forced to implement a design shown to be wrong; equally, the
architecture is never changed silently to make an implementation easier.

| Field | Value |
|---|---|
| Status | `proposed` → `accepted` / `rejected` → `applied` |
| Proposed by | <github-handle> (+ agent) · <date> |
| Accepted by | <github-handle> · <date> |
| Second approval (safety principle only) | <github-handle> in PR #… |
| Architecture version | from `1.8.x` → `1.8.y` |
| Task / PR | T-xxxx · PR #… |

## 1. Detect and explain
What failed or what is missing, with evidence: the test, the output (sanitized), the spec section.

## 2. Why the current architecture is insufficient
Quote the exact section (§ number) and show the contradiction or the gap.

## 3. Smallest reasonable change
The minimal modification to the text of `ARCHITECTURE.md` (quote before → after).

**Alternatives considered** (at least one, including "keep the architecture and work around it"):
- A: … — why not
- B: … — why not

## 4. Consequences
- Code, tests, deployment and other architecture sections affected:
- Risk:
- How to reverse it:
- Does it touch a **safety principle** (read-only, write gate, host isolation, evidence integrity, secrets)? yes / no

## 5. Decision
Plain-language summary of what was decided, and by whom.

## 6. Applied
- [ ] `ARCHITECTURE.md` updated, version bumped, changelog line added (with this ACR's link)
- [ ] journal entry
- [ ] the ACR, the architecture change and the first code that needs it are in the same pull request
