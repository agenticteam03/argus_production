# T-0044 — Evaluate a locally-hosted (open-source) Weaviate for hybrid runbook retrieval behind `KnowledgePort`

| Field | Value |
|---|---|
| Status | **`suspended`** (2026-10-15, conantkd) — steps 1–3 done (code; the index on vm-095; the section-level comparison: TF-IDF stays the default); the runbook corpus and the eval cases are improved first; vm-095 back on `main` without Weaviate ([step 4](../../execution/history/T-0044/step-04/evidence.md)); #157 is a draft |
| Phase | 5 / 9 — retrieval over the runbook corpus ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)) |
| Architecture | **ACR-0015** (applied, 1.8.13): §15.3 "no vector store" → evaluate a self-hosted Weaviate behind `KnowledgePort`; a §16.1 row and one deployment container |
| Branch | `task/T-0044-weaviate-rag` (implementation); `task/T-0044-rag-pgvector` was the ACR (#155) |
| Owner | `juanes6554` (+ agent) — proposer; `conantkd` (+ agent) — implementation |
| Needs the VM lease | the evaluation (deploy local Weaviate, build the index) and the benchmark |

## Problem

Runbook recall in the orchestrator is pure **TF-IDF** (`argus/adapters/outbound/config_adapters.py::TfidfRunbooks`),
built at startup, `k=3`. §21.2 targets recall@3 ≥ 0.9; the lab wants a stronger retriever and a TF-IDF-vs-RAG
comparison. The owner asks to **evaluate Weaviate** as the store for that retriever, run **locally**: Weaviate is open
source, so it is self-hosted in the lab as a container on Host A (private Docker network), **not** used through a
managed/cloud API and with no API key.

## Design (for the implementer)

- **One corpus loader for both retrievers** — a small module (e.g. `argus/adapters/outbound/runbook_corpus.py`):
  runbook IDs from metadata (never file names), one `##`-section per passage, an over-long section refused (never cut),
  the pinned `Safety and approval contract` sections shared. `TfidfRunbooks` is refactored onto it so the two
  retrievers agree on *what* a passage is and differ only on *ranking*.
- **`EmbeddingPort`** in `argus/ports/ports.py`, with two adapters: an OpenAI embeddings adapter (production,
  `text-embedding-3-small`, 1536 dims, batched + retried) and a deterministic keyless one (offline tests / smoke run,
  never for quality). Weaviate stores the vectors; the adapter that fills them lives in Argus.
- **Hybrid adapter behind `KnowledgePort`** (`search(query, k, runbook_ids)` unchanged), backed by the local Weaviate:
  BM25 (k1=1.5, b=0.75) and dense neighbours fused as `alpha * vector + (1 - alpha) * bm25` after max-normalising each
  side, **or** Weaviate's native hybrid query if the evaluation shows it equivalent. `top_k` (default **20**) is the
  fusion / retrieval depth; `search` still returns at most the caller's `k` (the orchestrator's 3, §21 recall@3), so
  the model context is unchanged. An empty index degrades to BM25 — retrieval never fails because the index is empty.
- **Weaviate client**: official `weaviate` Python client pointed at the **local** instance (no Cloud/API credentials),
  one collection for runbook passages (properties: runbook id, version, status, section, content, sha256), cosine
  distance, an optional local reranker module. Connection details from settings; no credentials in code.
- **Composition root** (`wiring.py`): a `make_knowledge(settings)` selector — `tfidf` (default) or `hybrid` — so the
  default path is byte-for-byte unchanged. `wiring` still validates every class's runbook ids.
- **CLI**: `argus runbooks index` (embed + upsert into the local Weaviate, idempotent) and
  `argus runbooks search "…" [--k N]`.
- **Deployment**: a self-hosted `weaviate` service definition (open-source image, port, network,
  `mem_limit`/`cpus`/`pids_limit`) following the existing deployment rules; the index is derived and rebuildable from
  `argus/runbooks/`. No external/cloud vector service is involved.

## Configuration (settings / env)

| Setting | Default | Meaning |
|---|---|---|
| `ARGUS_RETRIEVAL` | `tfidf` | `tfidf` (baseline) or `hybrid` (local Weaviate + BM25) |
| `ARGUS_RETRIEVAL_TOP_K` | `20` | fusion depth and maximum results |
| `ARGUS_RETRIEVAL_ALPHA` | `0.5` | `0` = pure BM25, `1` = pure vector |
| `ARGUS_WEAVIATE_URL` | — | the **local** Weaviate endpoint (e.g. `http://argus-v18-weaviate:8080`) |
| `ARGUS_WEAVIATE_CLASS` | `RunbookPassage` | the Weaviate collection/class |
| `ARGUS_EMBEDDINGS` | `openai` | `openai` (needs a key) or `hashing` (offline) |
| `ARGUS_EMBEDDING_MODEL` | `text-embedding-3-small` | must match the vectors stored in Weaviate |
| `ARGUS_EMBEDDING_BASE_URL` | — | for an OpenAI-compatible embeddings endpoint |

## Weaviate steps (owner-run, vm-095)

1. **Deploy Weaviate locally** as a new `argus-v18-*` container on Host A using the **open-source** image (for example
   `cr.weaviate.io/semitechnologies/weaviate:<pin>`; the `text2vec-*`/`reranker` modules are optional when Argus
   supplies its own vectors), its own port in the 18000–18799 range, its own named volume, the private Docker network,
   and the usual `mem_limit`/`cpus`/`pids_limit`. No cloud account, no API key. Nothing in the protected lab is touched.
2. **Smoke check**: `curl http://<host>:<port>/v1/.well-known/ready` returns 200.
3. **Build the index** from the worker host with the `openai_api_key` secret present and
   `ARGUS_RETRIEVAL=hybrid ARGUS_WEAVIATE_URL=…`: `argus runbooks index`. Re-run after any runbook change (idempotent).
4. **Flip the agent** on the worker (`ARGUS_RETRIEVAL=hybrid`) only after the benchmark (§ below) shows the Weaviate
   hybrid wins. Rollback is `ARGUS_RETRIEVAL=tfidf` and stopping the container.

## Benchmark plan (TF-IDF vs local Weaviate hybrid — the comparison table)

- Extend `argus/evaluation` recall to run the same labelled cases through both retrievers at `k=3` and report
  **recall@3** (and ideally MRR@3 / nDCG@3) from `tests/eval/thresholds.yaml` (`runbooks` labels), following the
  `2026-10-13-EVAL-*` form (mean and worst case).
- Grid: `tfidf` vs Weaviate `hybrid` for `alpha ∈ {0, 0.25, 0.5, 0.75, 1}` and `top_k ∈ {10, 20, 40}`; optionally
  with/without Weaviate's reranker.
- Done when: the table shows the Weaviate hybrid's recall@3 versus the TF-IDF baseline; that result justifies (or
  rejects) offering it to a class and the §21.2 threshold change in ACR-0015.

## Tests (for the implementer)

A `tests/test_t0044_rag.py` with an offline corpus check (loader equivalence with TF-IDF), BM25 ranking, fusion
weighting (`alpha=0` → BM25, `alpha=1` → vector), `runbook_ids` filtering, empty-index degradation, and the `index()`
upsert against a stubbed Weaviate client (no live service). The existing suite must stay green.

## Next step

A teammate reviews/accepts ACR-0015, then implements the design above (local Weaviate container + code + tests), leases
the VM for the deployment, builds the index and runs the benchmark. The architecture text (§15.3, §16.1, §21.2) and the
version bump are applied in that implementation pull request.

## Steps

1. **Code (offline)** — done 2026-10-15. `argus/adapters/outbound/rag.py`: `HashingEmbeddings`, `OpenAIEmbeddings`
   (batched, order kept), `WeaviateIndex` (REST/GraphQL on `httpx`: schema, batch, Weaviate's native hybrid with a
   `runbook_id` filter), `HybridRunbooks` (`KnowledgePort`: Weaviate ranks, the text comes from the library matched by
   SHA-256, stale entries skipped, any failure → TF-IDF, counted and logged; `index()` rebuilds idempotently with
   stable ids). `wiring.make_knowledge` (`tfidf` default, refuses a misconfigured hybrid); the replay pins `tfidf`;
   `argus runbooks index|search [--compare]`; `argus-v18-weaviate` in `compose.core.yml` (as measured in the capacity
   trial, plus `ENABLE_API_BASED_MODULES=false`, no host port), the worker's `ARGUS_RETRIEVAL` (default `tfidf`) and
   `ARGUS_WEAVIATE_URL`. Design changes from above: the native hybrid instead of a client-side fusion, no official
   client. Tests: `tests/test_t0044_rag.py`, 20 (red seen: no `rag` module).
2. **vm-095** — done 2026-10-15 ([evidence](../../execution/history/T-0044/step-02/evidence.md)): the branch deployed,
   `argus-v18-weaviate` up (no host port), 630 sections indexed from the worker in 23 s with real embeddings, the
   hybrid answering every query (no fallback); the worker stays `tfidf`.
3. **Comparison** — done 2026-10-15 ([evidence](../../execution/history/T-0044/step-03/evidence.md)): section labels
   by class (`tests/eval/section_labels.yaml`), the recall node's own queries replayed offline
   (`python -m argus.evaluation.retrieval`), `argus runbooks compare` on vm-095. TF-IDF: runbook recall@3 1.000,
   section hit@3 0.636, precision 0.250. Best hybrid (sections embedded with their runbook title, title stubs skipped):
   hit 0.705 (alpha 0.75) or precision 0.280 (alpha 1), runbook recall 0.909–0.977: better on disk and blind spot,
   worse on restart loop, dependency and CPU. **TF-IDF stays the default** (§21.2); `hybrid` and
   `ARGUS_RETRIEVAL_SKIP_TITLES` are opt-in.
4. **Suspended** — 2026-10-15 ([evidence](../../execution/history/T-0044/step-04/evidence.md)): vm-095 back on `main`,
   Weaviate removed. To resume: deploy the branch, start `argus-v18-weaviate`, `argus runbooks index`, re-measure.
5. **When resumed (not started):** rank fusion of TF-IDF and vectors; per-case labels where the class set is too coarse; the
   health query, which no retriever serves.
