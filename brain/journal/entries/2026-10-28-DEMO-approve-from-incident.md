## 2026-10-28 - Decide an approval from its incident; reference sources reachable and grouped by bundle

Type: fix
Who: conantkd (+ agent)
Context: three things seen in the UI on vm-095 (main `7036cf6`).
- An incident's Action card showed "Waiting for approval" but sent the approver to the Actions screen to decide it.
- Reference sources vanished from Tools: the entry needed `manage_corpus` in `/me`, which a privileged permission
  lists only inside a confirmed private session, so it disappeared whenever that session ended.
- The screen showed eight rows named `base`, each with only a licence. `base` is a staged bundle carrying the eight
  installed sources (the same passages hash as the installed corpus). The API names a staged row after its bundle,
  the UI drew one row per source, and it read `staged_at`/`installed_at` while the API sends `at`, so no date showed.
  Approving `base` would also have been refused: `approve()` replaced only installed sources named like the bundle,
  so the merge repeated every passage and the bundle check refused it.
Decision / result:
- `IncidentApproval.jsx`: on an incident whose approval is pending, an approver gets the Actions screen's steps
  (private login, security key) and its frozen `ApprovalCard`, and approves or denies there; the incident reloads.
  The steps live in `PrivateAccess.jsx`, shared with Actions; `privateStep` generalises `actionsStep`.
- `routes.js`: Reference sources is an approver's or administrator's entry, like Actions; `corpusStep` leads through
  the private login, and the list loads only once `/me` lists `manage_corpus`.
- `ReferenceSources.jsx`: one card per bundle (installed, or each staged one) with its build time, hash and each
  source's own name, one decision per bundle, and a notice when a staged bundle is identical to the installed corpus.
- `argus/corpus/staging.py`: approving a bundle replaces every source it carries; the list adds each row's `source`.
Consequences: frontend only, plus the corpus merge; no API route or permission changes. The `base` bundle on vm-095
can be rejected (it deletes only the staged copy) or approved (a no-op install) after this is deployed.
References: [ACR-0032](../../architecture/changes/ACR-0032-private-browser-login.md), [ACR-0034](../../architecture/changes/ACR-0034-reference-corpus.md), [ACR-0040](../../architecture/changes/ACR-0040-approver-manages-corpus.md).

### Test state

RED seen: `test_a_bundle_named_apart_from_its_sources_replaces_them_instead_of_repeating_them` (BundleRefused on the
repeated passage without the fix). GREEN locally: `test_t0057_corpus_sources.py`; vitest 346 tests, including
`IncidentApproval`, `corpusStep`, the bundle grouping and the identical-bundle notice; eslint without new warnings;
ruff clean on `argus/`. CI is the full check.

### Next step

Deploy the UI and the agent image on vm-095, then decide the `base` bundle from Reference sources.
