# T-0056 — The curated reference corpus: vendor documentation for `knowledge.reference`, with layered defences

| Field | Value |
|---|---|
| Status | `in progress` — code, ACR-0034 and the architecture in this PR; next: deploy on vm-095 (Weaviate, the bundle) |
| Phase | 22 (more autonomous investigation): the `knowledge.reference` read of ACR-0022 §3.4 |
| Architecture | [ACR-0034](../../architecture/changes/ACR-0034-reference-corpus.md) `accepted`, 1.8.39 (§15.3, §16.1) |
| Branch | `task/T-0056-reference-corpus` (from `main`) |
| Owner | `conantkd` (+ agent) |
| Needs the VM lease | for the deployment only (both leases: an agent change on vm-095) |
| Replaces | PR #157 (T-0044, Weaviate over the runbooks only), closed; its Weaviate client and service are reused |

## Design (ACR-0034)

- `config/corpus/sources.yaml`: the base allowlist (man-pages, the kernel's admin guide, systemd, Docker docs, the
  Engine API, Podman, PostgreSQL 16, nginx), each with its exact hosts, a pinned ref, a licence and size caps.
- `argus corpus build` (a developer's machine or CI, never the VM): fetch → sanitise → convert → chunk (1,800
  characters) → scan → `passages.jsonl`, `quarantine.jsonl`, `manifest.json` (SHA-256 of the files and of every
  passage). `argus corpus import` verifies and installs it with an FTS5 keyword index; `argus corpus index` builds
  the Weaviate class (hybrid); `argus corpus search` is a debug view.
- `knowledge.reference` / `query_reference`: Level 3, in-worker, `max_per_incident` 3, tag `reference` (offered to no
  class). The answer is delimited, untrusted data with provenance; `reference_grounds` gives a `ref-*` ground its
  basis only when that passage was returned.
- Retrieval: keyword by default; hybrid (`ARGUS_CORPUS_RETRIEVAL=hybrid`) with Weaviate ranking only, the text from
  the bundle by hash, two passages per source, dedupe, fallback to keywords on any failure.

## Steps

1. This PR: ACR-0034, the architecture, the code, the tests, the compose service and the worker mount.
2. Deploy on vm-095: the images, `argus-v18-weaviate`, the bundle built on the laptop and copied, `import`, `index`
   in the worker (the model key stays on the VM), a reference search from the worker, `NO INTERFERENCE`.
3. The local corpus: the isolated `argus-v18-corpus` fetch service (its own PR).
4. The UI's pending-sources screen, approved on the private path (its own PR).
5. A model batch before offering the read to a class (ACR-0024 §3.8).

## Not in this PR

A signature over the manifest (hashes only), the scanner's similarity check, the run-time quarantine alert.
