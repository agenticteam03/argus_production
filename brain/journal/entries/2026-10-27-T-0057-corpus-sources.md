## 2026-10-27 - T-0057: local corpus sources, staged fetch and the approval API (ACR-0034 local tier)

Type: implementation
Who: conantkd (+ agent)
Context: ACR-0034 designed a local tier: an installation adds a reference source through an isolated fetch and an
administrator's approval, without a developer or Git.
Decision / result:
- `argus corpus fetch` stages one source of the allowlist (or of an administrator's local list, whose hosts must be in
  the base allowlist) and never installs it.
- `argus-v18-corpus` runs it on demand (profile `corpus`), internal network, egress proxy only, no secret. The egress filter is
  NOT widened (review before the merge): the scheduler shares the proxy and holds the OCI and Telegram credentials,
  so the documentation hosts wait for a per-client filter; until then the fetch runs on a laptop and is imported.
- Role `admin` with the privileged permission `manage_corpus`; the list, approve and reject routes under the private
  prefix; each decision has a step-up bound to the staged bundle's passages hash; approve verifies the hashes and merges
  the source into the installed bundle; both decisions are audited.
- Architecture 1.8.40 (§15.3 and the changelog).
Consequences: enabling `argus-v18-corpus` on vm-095 needs a per-client egress filter first; the
worker sees an approved source only after a restart; the UI screen is T-0058.
References: [T-0057 task](../../tasks/current/T-0057-corpus-sources.md), ACR-0034.

### Test state

Red first: `tests/test_t0057_corpus_sources.py` failed on the missing `argus.corpus.staging`. Then 10 passed; with the
phase 16 alerts and private-path tests, phase 19 private login and T-0056: 131 passed. UI contract: the three routes
added, samples unchanged.

### Next step

T-0058 (the UI screen); then deploy with the corpus: the staging folder, the egress and agent images, an `admin` user.
