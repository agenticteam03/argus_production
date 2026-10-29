# ACR-0040 — An approver manages the reference corpus

| Field | Value |
|---|---|
| Status | `accepted` |
| Proposed by | `conantkd` · 2026-10-28 |
| Accepted by | `conantkd` · 2026-10-28 |
| Second approval (safety principle only) | not required |
| Architecture version | proposed: `1.8.47` → `1.8.48` |
| Task / PR | demo of 2026-10-28 · PR to be numbered on opening |

## 1. Problem

ACR-0034's local tier lets only an administrator (role `admin`, `manage_corpus`) list, approve and reject staged reference sources, the vendor documentation Argus may cite as a ground. The people who answer approvals are approvers; they already work on the private path with two security keys and a step-up per decision, and they are the ones who need the corpus to cite what a proposal relies on.

Also, `/me` never listed `manage_corpus` among its actions, while the UI shows the Reference sources screen only when it does (ACR-0001), so nobody, an administrator included, saw that screen.

## 2. Why the current architecture is insufficient

The corpus decision is a reviewed, privileged act with its own step-up bound to the staged bundle's hash; who may make it is a role assignment, and the approver role is the one the team uses on the private path.

## 3. Smallest reasonable change

- `CORPUS_ROLE_PERMISSIONS` grants `manage_corpus` to `approver` as well as `admin`. Everything else stays: a human principal, the private path, a key-completed session (no privileged permission before it), a step-up bound to `corpus:<name>:<passages sha256>` for each approval or rejection, a reason for a rejection, the staged hashes verified, the audit (`corpus.source_approved`, `corpus.source_rejected`).
- `/me` lists `manage_corpus` among the actions when it is granted, so the Reference sources screen appears for whoever holds it.
- An operator or a viewer still cannot.

**Alternatives considered:**

- Make every approver an administrator: rejected; `admin` also issues enrolment tickets for security keys, which an approver should not.

## 4. Consequences

- Code and tests: `argus/adapters/inbound/http.py`; the Reference sources text and comments in the UI; `tests/test_t0057_corpus_sources.py`.
- Deployment: the next agent and UI images; no migration, no configuration.
- Risk: more people may install a reference source. Each installation is a reviewed staged bundle, verified by hash, bound to a step-up and audited; a source never runs code, and a passage is only a ground a proposal may cite.
- Reversal: remove `approver` from `CORPUS_ROLE_PERMISSIONS`.
- Safety principle changed: no.

## 5. Decision

`conantkd` asked for it on 2026-10-28: the approver may operate on the reference sources as well.

## 6. Applied

- [x] `ARCHITECTURE.md` updated, version bumped to 1.8.48, changelog line added with this ACR's link
- [x] journal entry
- [x] the ACR, the architecture change and the code that needs it are in the same pull request
