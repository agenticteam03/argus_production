# ACR-0015 — Evaluate Weaviate as the vector store for hybrid runbook retrieval behind `KnowledgePort`

| Field | Value |
|---|---|
| Status | `proposed` — needs a teammate's approval of its pull request; then applied (ARCHITECTURE.md, code) |
| Proposed by | `juanes6554` (+ agent) · 2026-10-14 |
| Accepted by | — |
| Second approval (safety principle only) | not needed (no safety principle is touched; see §4) |
| Architecture version | from `1.8.12` → `1.8.13` (when applied) |
| Task / PR | T-0044 · this pull request (ACR and documentation only; the evaluation, the code and the deployment are delivered by a teammate's implementation pull request) |

## 1. Detect and explain

Runbook recall in the orchestrator is pure **TF-IDF**: `argus/adapters/outbound/config_adapters.py::TfidfRunbooks`,
built at startup from `argus/runbooks/`, used at `k=3` (§10.5, `KnowledgePort.search(query, 3, …)`). §21.2 makes the
retriever a **measured** decision:

> **Retrieval:** TF-IDF recall@3 ≥ 0.9. Below that, fix the runbook corpus before changing retrievers.

The aim for T-0044 is a **hybrid retriever** — dense embeddings + BM25 — measured against the TF-IDF baseline on the
same evaluation cases (`tests/eval/thresholds.yaml`, `recall_at_3: 0.9`). The owner asks to **evaluate Weaviate** (a
dedicated vector database with native hybrid search and a reranking stage) as the vector store for that retriever,
instead of adopting pgVector on the existing Postgres. As written, the architecture names the *mechanism* for a better
retriever but forbids the *store*, and the state inventory has no retrieval index. This ACR records that change before
any code is written.

## 2. Why the current architecture is insufficient

Two sections block a vector store, and Weaviate is a **separate service** (not a Postgres extension):

- §15.3: "**No vector store is part of the architecture.** A future retriever plugs in behind `KnowledgePort` (§24),
  and only once §21 shows TF-IDF recall is insufficient." — a blanket prohibition that must be replaced by the named
  candidate and the condition for using it.
- §16.1 ("Inventory of state"): "All Argus-owned durable state lives in **one Postgres 16 instance on Host A**" — with no
  room for a retrieval index, let alone a second service.
- §24 already permits a new retriever: "**A retriever (e.g. vector store)** | a new `KnowledgePort` adapter, justified
  by the §21.2 retrieval metric | untouched". Portability is therefore not the problem; the store and its deployment
  are.

Without this ACR, deploying and evaluating Weaviate is a silent architecture change — exactly what the change-control
rule forbids.

## 3. Smallest reasonable change

Minimal edits to `ARCHITECTURE.md` (quote **before → after**):

1. **§15.3** (last paragraph of the runbook-retrieval section)
   - before: *"No vector store is part of the architecture. A future retriever plugs in behind `KnowledgePort` (§24),
     and only once §21 shows TF-IDF recall is insufficient."*
   - after: *"Runbook retrieval may be hybrid: BM25 (lexical) and a vector store (dense embeddings) fused behind one
     `KnowledgePort` adapter, selected by `ARGUS_RETRIEVAL` (`tfidf` default, `hybrid` opt-in). The candidate store is
     **Weaviate**, evaluated in T-0044 against the TF-IDF baseline (§21.2) before it becomes the default; TF-IDF stays
     the default until that evaluation matches or beats it."*

2. **§16.1** (state inventory) — add one row: *runbook retrieval index (Weaviate) | embeddings of the bounded runbook
   sections, for cosine/BM25 hybrid search | Weaviate, its own container/service on Host A | derived and rebuildable
   from the runbook library in Git — not the system of record, not evidence, not audit | rebuilt with
   `argus runbooks index`.* (The service's port, network and resource limits follow the existing deployment rules §5 /
   §14.)

3. **§21.2** (metrics/thresholds) — "TF-IDF recall@3 ≥ 0.9" becomes the **baseline**: the Weaviate hybrid must match or
   beat it on the same cases before it is offered to a class.

4. **§24** — unchanged; the existing "A retriever (e.g. vector store)" row already covers the extension point.

**Alternatives considered:**
- **A: Keep the architecture and work around it** (ship the retriever without an ACR) — rejected: it violates the
  change-control rule; the architecture is never changed silently to make an implementation easier.
- **B: Do the RAG outside Argus** (an offline notebook that re-ranks runbooks) — rejected: it proves nothing about the
  agent's real retrieval path, the §21.2 recall@3 metric or the §24 extension point.
- **C: pgVector on the existing Postgres** — considered and set aside: it is the smaller change (one extension, one
  table, no new service), but the owner wants Weaviate's native hybrid search and reranking as the stronger long-term
  option. pgVector remains the fallback if the Weaviate evaluation is inconclusive.
- **D: Adopt Weaviate as the default now** — rejected: §21.2 says the corpus and the measurement come first; T-0044 is
  an *evaluation*, TF-IDF stays the default until the Weaviate hybrid wins.

## 4. Consequences

- **Code, tests, deployment:** a Weaviate-backed `KnowledgePort` adapter (hybrid: embeddings + BM25/Weaviate native
  hybrid, fused by `alpha`), an embedding adapter to populate the index, a shared runbook parser used by both
  retrievers, a `make_knowledge` selector in the composition root, a CLI to build the index, and a **new
  container/service for Weaviate** on Host A (image, port, network and `mem_limit`/`cpus`/`pids_limit` per §5 / §14).
  The evaluation gains a TF-IDF-vs-Weaviate comparison; the orchestrator's `k=3` and the `knowledge.runbook` capability
  are untouched. A teammate delivers this; the present pull request is the ACR and its documentation only.
- **New service:** Weaviate is a second data plane. It must not touch the protected objects of the lab and must be
  rebuilt from the runbook library if lost (the index is derived, not the source of truth).
- **Other architecture sections affected:** §16.1 (state inventory), §21.2 (baseline wording); the deployment resource
  budget (§5 / §14) gains one container.
- **Risk:** a new service to operate (memory footprint, an extra port/network); mitigated by making the index
  rebuildable and by keeping TF-IDF as the default/reversal path.
- **How to reverse it:** keep `ARGUS_RETRIEVAL=tfidf` (the default) and stop/drop the Weaviate container — nothing else
  depends on it.
- **Safety principle (read-only, write gate, host isolation, evidence integrity, secrets):** **no**. Retrieval is
  read-only, runs inside the worker, and the runbooks are a public corpus; no write gate, host isolation,
  evidence-integrity or secrets rule is touched.

## 5. Decision

Evaluate **Weaviate** as the vector store for a hybrid (`BM25` + embeddings) runbook retriever behind `KnowledgePort`,
opt-in via `ARGUS_RETRIEVAL=hybrid`, keeping TF-IDF as the measured default until the §21.2 comparison justifies the
switch. Proposed by `juanes6554`; pending a teammate's acceptance.

## 6. Applied
- [ ] `ARCHITECTURE.md` updated, version bumped (`1.8.12` → `1.8.13`), changelog line added (with this ACR's link)
- [x] journal entry (`brain/journal/entries/2026-10-14-T-0044-rag-pgvector.md`)
- [ ] the ACR, the architecture change and the first code that needs it are in the same pull request (the evaluation,
      the code and the deployment follow in a teammate's implementation pull request, per the owner's decision)
