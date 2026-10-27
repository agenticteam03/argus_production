## 2026-10-27 - T-0058: the reference sources screen (ACR-0034, the local tier)

Type: implementation
Who: conantkd (+ agent)
Context: ACR-0034 designs a local corpus tier: an isolated service downloads a source, and an administrator approves
it in the UI before it is installed. T-0057 builds the routes; this task builds the screen against the same contract.
Decision / result:
- `Tools → Reference sources`, shown only when `/me` lists `manage_corpus`; the table of installed and staged
  sources with status, ref, licence, passages, quarantine count, dates and the sha256 prefix.
- Approve and reject a staged source: a one-use step-up bound to `corpus:<name>:<sha256>` (a newer bundle needs a new
  touch); a rejection needs a reason before the key is asked; a 409 (nothing staged, a hash mismatch) shows inline.
- Adapters: `listCorpusSources`, `approveCorpusSource`, `rejectCorpusSource`; the preview installs nothing.
- Not here: the routes and the contract (T-0057); the private sign-in stays on Actions.
Consequences: the screen answers 404 until T-0057's routes are deployed; nothing else changes.
References: [T-0058 task](../../tasks/current/T-0058-corpus-sources-ui.md), ACR-0034.

### Test state

Red first: the three new test files failed (the modules missing, the route absent). Then: Vitest 55 files, 332 tests
passed (with coverage); ESLint 0 errors and no warning in the changed files; `vite build` passes.

### Next step

Merge after T-0057 (the routes), then add the three calls to `services/contract.test.js`.
