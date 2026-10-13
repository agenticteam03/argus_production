# E2E-8 step 02 — evidence: the remaining scenarios ×5 through the runner (2026-10-13, conantkd, session 38abbb604d92)

Both leases. Both VMs on `main` `ad72617` (AFTER-MERGE the same day,
[evidence](../../AFTER-MERGE-main-2026-10-13/step-01/evidence.md)). The batches (which need the shared password) were
run by `conantkd` on the laptop; the agent read the results. Commands: [`code.bash`](code.bash). Sanitized: no
addresses, no secrets.

## 1. Batch 1: `run.py --runs 5 H-1 H-2 SC-09 SC-11` (no failure induced)

| Scenario | Pass | Runs (incident, outcome, duration) |
|---|---|---|
| H-1 | 5/5 | `inc_4ddc32dc77d6` no_incident 7 s; `inc_2d652963673f` no_incident 6 s; `inc_cc9c326328aa` no_incident 6 s; `inc_441a12e45e42` no_incident 6 s; `inc_9b4f661276cb` no_incident 6 s |
| H-2 | 5/5 | `inc_04fbb49c3487` no_incident 6 s; `inc_c42add492ac2` no_incident 6 s; `inc_2279d5c3e000` no_incident 6 s; `inc_d9a84c115e6a` no_incident 6 s; `inc_0f346e08bd0c` no_incident 6 s |
| SC-09 | 5/5 | `inc_d3b22f87ac4c` unsupported_escalated 11 s; `inc_7768d2f7be98` unsupported_escalated 6 s; `inc_9bfa0e7daeaa` unsupported_escalated 6 s; `inc_79d75fd99ba7` unsupported_escalated 6 s; `inc_ff0a346a64bf` unsupported_escalated 6 s |
| SC-11 | 5/5 | `inc_16f2395b1324` refused 7 s; `inc_12306fe87d91` refused 6 s; `inc_138ebe9a7301` refused 6 s; `inc_d552eb7f8e68` refused 6 s; `inc_6bfac2592ecd` refused 6 s |

20 runs, 18:14-18:16 UTC; 0 errors, no problem recorded. The runner checks NO INTERFERENCE after every run and stops
the batch otherwise.

## 2. Batch 2: `run.py --runs 5 SC-10 SC-12 ID-1` (Argus's own services stopped; two hosts at once)

Each run has two investigations (the runner sends them together and grades both); the cell lists both incidents.

| Scenario | Pass | Runs (incidents, outcomes, duration) |
|---|---|---|
| SC-10 | 5/5 | `inc_c358321fa5fb` no_action_escalated + `inc_06246ca75e5a` no_incident 20 s; `inc_ae0ce860bd7f` + `inc_929893de9e8a` 35 s; `inc_4a75fbd049a1` + `inc_0e8c33860f39` 34 s; `inc_40c94f69b22a` + `inc_b2bcbcb094cb` 35 s; `inc_c4d2be9fbbb2` + `inc_bb97553e55b3` 29 s (same outcomes) |
| SC-12 | **4/5** | **FAIL** `inc_abe543607681` diagnosed + `inc_ca8730855fc4` no_incident 66 s; `inc_de5b6ec114d7` no_action_escalated + `inc_8bf8473831e0` no_incident 662 s; `inc_09b55b68d787` + `inc_a69c2cd68d75` 659 s; `inc_aba7e28ff4f7` + `inc_676bd32d9fb1` 656 s; `inc_e9c6b0fe626d` + `inc_1305a40cd802` 640 s (same outcomes) |
| ID-1 | 5/5 | `inc_9130b3ff9172` diagnosed + `inc_e8cc72de8f75` diagnosed 662 s; `inc_3869c38532c3` + `inc_d83ad030d316` 662 s; `inc_09304bfe80ac` + `inc_0a7ac7634a4a` 662 s; `inc_75504fd77cc8` + `inc_8ff5a33a9fc3` 657 s; `inc_8c4960b217d4` + `inc_eef98323b026` 662 s (same outcomes) |

15 runs, 18:19-19:52 UTC; 0 errors; NO INTERFERENCE after every run.

- **SC-10** (18:19-18:22): vm-095's `argus-v18-node-exporter` stopped; `vm-095/host:vm-095` is
  `monitoring_blind_spot`, RB-014, `no_action_escalated`, **no model call** (graded `model: none`), reads on vm-095
  only; vm-166's api `no_incident`. The reset started the exporter every time (the next pre-gate saw `up == 1`).
- **ID-1** (19:07-19:52): SC-01 on vm-166 and SC-02 on vm-095 at once, the same container name on both hosts. Every
  run: two incidents, `container_restart_loop`, each with **its own host's** root cause and runbook (vm-166 RB-001,
  vm-095 RB-008), reads on that host only.
- **SC-12** (18:22-18:57): vm-166's `argus-v18-read-gateway` stopped during SC-01's OOM loop; vm-095's api
  `no_incident` in every run. Run 1 is the miss below. Runs 2-5 lasted ~11 min: the pre-gate waits until the
  10-minute restart window of the previous run is clean.

## 3. Reading the SC-12 miss (run 1) next to a pass (run 2)

Read from the store on vm-095 (`incident`, `evidence`; read-only `psql`).

| | Run 1 `inc_abe543607681` (FAIL: `diagnosed`) | Run 2 `inc_de5b6ec114d7` (PASS: `no_action_escalated`) |
|---|---|---|
| detector | 3 restarts in 10 min, OOMKilled, exit 137 | 5 restarts in 10 min, OOMKilled, exit 137 |
| `docker_read` (read gateway) | `status: error` (gateway stopped) | `status: error` (gateway stopped) |
| `prometheus` | memory history, ok (two samples) | memory history, ok (three samples) |
| `host_probe` | **two reads, ok**: `host.memory` (4,812 MiB available, no swap) and `host.kernel_oom_records` (6 memcg OOM kills of that container in 60 min, python, anon_rss 63.5 MiB) | none |
| conclusion | *"memory exhaustion within the argus-lab-worker container's memcg limit: the kernel recorded six memcg OOM kills of its Python process … while the host had 4,812 MiB available"*; root cause the worker, confidence high; says the memory history is sparse and the Docker reader unreachable | *"insufficient to distinguish a container-limit OOM from host-wide memory pressure"*; escalated |

- **Not a made-up diagnosis.** SC-12 was written (LGS) when the read gateway was the only way into a vm-166
  container: "never `diagnosed`" meant "no diagnosis without evidence". Since T-0019 batch 2 the **host probe** is a
  separate executor on vm-166. Run 1 used it and found the kernel's proof that the OOM is the container's own limit,
  which is exactly what run 2 said it was missing.
- **The degradation is right:** no crash, the failed read recorded as an error, vm-095 unaffected, and the diagnosis
  names its own gaps. The miss is the catalogue's expectation, not Argus.
- **Follow-up (option a, agreed with `conantkd`):** SC-12 accepts `diagnosed` only when no read of the stopped
  gateway succeeded and the root cause is the right container; the other outcomes stay. Its own task and PR.

## 4. Phase 12

| Scenario | Runs on the VMs (runner) |
|---|---|
| SC-01 … SC-08 | 5/5 each (E2E-1 to E2E-6) |
| H-1, H-2, SC-09, SC-10, SC-11, identity proof | 5/5 each (this step) |
| SC-12 | 4/5; the miss read and explained above (an expectation older than the host probe) |

Every scenario has five runs and every miss is read: **Phase 12 is done** by E2E-8's rule.
