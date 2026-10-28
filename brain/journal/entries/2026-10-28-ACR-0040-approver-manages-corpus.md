## 2026-10-28 - ACR-0040: an approver manages the reference corpus

Type: architecture change
Who: conantkd
Context: only an administrator could list, approve and reject staged reference sources, while the people on the private path with two security keys are approvers. Also, `/me` never listed `manage_corpus` among its actions, so the Reference sources screen never appeared, not even for an administrator.
Decision / result:
- `CORPUS_ROLE_PERMISSIONS` grants `manage_corpus` to `approver` as well as `admin`; the private path, the key-completed session, the step-up per decision, the hash check and the audit are unchanged.
- `/me` lists `manage_corpus` among the actions when it is granted.
- The UI text says approvers and administrators; `ARCHITECTURE.md` 1.8.48, [ACR-0040](../../architecture/changes/ACR-0040-approver-manages-corpus.md), a note in ACR-0034.
Consequences: takes effect with the next agent and UI images on vm-095; no migration.
References: [ACR-0034](../../architecture/changes/ACR-0034-reference-corpus.md).

### Test state

RED seen: `test_an_approver_manages_the_corpus_like_an_administrator` (403 for an approver) and `/me` without `manage_corpus` before the change. GREEN locally: `test_t0057_corpus_sources.py` (an approver lists and approves with a step-up bound to the bundle; `/me` lists the action only with the second factor; an operator and a viewer still get 403), the private login tests, the UI contract. The frontend tests and the full suite are left to CI.

### Next step

After the deploy, an approver signs in privately and opens Tools → Reference sources.
