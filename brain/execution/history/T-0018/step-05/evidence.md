# T-0018 step 05 — evidence (2026-10-07 05:03–05:10 UTC; conantkd, session 796fd4f3bf61)

Goal: SC-07 on vm-166 — a healthy backend on the wrong Docker network. Argus must diagnose a network
misattachment, not a failed backend.

V.1 was run both by `conantkd` and, 20 s later, by the agent over SSH (`up -d` is idempotent: the containers were
created at 05:03:17 and not recreated). V.2 (needs the user's password) and V.3 were run by `conantkd`. Key output
lines, SANITIZED (no VM addresses, no secrets, no personal names).

| Block | Expected | Observed | Result |
|---|---|---|---|
| V.1 session + before | `SESSION OK`, snapshot | `SESSION OK`; `saved … before.txt (87 lines)` | OK |
| V.1 induce | backend healthy; client on `argus-lab-app`, backend on `argus-lab-iso` | `backend health=healthy`; `/argus-lab-client networks=argus-lab-app`; `/argus-lab-backend networks=argus-lab-iso` | OK |
| V.1 symptom | client errors | `ERROR cannot reach http://argus-lab-backend:8080/health: [Errno -3] Try again` | OK |
| V.1 signal (readiness gate) | `argus_probe_success{owner="argus-lab-client"}` = 0 | `none` (first scrape not in yet), then `0`; `VERDICT V.1 OK` | OK |
| V.2 detect | `dependency_unavailable` | `incident inc_fb92d115abb2`; scope client, backend, host vm-166; `dependency_probe_min=0.0`; class `dependency_unavailable`, `model_loop` | OK |
| V.2 recall | RB-003 (+ branches) | RB-003 v1.0.0 (2 sections), RB-004 v1.0.0; **RB-009 not recalled** (see below) | partial |
| V.2 investigate (vm-166 only) | status, DNS/TCP from the app network, logs | step 1 `container.status` of client and backend (both running; the status carries `networks`); step 2 DNS of the client resolved; step 3 container list (backend running); step 4 logs of both; step 5 DNS of the backend **FAILED** and TCP `argus-lab-backend:8080` **FAILED** from vm-166's app network; step 6 conclude | OK |
| V.2 record | `DIAGNOSED`, a network misattachment | `outcome: DIAGNOSED · class dependency_unavailable`; `root cause: vm-166/container:argus-lab-backend · confidence high`; diagnosis: *"the declared backend dependency is not attached to the client's application network. The client is on argus-lab-app while the backend is only on argus-lab-iso … The client is the victim; the backend is running and listening, so its process is not shown to be failed … correct the deployment/network attachment … Do not restart containers based on the current evidence."*; 6 cited observations; `VERDICT V.2 OK` | OK |
| V.3 reset | both containers and the network removed; baseline | `SC-07 containers gone`; `argus-lab-iso gone`; `LAB BASELINE OK`; `NO INTERFERENCE: non-Argus objects unchanged`; `T-0018.5 SC-07 DONE` | OK |

nonint-check: NO INTERFERENCE on vm-166 (yes). vm-095 only ran the read-only diagnosis.

**Result:** SC-07 passes (one run). Argus tells "healthy backend on the wrong network" apart from "backend down",
names both networks, and advises against restarting. The deciding evidence was the new `networks` field of the
container status (step 1), confirmed by DNS and TCP failing from the client's network (step 5).

**Follow-up:** RB-009 (the DNS/network runbook) was not recalled. It is a *branch* runbook of
`dependency_unavailable`, and this run never retrieved it. The diagnosis did not need it, but RB-009's
`last_tested` stays `null` until a run actually uses it (a `dns_network_failure` class, or branch retrieval on
network findings).
