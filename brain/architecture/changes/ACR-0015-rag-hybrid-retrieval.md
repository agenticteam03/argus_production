# ACR-0015 — A pgVector + BM25 hybrid retriever behind `KnowledgePort`

| Field | Value |
|---|---|
| Status | `proposed` — needs a teammate's approval of its pull request; then applied (ARCHITECTURE.md, code) |
| Proposed by | `juanes6554` (+ agent) · 2026-10-14 |
| Accepted by | — |
| Second approval (safety principle only) | not needed (no safety principle is touched; see §4) |
| Architecture version | from `1.8.12` → `1.8.13` (when applied) |
| Task / PR | T-0044 · this pull request (ACR and documentation only; the code and the database step are delivered by a teammate's implementation pull request) |

## 1. Detect and explain

Runbook recall in the orchestrator is pure **TF-IDF**: `argus/adapters/outbound/config_adapters.py::TfidfRunbooks`,
built at startup from `argus/runbooks/`, used at `k=3` (§10.5, `KnowledgePort.search(query, 3, …)`). §21.2 makes the
retriever a **measured** decision:

> **Retrieval:** TF-IDF recall@3 ≥ 0.9. Below that, fix the runbook corpus before changing retrievers.

The lab's aim for T-0044 is a **hybrid retriever** — dense embeddings + BM25 — and a TF-IDF-vs-RAG comparison on the
same evaluation cases (`tests/eval/thresholds.yaml`, `recall_at_3: 0.9`). As written, the architecture names the
*mechanism* for a better retriever but forbids the *store* the comparison needs, and the state inventory does not list
the retrieval index. This ACR records that change before any code is written.

## 2. Why the current architecture is insufficient

§24 already permits a new retriever: "**A retriever (e.g. vector store)** | a new `KnowledgePort` adapter, justified by
the §21.2 retrieval metric | untouched". Portability is therefore not the problem. The gaps are:

- §15.3 states: "**No vector store is part of the architecture.** A future retriever plugs in behind `KnowledgePort`
  (§24), and only once §21 shows TF-IDF recall is insufficient." — a blanket prohibition that must be replaced by the
  named store and the condition for using it.
- §16.1 ("Inventory of state") enumerates every piece of durable state in the one Postgres instance but has no row for
  a retrieval index, while the whole point of T-0044 is to build and measure one.

Without this ACR, adding pgVector is a silent architecture change — exactly what the change-control rule forbids.

## 3. Smallest reasonable change

Minimal edits to `ARCHITECTURE.md` (quote **before → after**):

1. **§15.3** (last paragraph of the runbook-retrieval section)
   - before: *"No vector store is part of the architecture. A future retriever plugs in behind `KnowledgePort` (§24),
     and only once §21 shows TF-IDF recall is insufficient."*
   - after: *"Runbook retrieval is hybrid: BM25 (lexical) and pgVector (dense embeddings) fused behind one
     `KnowledgePort` adapter, selected by `ARGUS_RETRIEVAL` (`tfidf` default, `hybrid` opt-in). The embeddings live in
     a `runbook_passage` table (`vector(1536)`) in the existing Postgres instance; TF-IDF remains the default until
     §21.2 shows its recall@3 below the target, after which the hybrid is the measured successor."*

2. **§16.1** (state inventory) — add one row:
   *`runbook_passage` | one row per bounded runbook section: id, runbook id/version/status, section, content, content
   hash, `vector(1536)` embedding | pgVector extension in the existing Postgres 16 instance | derived and
   rebuildable; `argus_runtime` may `SELECT/INSERT/UPDATE/DELETE` (unlike incident/evidence/audit) | rebuilt from the
   runbook library in Git.*

3. **§21.2** (metrics/thresholds) — "TF-IDF recall@3 ≥ 0.9" becomes the **baseline**: a hybrid retriever must match or
   beat it on the same cases before it is offered to a class.

4. **§24** — unchanged; the existing "A retriever (e.g. vector store)" row already covers the extension point.

**Alternatives considered:**
- **A: Keep the architecture and work around it** (ship the adapter without an ACR) — rejected: it violates the
  change-control rule; the architecture is never changed silently to make an implementation easier.
- **B: Do the RAG outside Argus** (an offline notebook that re-ranks runbooks) — rejected: it proves nothing about the
  agent's real retrieval path, the §21.2 recall@3 metric or the §24 extension point.
- **C: A dedicated vector database (Weaviate)** — deferred, not rejected: the plan of record is Weaviate + reranking
  *later*; pgVector on the existing Postgres is the smallest change now (one extension, one table, no new service to
  operate), and a dedicated store can be a later ACR behind the same `KnowledgePort`.
- **D: Make the hybrid the default immediately** — rejected: §21.2 says the corpus comes before the retriever; the
  default stays TF-IDF until the comparison shows the hybrid wins.

## 4. Consequences

- **Code, tests, deployment:** a new `KnowledgePort` adapter (hybrid, BM25 + pgVector cosine, fused by `alpha`),
  an embedding adapter, a shared runbook parser used by both retrievers, a `make_knowledge` selector in the composition
  root, a CLI to build the index, and a migration (`CREATE EXTENSION vector`, `runbook_passage` + HNSW cosine index).
  The evaluation gains a TF-IDF-vs-hybrid comparison; the orchestrator's `k=3` and the `knowledge.runbook` capability
  are untouched. A teammate delivers this; the present pull request is the ACR and its documentation only.
- **Prerequisite:** the Postgres image on vm-095 must ship the `vector` extension (the stock `postgres:16-alpine`
  does not) before the migration can be applied.
- **Other architecture sections affected:** §16.1 (state inventory), §21.2 (baseline wording).
- **Risk:** an embedding-provider call at index time (batched, retried); the default path never calls it.
- **How to reverse it:** keep `ARGUS_RETRIEVAL=tfidf` (the default) — the hybrid is inert; the migration is additive and
  the table can be dropped.
- **Safety principle (read-only, write gate, host isolation, evidence integrity, secrets):** **no**. Retrieval is
  read-only, runs inside the worker, and the runbooks are a public corpus; no write gate, host isolation,
  evidence-integrity or secrets rule is touched.

## 5. Decision

Adopt a pgVector + BM25 hybrid retriever behind `KnowledgePort`, opt-in via `ARGUS_RETRIEVAL=hybrid`, with TF-IDF kept
as the measured default until the §21.2 comparison justifies the switch. Proposed by `juanes6554`; pending a teammate's
acceptance.

## 6. Applied
- [ ] `ARCHITECTURE.md` updated, version bumped (`1.8.12` → `1.8.13`), changelog line added (with this ACR's link)
- [x] journal entry (`brain/journal/entries/2026-10-14-T-0044-rag-pgvector.md`)
- [ ] the ACR, the architecture change and the first code that needs it are in the same pull request (the code and the
      database step follow in a teammate's implementation pull request, per the owner's decision)
