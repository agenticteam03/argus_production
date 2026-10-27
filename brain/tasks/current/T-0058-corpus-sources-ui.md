# T-0058 — The reference sources screen (ACR-0034, the local tier, UI)

**Status:** in review · **Owner:** conantkd (+ agent) · **Depends on:** T-0057 (the corpus routes under
`/api/v1/ops/corpus/`)

## Goal

An administrator sees the reference sources Argus may cite (installed and staged) and approves or rejects a staged
one with a security key, as [ACR-0034](../../architecture/changes/ACR-0034-reference-corpus.md)'s local tier designs.

## Done in this task

- `Tools → Reference sources` (`/tools/reference-sources`), listed only when `/me` lists `manage_corpus`.
- A table of sources: status badge, ref, licence, passages, quarantined count, staged and installed dates, the sha256
  prefix.
- A staged source: Approve (a WebAuthn step-up bound to `corpus:<name>:<sha256>`, then the POST) and Reject (a reason
  required before the key is asked).
- The HTTP adapter's `listCorpusSources`, `approveCorpusSource`, `rejectCorpusSource`; the local preview lists one
  installed and one staged source and installs nothing.

## Not in this task

- The routes themselves, `contracts/ui-api.json` and `docs/API-FOR-UI.md` (T-0057). The contract test adds these
  calls once T-0057 declares the routes.
- The private sign-in on this screen: an administrator signs in privately from Actions first (the screen says so).
