# T-0044 step 3 — evidence: TF-IDF vs the hybrid at the section level (2026-10-15, conantkd, session 38fca4f6c9f1)

Goal: a metric that can tell two retrievers apart, and the TF-IDF vs hybrid table on the real index. Commands:
[`code.bash`](code.bash). Labels: [`tests/eval/section_labels.yaml`](../../../../../tests/eval/section_labels.yaml).

**Method.** 44 class cases with runbook labels. The query of each is the recall node's own, captured by replaying the
case offline with TF-IDF (`python -m argus.evaluation.retrieval`). A case's useful sections are the six diagnostic
sections (Symptoms, Plausible causes / hypotheses, Required evidence, Diagnostic workflow, Decision tree, Evidence
interpretation) of its labelled runbooks, plus RB-009's for `dep-backend-wrong-network`. Per retriever: runbook
recall@3, section hit@3 (at least one useful section in the top 3), section precision@3 (useful share of 3). The hybrid
runs on vm-095's Weaviate with the provider's embeddings (`argus runbooks compare`, one-off container, query embeddings
memoised across alphas); `-titles` drops each runbook's title stub (`ARGUS_RETRIEVAL_SKIP_TITLES`).

## C.1 — index: sections embedded as `RB-xxx <section>`

| Retriever | runbook recall@3 | section hit@3 | section precision@3 |
|---|---|---|---|
| **tfidf** | **1.000** | 0.636 | 0.250 |
| hybrid a=0 / -titles | 1.000 / 1.000 | 0.227 / 0.386 | 0.076 / 0.129 |
| hybrid a=0.25 / -titles | 1.000 / 1.000 | 0.205 / 0.432 | 0.083 / 0.197 |
| hybrid a=0.5 / -titles | 0.977 / 0.932 | 0.455 / 0.523 | 0.152 / 0.235 |
| hybrid a=0.75 / -titles | 1.000 / 0.909 | 0.477 / 0.545 | 0.159 / 0.242 |
| hybrid a=1 / -titles | 1.000 / 0.909 | 0.545 / 0.682 | 0.205 / 0.326 |

Without the title stubs the remaining sections did not say which runbook they belong to: the restart loop mixed RB-001
(OOM) and RB-008 (crash), runbook recall 0.33 for that class.

## C.2 — index rebuilt: sections embedded as `RB-xxx <runbook title> — <section>`

| Retriever | runbook recall@3 | section hit@3 | section precision@3 |
|---|---|---|---|
| **tfidf** | **1.000** | 0.636 | 0.250 |
| hybrid a=0 / -titles | 1.000 / 1.000 | 0.227 / 0.386 | 0.076 / 0.129 |
| hybrid a=0.25 / -titles | 1.000 / 1.000 | 0.295 / 0.477 | 0.114 / 0.212 |
| hybrid a=0.5 / -titles | 0.977 / 0.977 | 0.318 / 0.659 | 0.129 / 0.242 |
| hybrid a=0.75 / -titles | 0.977 / 0.909 | 0.682 / **0.705** | 0.250 / 0.273 |
| hybrid a=1 / -titles | 0.955 / 0.977 | 0.636 / 0.636 | 0.273 / **0.280** |

Per class, section hit@3:

| Class | tfidf | hybrid a=0.75 -titles | hybrid a=1 -titles |
|---|---|---|---|
| container_restart_loop | **1.00** | 0.33 | 0.33 |
| cpu_saturation | **1.00** | 0.80 | 0.20 |
| dependency_unavailable | **1.00** | 0.40 | 0.40 |
| disk_pressure | 0.00 | **1.00** | **1.00** |
| health_check_failed | 0.00 | 0.00 | 0.00 |
| monitoring_blind_spot | 0.40 | **1.00** | **1.00** |
| nginx_upstream_failure | 1.00 | 1.00 | 1.00 |
| postgresql_connection_exhaustion | 1.00 | 1.00 | 1.00 |

## Reading

- The hybrid is much better where TF-IDF fails (disk: 0 → 1, blind spot: 0.4 → 1) and worse where TF-IDF already
  works (restart loop, dependency, CPU). No configuration is at least as good on every measure, so by §21.2 **TF-IDF
  stays the default**; `ARGUS_RETRIEVAL=hybrid` remains opt-in.
- Health is 0 for every retriever: the health query (class + "health check reports unhealthy" + reason) lands on
  RB-002's Incident definition / Trigger / False positives. A corpus or query question, not a retriever one.
- Embedding the runbook title into each section (C.2) is kept: it is what lets `-titles` keep the runbook right.
- Next candidates, not done here: fuse TF-IDF and vector ranks (reciprocal rank fusion) instead of Weaviate's BM25,
  and per-case section labels where the class-level set is too coarse.

The run: 31 s per full grid; `NO INTERFERENCE` after each. The running worker was never changed (one-off containers);
`/tmp/t0044` removed; leases released. vm-095's index now holds the C.2 form (sections with titles), which is what
this branch's `index()` builds.
