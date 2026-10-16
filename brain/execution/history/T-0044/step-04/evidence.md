# T-0044 step 4 — evidence: task suspended, vm-095 back to main (2026-10-15, conantkd, session 0ec3a32ee8cd)

Decision (conantkd): T-0044 is **suspended**. The comparison (step 3) points at the corpus and the cases, not the
retriever (health scores 0 for every retriever; title stubs and action/validation sections crowd the top 3; about 5
cases per class). The team improves the runbooks and expands the eval cases first (§15.3, §21.2), then resumes this
task and re-measures with `argus runbooks compare`. Commands: [`code.bash`](code.bash).

| Block | Observed | Result |
|---|---|---|
| S.1 vm-095 | `SESSION OK`; `BACKUP OK` (2266151 bytes); weaviate container and volume removed; `DEPLOY OK: 1d222ad13f8b (main)`; agent, worker, scheduler recreated on image `5eb30894fdbd`, `health 200`, `restarts=0`; no startup errors; `20/20`; `55/55`; `WRITE GATE CLOSED`; `weaviate containers left: 0`; `commit=1d222ad` `ref=main`; `LAB BASELINE OK`; `NO INTERFERENCE` | OK |

State: vm-095 on `main` `1d222ad`, no Weaviate; vm-166 not touched; leases released. The branch
`task/T-0044-weaviate-rag` (#157, draft) keeps the code, the measurement tool and steps 1–4.
