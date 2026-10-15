# T-0044 — Hybrid runbook retrieval: pgVector + BM25 behind `KnowledgePort`

| Field | Value |
|---|---|
| Status | `proposed` — **ACR + documentation only** (this pull request); the code, the database step and the benchmark are delivered by a teammate's implementation pull request |
| Phase | 5 / 9 — retrieval over the runbook corpus ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)) |
| Architecture | **ACR-0015** (proposed): §15.3 "no vector store" → pgVector behind `KnowledgePort`; a §16.1 state row |
| Branch | `task/T-0044-rag-pgvector` (from `main`) |
| Owner | `juanes6554` (+ agent) — proposer; implementation handed to a teammate |
| Needs the VM lease | the implementation (recreate `argus-v18-postgres` with a pgvector image, apply the migration) and the benchmark |

## Problem

Runbook recall in the orchestrator is pure **TF-IDF** (`argus/adapters/outbound/config_adapters.py::TfidfRunbooks`),
built at startup, `k=3`. §21.2 targets recall@3 ≥ 0.9; the lab wants a stronger retriever and a TF-IDF-vs-RAG
comparison. The corpus is small (21 runbooks, ~630 bounded sections) and the system of record is already Postgres, so
the cheapest stronger retriever is **pgVector on the same database** rather than a new service. Weaviate plus a
reranking stage is the later, stronger option.

## Design (for the implementer)

- **One corpus loader for both retrievers** — a small module (e.g. `argus/adapters/outbound/runbook_corpus.py`):
  runbook IDs from metadata (never file names), one `##`-section per passage, an over-long section refused (never cut),
  the pinned `Safety and approval contract` sections shared. `TfidfRunbooks` is refactored onto it so the two
  retrievers agree on *what* a passage is and differ only on *ranking*.
- **`EmbeddingPort`** in `argus/ports/ports.py`, with two adapters: an OpenAI embeddings adapter (production,
  `text-embedding-3-small`, 1536 dims, batched + retried) and a deterministic keyless one (offline tests / smoke run,
  never for quality).
- **Hybrid adapter behind `KnowledgePort`** (`search(query, k, runbook_ids)` unchanged): BM25 (k1=1.5, b=0.75) over the
  sections in the worker; dense neighbours from pgVector (`embedding <=> query`, cosine); fused as
  `alpha * vector + (1 - alpha) * bm25` after max-normalising each side. `top_k` (default **20**) is the fusion /
  retrieval depth; `search` still returns at most the caller's `k` (the orchestrator's 3, §21 recall@3), so the model
  context is unchanged. An empty index degrades to BM25 — retrieval never fails because the index is empty.
- **Composition root** (`wiring.py`): a `make_knowledge(settings)` selector — `tfidf` (default) or `hybrid` — so the
  default path is byte-for-byte unchanged. `wiring` still validates every class's runbook ids.
- **CLI**: `argus runbooks index` (embed + upsert, idempotent, prunes removed passages) and
  `argus runbooks search "…" [--k N]`.
- **Migration**: `CREATE EXTENSION vector` + `runbook_passage` (`vector(1536)`, HNSW cosine index), granted to
  `argus_runtime`. Derived and rebuildable, so it is the one table the runtime role may replace (incident / evidence /
  audit stay insert-only).

## Configuration (settings / env)

| Setting | Default | Meaning |
|---|---|---|
| `ARGUS_RETRIEVAL` | `tfidf` | `tfidf` (baseline) or `hybrid` (pgVector + BM25) |
| `ARGUS_RETRIEVAL_TOP_K` | `20` | fusion depth and maximum results |
| `ARGUS_RETRIEVAL_ALPHA` | `0.5` | `0` = pure BM25, `1` = pure vector |
| `ARGUS_EMBEDDINGS` | `openai` | `openai` (needs a key) or `hashing` (offline) |
| `ARGUS_EMBEDDING_MODEL` | `text-embedding-3-small` | must produce `ARGUS_EMBEDDING_DIM` dims |
| `ARGUS_EMBEDDING_DIM` | `1536` | must match the column `vector(<dim>)` in the migration |
| `ARGUS_EMBEDDING_BASE_URL` | — | for an OpenAI-compatible embeddings endpoint |

## Database steps (owner-run, vm-095)

1. **Give Postgres the pgvector extension.** The stock `postgres:16-alpine` does **not** ship it; `CREATE EXTENSION
   vector` fails with *"could not open extension control file"*. Recreate `argus-v18-postgres` from an image that
   includes pgvector (for example `pgvector/pgvector:pg16`), keeping the same volume so the data survives. Confirm:
   ```bash
   docker exec argus-v18-postgres psql -U argus_owner -d argus -c "SELECT * FROM pg_available_extensions WHERE name='vector'"
   ```
2. **Apply the new migration** as the owner (`sudo bash ops/db-migrate.sh`). It runs `CREATE EXTENSION vector`, creates
   `runbook_passage`, the HNSW cosine index and the grants. Verify `argus db check` passes and
   `SELECT count(*) FROM runbook_passage` returns 0 without error.
3. **Build the index** from the worker host with the `openai_api_key` secret present and
   `ARGUS_RETRIEVAL=hybrid ARGUS_DB_BACKEND=postgres`: `argus runbooks index`. Re-run after any runbook change.
4. **Flip the agent** on the worker (`ARGUS_RETRIEVAL=hybrid`) only after the benchmark (§ below) shows the hybrid wins.

## Benchmark plan (TF-IDF vs hybrid — the comparison table)

- Extend `argus/evaluation` recall to run the same labelled cases through both retrievers at `k=3` and report
  **recall@3** (and ideally MRR@3 / nDCG@3) from `tests/eval/thresholds.yaml` (`runbooks` labels), following the
  `2026-10-13-EVAL-*` form (mean and worst case).
- Grid: `tfidf` vs `hybrid` for `alpha ∈ {0, 0.25, 0.5, 0.75, 1}` and `top_k ∈ {10, 20, 40}`.
- Done when: the table shows the hybrid's recall@3 versus the TF-IDF baseline; that result justifies (or rejects)
  offering the hybrid to a class and the §21.2 threshold change in ACR-0015.

## Tests (for the implementer)

A `tests/test_t0044_rag.py` with an offline corpus check (loader equivalence with TF-IDF), BM25 ranking, fusion
weighting (`alpha=0` → BM25, `alpha=1` → vector), `runbook_ids` filtering, empty-index degradation, and the `index()`
upsert against a stubbed pool (no live Postgres). The existing suite must stay green.

## Next step

A teammate reviews/accepts ACR-0015, then implements the design above (code + migration + tests), leases the VM for the
database step, builds the index and runs the benchmark. The architecture text (§15.3, §16.1, §21.2) and the version
bump are applied in that implementation pull request.
