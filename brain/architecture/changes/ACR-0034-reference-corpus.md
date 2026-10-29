# ACR-0034 — A curated reference corpus of vendor documentation, with layered defences

Extends [ACR-0015](ACR-0015-rag-hybrid-retrieval.md) (hybrid retrieval behind a port, still `proposed`; this ACR
takes its design for a corpus where it pays, while the runbooks stay on TF-IDF) and makes the `knowledge.reference`
read of [ACR-0022](ACR-0022-autonomous-investigation.md) §3.4 concrete.

| Field | Value |
|---|---|
| Status | `accepted` (applied in part in T-0056; see §6) |
| Proposed by | conantkd (+ agent) · 2026-10-27 |
| Accepted by | juanbetancurm, verbally, relayed by conantkd · 2026-10-27; recorded for review in the redemption PR |
| Second approval (safety principle only) | conantkd as author (AGENT_PROTOCOL §4): **secrets** (a new outbound path to fetch documentation, offline only in this version) and **evidence integrity** (a new evidence kind, `knowledge.reference` passages) |
| Architecture version | from `1.8.38` → `1.8.39` |
| Task / PR | T-0056 · the pull request that adds this file |

## 1. Detect and explain

Argus knows how to fix what its 21 runbooks describe (`argus/runbooks/`, TF-IDF, `KnowledgePort.search`, §15.3), and
nothing else. A message, a setting or a command outside them (a Docker restart policy, a systemd unit option, a
PostgreSQL parameter, an nginx directive, a kernel OOM line) has no source the model can cite, so the investigation
either guesses or escalates. Operator suggestions (`suggest_action`, ACR-0019 §3.3) already carry a basis computed by
code from cited grounds, including `ref-*` for "curated reference documentation" (`argus/actions/suggestions.py`), but
no reference corpus exists to cite.

## 2. Why the current architecture is insufficient

§15.3: "No vector store is part of the architecture. A future retriever plugs in behind `KnowledgePort` (§24), and only
once §21 shows TF-IDF recall is insufficient." That holds for 21 runbooks. Vendor documentation is thousands of pages,
and an incident's words ("exited 137") are not the documentation's words ("OOM killer"), so keyword search alone
misses passages a hybrid search finds. §16.1 has no row for a reference corpus, and §10.8's untrusted-text rules
cover target text but not third-party documentation entering the model's context.

## 3. Smallest reasonable change

**Two tiers.**
- **Base corpus**, maintained by the developers of Argus: built offline by `argus corpus build` from the allowlist
  below, shipped as a bundle (passages, quarantine, manifest of SHA-256s), installed with `argus corpus import`.
- **Local corpus**, maintained by an installation's administrator: the inventory shows software without
  documentation, an isolated `argus-v18-corpus` service fetches its pinned docs through the egress proxy (an
  allowlist of documentation hosts), and a person approves each new source in the UI before it is indexed.
  *Designed here, built in later pull requests.*

**The base allowlist** (`config/corpus/sources.yaml`; HTTPS, the listed hosts only, a pinned tag or commit):

| Source | Archive host | Ref | Licence | Format |
|---|---|---|---|---|
| Linux man-pages (man1, 5, 7, 8) | mirrors.edge.kernel.org | man-pages-6.20 | permissive, per page | roff |
| Linux kernel admin guide | github.com (torvalds/linux) | v6.19 | GPL-2.0 | reStructuredText |
| systemd man pages | github.com (systemd/systemd) | v257 | LGPL-2.1-or-later | DocBook XML |
| Docker docs (Engine, Compose, CLI reference) | github.com (docker/docs) | commit 171f597 | Apache-2.0 | Markdown |
| Docker Engine API | github.com (moby/moby) | v28.5.2 | Apache-2.0 | OpenAPI |
| Podman command reference | github.com (containers/podman) | v5.8.9 | Apache-2.0 | Markdown |
| PostgreSQL 16 documentation | github.com (postgres/postgres, the official mirror) | REL_16_15 | PostgreSQL | DocBook SGML |
| nginx documentation | github.com (nginx/nginx.org) | commit 159f0a3 | BSD-2-Clause | XML |

Sources with share-alike or no-derivatives licences (distribution guides, community wikis, books) are out until a
licence review. Forums, issue trackers and blogs are out: user-written text is the likeliest carrier of injected
instructions; at most they reach the isolated research of ACR-0022 §3.5, for the operator only.

**Six defence layers.**
1. **Origin.** Only the allowlist, at pinned refs; a redirect to another host, plain HTTP or a moving branch is
   refused; archives are read in memory under size caps, never extracted or executed. Updating a ref shows the
   manifest's difference for review.
2. **Sanitising.** HTML comments, hidden elements, images and data URIs, front matter (its title kept), invisible
   Unicode (format and control characters) are removed before anything else; links keep their text and URL.
3. **Scanner and quarantine.** A passage addressed to an AI, rewriting instructions, with chat-role markers, naming
   Argus's tools or action cards, carrying a long encoded blob, or piping a download into a shell is written to
   `quarantine.jsonl` and never indexed until a person reviews it. Heuristics in this version; a similarity check
   against known injections (vectors of the same index) is designed, not built.
4. **Blast radius.** `knowledge.reference` returns passages as delimited data with their provenance under a header that
   calls them untrusted; a closing tag inside a passage is escaped. The read grants no tool and no permission, every
   action still goes through its card, the policy, the judge and the gateway, and the model has no outbound tool.
   The read is offered to no class until a model batch shows it does not lower accuracy (ACR-0024 §3.8).
5. **Output checks.** A `ref-*` ground gives a suggestion the `reference` basis only when that passage id was returned
   by `knowledge.reference` in the same investigation (`reference_grounds`); targets are substituted by code; command
   suggestions keep ACR-0019's never-offered list; the judge is not given the corpus text.
6. **Tests and monitoring.** Planted injections (several phrasings) are quarantined; a planted passage does not change
   the offers; the passages each incident used are in its evidence; a quarantine pattern seen at run time raises a
   security alert (designed, with the local corpus).

**Retrieval.** The installed bundle carries a keyword index (SQLite FTS5, BM25), the fallback and the default
(`ARGUS_CORPUS_RETRIEVAL=keyword`). With `hybrid`, a local Weaviate (`argus-v18-weaviate`, ACR-0015's measured
service: no vectorizer or API modules, `argus-v18-core` only, no host port, 512 MiB) ranks BM25 + vectors and **only
ranks**: each hit's text is read from the local bundle and must match the SHA-256 the index stored, else it is skipped.
Answers keep at most two passages per source, each passage once, official documentation weighted above text from a
target, and at most 1,800 characters per passage. Any failure (embeddings, Weaviate down, an empty or stale index)
falls back to the keyword search, counted and logged. Vectors are `text-embedding-3-small`, computed by Argus at
index time with the worker's existing model key on vm-095 (one query embedding per search). The runbooks stay on
TF-IDF (§15.3 unchanged for them).

**Alternatives considered**
- Fetch documentation live during an investigation: needs open egress from the worker, gives no stable citation and
  lets any page reach the model. Rejected.
- pgvector in the existing Postgres instead of Weaviate: avoids a container, but ACR-0015's trial and the project's
  choice are Weaviate; the retriever stays behind one class, so the store can change without touching the read.
- Keep runbooks only, and grow them by hand: does not scale to "any application"; generated runbook drafts from this
  corpus remain a later step.

## 4. Consequences

- **Code:** `argus/corpus/` (sources, fetch, sanitize, convert, scan, bundle, retrieval); `argus corpus build | import
  | index | search`; `knowledge.reference` (in-worker, Level 3, tag `reference`, offered to no class); the worker's
  `KnowledgeClient.reference`; `reference_grounds` for suggestions; `make_reference` in the wiring; the evaluation
  replay pins no corpus.
- **Deployment (vm-095):** `argus-v18-weaviate` and its volume; the worker mounts `/opt/argus-v18/corpus` read-only
  (`ARGUS_CORPUS_DIR=/corpus`); the bundle is built on a developer's machine, copied to the VM, installed with
  `argus corpus import`, indexed with `argus corpus index` in the worker (the model key never leaves the VM).
- **Risk:** injected instructions in documentation, limited by the six layers; a poisoned ranking, limited by the
  per-source quota, the trust weight and the hash check; licence obligations, limited by the allowlist's licence
  column.
- **How to reverse it:** unset `ARGUS_CORPUS_DIR` (or remove the bundle) and stop `argus-v18-weaviate`; the read then
  answers "no reference corpus" and nothing else changes.
- **Safety principles touched:** yes, secrets (a new fetch path; offline in this version, no secret involved) and
  evidence integrity (a new evidence kind, hashed per passage). Second approval as recorded above.

## 5. Decision

Accepted on 2026-10-27: juanbetancurm agreed verbally (relayed by conantkd), to be confirmed in the review of the
redemption pull request; conantkd gives the second approval as author. Ubuntu's documentation was removed from the
allowlist for its share-alike licence.

## 6. Applied

- [x] `ARCHITECTURE.md` updated (§15.3, §16.1), version 1.8.39, changelog row (T-0056)
- [x] Base allowlist, offline build, sanitising, scanner and quarantine, bundle hashes, keyword and hybrid retrieval,
      `knowledge.reference`, `reference_grounds`, the Weaviate service and the worker mount (T-0056)
- [ ] A signature over the bundle's manifest (this version verifies hashes only)
- [ ] The local corpus: the `argus-v18-corpus` fetch service and the UI's pending-sources screen
- [ ] The scanner's similarity check; the run-time quarantine alert
- [ ] Deployment evidence on vm-095 (bundle installed, indexed, a reference search from the worker)
- [ ] A model batch before offering the read to any class

- **Amended by [ACR-0040](ACR-0040-approver-manages-corpus.md) (2026-10-28):** an approver may list, approve and reject
  staged sources as an administrator does (`manage_corpus`, private path, a step-up per decision).
