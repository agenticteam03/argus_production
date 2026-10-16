# T-0044 step 2 — evidence: the hybrid retriever on vm-095 with a real index (2026-10-15, conantkd, session cd8044e6d88e)

Goal: vm-095 on the PR branch `task/T-0044-weaviate-rag` (#157, `5751405`), `argus-v18-weaviate` started, the index built
from the worker with the provider's embeddings, and the hybrid compared with TF-IDF on one query per class. The worker
stays `ARGUS_RETRIEVAL=tfidf`. Leases: vm-095 + vm-166. Commands: [`code.bash`](code.bash). Times UTC.

| Block | Observed | Result |
|---|---|---|
| R.1 state probe | `commit=5d4b347` `ref=main`; `LAB BASELINE OK`; `NO INTERFERENCE`; 4240 MiB available; I/O avg10 0.72 | OK |
| R.2 branch + Weaviate + core | `BACKUP OK` (2266151 bytes); `DEPLOY OK: 5751405ce646 (task/T-0044-weaviate-rag)`; volume and `argus-v18-weaviate` created; ready 200 **from the worker**; agent, worker, scheduler recreated, `health 200`, all `restarts=0`; `retrieval=tfidf weaviate=http://argus-v18-weaviate:8080`; no startup errors; `20/20`; `55/55`; `WRITE GATE CLOSED`; `weaviate host ports: 0`; `ref=task/T-0044-weaviate-rag`; `LAB BASELINE OK`; `NO INTERFERENCE` (no new listener) | OK |
| R.3 index | `indexed 630 sections of 21 runbooks (library 1.1.1) into RunbookPassage …; 630 objects stored` in 23.3 s; Weaviate 84 MiB, worker 103 MiB | OK |
| R.4 comparison | nine queries, every one answered by the hybrid (no fallback); Weaviate 91 MiB; `NO INTERFERENCE` | OK |

## R.4 — top 3, hybrid vs TF-IDF (query = class + typical findings + reason; the class's runbooks)

| Class (query) | Hybrid | TF-IDF |
|---|---|---|
| health_check_failed | RB-002 Trigger/detection, RB-002 title, RB-002 Incident definition | RB-002 Incident definition, Trigger/detection, False positives |
| restart loop, OOM | **RB-001** title, RB-001 Trigger/detection, RB-008 title | RB-001 Required tools, Scope, Lab validation |
| restart loop, crash | **RB-008** title, RB-001 title, RB-001 Trigger/detection | RB-008 Symptoms, RB-001 Required tools, RB-001 Trigger/detection |
| dependency_unavailable (no shared network) | RB-003 title, **RB-009** Trigger/detection, RB-003 User impact | RB-003 Diagnostic workflow, Incident definition, User impact (no RB-009) |
| postgresql_connection_exhaustion | RB-004 title, Incident definition, Evidence interpretation | RB-004 Scope, Verification, Evidence interpretation |
| disk_pressure | **RB-005** title, RB-019 Incident definition, RB-019 title | **RB-019** Incident definition (first), RB-005 title, RB-019 Root-cause correction |
| cpu_saturation | RB-006 title, Symptoms, Evidence interpretation | RB-006 Evidence interpretation, Lab validation, Diagnostic workflow |
| nginx_upstream_failure | **RB-015** Incident definition, title, Symptoms | **RB-003** Required tools (first), RB-015 Incident definition, Symptoms |
| monitoring_blind_spot | RB-014 title, False positives, Decision tree | RB-014 Decision tree, Diagnostic workflow, Trigger/detection |

Reading: the hybrid picks the **right runbook first** more often (disk → RB-005, nginx → RB-015, crash → RB-008, and
RB-009 appears for a network cause), but it favours each runbook's **title section** (`RB-xxx — …`, mostly a summary),
while TF-IDF more often returns working sections (Diagnostic workflow, Evidence interpretation, Decision tree). Neither
is better at the section level by eye: step 3 labels the useful sections per case and measures both.

## State at the end

vm-095 on `task/T-0044-weaviate-rag` `5751405` (until #157 merges and an AFTER-MERGE returns it to `main`),
`argus-v18-weaviate` running with the 630-section index, the worker on TF-IDF. vm-166 not touched. Leases released.
