## 2026-10-27 - T-0056: Weaviate's memory sized for the installed corpus

Type: implementation
Who: conantkd (+ agent)
Context: DEPLOY-7f137da installed and indexed the reference bundle (20,251 passages). Weaviate then held 425 MiB of its
512 MiB limit while idle, above its 400 MiB `GOMEMLIMIT`; the limits came from a 2026-10-15 trial with 6,510 objects
(210 MiB peak). Hybrid retrieval stayed off for that reason.
Decision / result:
- `argus-v18-weaviate`: `mem_limit` and `memswap_limit` 768m, `GOMEMLIMIT` 640MiB (about 85 % of the limit, so Go
  collects before the kernel kills). vm-095 had about 4 GB available during the deploy.
- The deployment test pins both values.
Consequences: after the merge: recreate `argus-v18-weaviate` on vm-095 (both leases), set
`ARGUS_CORPUS_RETRIEVAL=hybrid` in `/opt/argus-v18/hosts.env`, recreate the worker, run a few reference searches and
read Weaviate's peak memory. Rollback: the previous limits and `keyword` (the default); retrieval fails open to
keywords meanwhile.
References: DEPLOY-7f137da's evidence (PR #357), [T-0056 task](../../tasks/current/T-0056-reference-corpus.md).

### Test state

`tests/test_t0056_reference_corpus.py`, the compose split and phase 16's network tests: green.

### Next step

The VM step above, after the merge.
