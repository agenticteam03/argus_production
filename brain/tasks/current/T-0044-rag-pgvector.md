# T-0044 — Evaluate Weaviate for hybrid runbook retrieval behind `KnowledgePort`

| Field | Value |
|---|---|
| Status | `proposed` — **ACR + documentation only** (this pull request); the evaluation, the code and the deployment are delivered by a teammate's implementation pull request |
| Phase | 5 / 9 — retrieval over the runbook corpus ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)) |
| Architecture | **ACR-0015** (proposed): §15.3 "no vector store" → evaluate Weaviate behind `KnowledgePort`; a §16.1 row and one deployment container |
| Branch | `task/T-0044-rag-pgvector` (from `main`; the branch name is historical — the store under evaluation is Weaviate) |
| Owner | `juanes6554` (+ agent) — proposer; evaluation handed to a teammate |
| Needs the VM lease | the evaluation (deploy Weaviate, build the index) and the benchmark |

## Problem

Runbook recall in the orchestrator is pure **TF-IDF** (`argus/adapters/outbound/config_adapters.py::TfidfRunbooks`),
built at startup, `k=3`. §21.2 targets recall@3 ≥ 0.9; the lab wants a stronger retriever and a TF-IDF-vs-RAG
comparison. The owner asks to **evaluate Weaviate** — a dedicated vector database with native hybrid search and a
reranking stage — as the store for that retriever, instead of adopting pgVector on the existing Postgres.

## Design (for the implementer)

- **One corpus loader for both retrievers** — a small module (e.g. `argus/adapters/outbound/runbook_corpus.py`):
  runbook IDs from metadata (never file names), one `##`-section per passage, an over-long section refused (never cut),
  the pinned `Safety and approval contract` sections shared. `TfidfRunbooks` is refactored onto it so the two
  retrievers agree on *what* a passage is and differ only on *ranking*.
- **`EmbeddingPort`** in `argus/ports/ports.py`, with two adapters: an OpenAI embeddings adapter (production,
  `text-embedding-3-small`, 1536 dims, batched + retried) and a deterministic keyless one (offline tests / smoke run,
  never for quality). Weaviate stores the vectors; the adapter that fills them lives in Argus.
- **Hybrid adapter behind `KnowledgePort`** (`search(query, k, runbook_ids)` unchanged), backed by Weaviate: BM25
  (k1=1.5, b=0.75) and dense neighbours fused as `alpha * vector + (1 - alpha) * bm25` after max-normalising each side,
  **or** Weaviate's native hybrid query if the evaluation shows it equivalent. `top_k` (default **20**) is the fusion /
  retrieval depth; `search` still returns at most the caller's `k` (the orchestrator's 3, §21 recall@3), so the model
  context is unchanged. An empty index degrades to BM25 — retrieval never fails because the index is empty.
- **Weaviate client**: official `weaviate` Python client, one collection for runbook passages (properties: runbook id,
  version, status, section, content, sha256), cosine distance, an optional reranker module. Connection details from
  settings; no credentials in code.
- **Composition root** (`wiring.py`): a `make_knowledge(settings)` selector — `tfidf` (default) or `hybrid` — so the
  default path is byte-for-byte unchanged. `wiring` still validates every class's runbook ids.
- **CLI**: `argus runbooks index` (embed + upsert into Weaviate, idempotent) and `argus runbooks search "…" [--k N]`.
- **Deployment**: a `weaviate` service definition (image, port, network, `mem_limit`/`cpus`/`pids_limit`) following the
  existing deployment rules; the index is derived and rebuildable from `argus/runbooks/`.

## Configuration (settings / env)

| Setting | Default | Meaning |
|---|---|---|
| `ARGUS_RETRIEVAL` | `tfidf` | `tfidf` (baseline) or `hybrid` (Weaviate + BM25) |
| `ARGUS_RETRIEVAL_TOP_K` | `20` | fusion depth and maximum results |
| `ARGUS_RETRIEVAL_ALPHA` | `0.5` | `0` = pure BM25, `1` = pure vector |
| `ARGUS_WEAVIATE_URL` | — | Weaviate endpoint (e.g. `http://argus-v18-weaviate:8080`) |
| `ARGUS_WEAVIATE_CLASS` | `RunbookPassage` | the Weaviate collection/class |
| `ARGUS_EMBEDDINGS` | `openai` | `openai` (needs a key) or `hashing` (offline) |
| `ARGUS_EMBEDDING_MODEL` | `text-embedding-3-small` | must match the vectors stored in Weaviate |
| `ARGUS_EMBEDDING_BASE_URL` | — | for an OpenAI-compatible embeddings endpoint |

## Weaviate steps (owner-run, vm-095)

1. **Deploy Weaviate** as a new `argus-v18-*` container on Host A: an image (for example `semitechnologies/weaviate`
   with the `text2vec-*`/`reranker` modules not required if Argus supplies vectors), its own port in the 18000–18799
   range, its own named volume, and the usual `mem_limit`/`cpus`/`pids_limit`. Nothing in the protected lab is touched.
2. **Smoke check**: `curl http://<host>:<port>/v1/.well-known/ready` returns 200.
3. **Build the index** from the worker host with the `openai_api_key` secret present and
   `ARGUS_RETRIEVAL=hybrid ARGUS_WEAVIATE_URL=…`: `argus runbooks index`. Re-run after any runbook change (idempotent).
4. **Flip the agent** on the worker (`ARGUS_RETRIEVAL=hybrid`) only after the benchmark (§ below) shows the Weaviate
   hybrid wins. Rollback is `ARGUS_RETRIEVAL=tfidf` and stopping the container.

## Benchmark plan (TF-IDF vs Weaviate hybrid — the comparison table)

- Extend `argus/evaluation` recall to run the same labelled cases through both retrievers at `k=3` and report
  **recall@3** (and ideally MRR@3 / nDCG@3) from `tests/eval/thresholds.yaml` (`runbooks` labels), following the
  `2026-10-13-EVAL-*` form (mean and worst case).
- Grid: `tfidf` vs Weaviate `hybrid` for `alpha ∈ {0, 0.25, 0.5, 0.75, 1}` and `top_k ∈ {10, 20, 40}`; optionally
  with/without Weaviate's reranker.
- Done when: the table shows the Weaviate hybrid's recall@3 versus the TF-IDF baseline; that result justifies (or
  rejects) offering it to a class and the §21.2 threshold change in ACR-0015. If the evaluation is inconclusive, record
  it and fall back to the pgVector alternative (ACR-0015 §3).

## Tests (for the implementer)

A `tests/test_t0044_rag.py` with an offline corpus check (loader equivalence with TF-IDF), BM25 ranking, fusion
weighting (`alpha=0` → BM25, `alpha=1` → vector), `runbook_ids` filtering, empty-index degradation, and the `index()`
upsert against a stubbed Weaviate client (no live service). The existing suite must stay green.

## Next step

A teammate reviews/accepts ACR-0015, then implements the design above (Weaviate container + code + tests), leases the VM
for the deployment, builds the index and runs the benchmark. The architecture text (§15.3, §16.1, §21.2) and the version
bump are applied in that implementation pull request.
