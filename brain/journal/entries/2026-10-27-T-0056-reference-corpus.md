## 2026-10-27 - T-0056: the curated reference corpus (ACR-0034), `knowledge.reference`, layered defences

Type: implementation + architecture
Who: conantkd (+ agent)
Context: the runbooks (21, TF-IDF) are Argus's only knowledge; a message, a setting or a command outside them has no
source to cite. ACR-0034 (accepted verbally by juanbetancurm, relayed by conantkd; recorded for review in the
redemption PR) adds a curated corpus of vendor documentation. PR #157 (Weaviate over the runbooks only) is closed;
its Weaviate client and service are reused.
Decision / result:
- ACR-0034 and `ARCHITECTURE.md` 1.8.39 (§15.3 the reference corpus, §16.1 row 6b, the changelog). Ubuntu's
  documentation is not in the allowlist (share-alike licence).
- `config/corpus/sources.yaml`: eight sources at pinned refs (man-pages-6.20, Linux v6.19 admin guide, systemd v257,
  docker/docs 171f597, moby v28.5.2's Engine API, Podman v5.8.9, PostgreSQL REL_16_15, nginx.org 159f0a3).
- `argus/corpus/`: fetch (allowlisted hosts, redirects checked per hop, size caps, read in memory, nothing executed),
  sanitise, convert (Markdown, reStructuredText, roff, DocBook/XML, OpenAPI), chunk, scan (heuristics; quarantine),
  bundle (manifest of SHA-256s; `verify` refuses a tampered passage), retrieval (FTS5 keywords; hybrid through
  Weaviate that only ranks, text by hash, two per source, dedupe, fallback).
- `argus corpus build | import | index | search`.
- `knowledge.reference` (in-worker, Level 3, tag `reference`, offered to no class), `KnowledgeClient.reference`,
  `make_reference`, `reference_grounds`; the replay pins no corpus.
- vm-095 compose: `argus-v18-weaviate` (1.38.18, no modules, `argus-v18-core`, no host port, 512 MiB) and its volume;
  the worker mounts `/opt/argus-v18/corpus` read-only (`ARGUS_CORPUS_DIR=/corpus`, keyword by default).
- A real build of two sources (nginx, the Engine API) gave 961 passages, none quarantined; searches found the
  restart operation and the nginx core module.
Consequences: deploy order: the agent image, `argus-v18-weaviate`, the bundle copied to `/opt/argus-v18/corpus`
through `argus corpus import`, `argus corpus index` in the worker, then `ARGUS_CORPUS_RETRIEVAL=hybrid`. Without a
bundle the read answers "no reference corpus" and nothing else changes.
References: [T-0056](../../tasks/current/T-0056-reference-corpus.md),
[ACR-0034](../../architecture/changes/ACR-0034-reference-corpus.md).

### Test state

Red first: `tests/test_t0056_reference_corpus.py` failed on `ModuleNotFoundError: argus.corpus`; then 41 passed
(allowlist, fetch and redirects, members never extracted, each hidden-text trick, the scanner on seven planted
phrasings and four ordinary passages, provenance and quarantine, bounded passages, a tampered passage refused, the
keyword search and its quota, hash-checked hybrid ranking, fallbacks, dedupe, the read's spec and delimiting, no
corpus = unreachable, `ref-*` only when retrieved, a planted passage does not change the offers, the compose service
and mount, the CLI). `tests/test_t0056_corpus_paths.py`, 28 more: each converter, the Weaviate client (schema, upsert, query, errors raised), the embeddings, the hybrid index, the wiring (no bundle, keywords, hybrid with and without the key, fail-open) and the CLI's error paths. Diff coverage of the changed lines 97 % (CI's gate 80 %). The capability checker passes on `knowledge.reference`; the full suite passed.

### Next step

Deploy on vm-095 (both leases): images, `argus-v18-weaviate`, build the bundle on the laptop, copy it, `argus corpus
import`, `argus corpus index` in the worker, a reference search, `NO INTERFERENCE`. Then the fetch-service PR and the
UI's pending-sources PR.
