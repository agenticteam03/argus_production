# E2E-3 step 02 — evidence: both VMs on `main` with `host_mounts`, and SC-05 / SC-08 ×5 (2026-10-11, conantkd, session 0e96417eb3e8)

Both leases. A, D.1 and D.2 were run by the agent over SSH; B.1 (the batch, which needs the shared password) by `conantkd` on the laptop.
Commands: `code.bash` in this folder. Sanitized: no addresses, no secrets.

## 1. State probe and deploy (13:10-13:19 UTC)

| Check | Result |
|---|---|
| A vm-095, vm-166 | both `commit=0f076f2…` `ref=main` (E2E-2 step 2), LAB BASELINE OK, every `argus-v18-*` Up, NO INTERFERENCE |
| D.1 vm-166 deploy | `DEPLOY OK: e3286dfe27ac (main)` |
| D.1 rebuild | read-gateway, host-probe, network-probe, exporter recreated and Up; `host_mounts` in the gateway image: 1 |
| D.1 after | lab filesystem mounted; LAB BASELINE OK; NO INTERFERENCE |
| D.2 backup | `BACKUP OK argus-20261011T131837Z.dump` (12 tables, 19381 rows) |
| D.2 deploy + rebuild | `DEPLOY OK: e3286dfe27ac (main)`; agent, worker, scheduler running, restarts 0 |
| D.2 database | `20/20 database checks passed` |
| D.2 `/healthz` | ok; `policy_version=987032aaddc8`, `inventory_version=60b8907a2584` (both unchanged: no policy or inventory change) |
| D.2 new code loaded | in the worker, `container.status`'s description names the filesystems and its "when" names a disk incident: `True True` |
| D.2 write gate | `WRITE GATE CLOSED: argus-v18-agent,argus-v18-worker,argus-v18-scheduler read-only` |
| D.2 after | LAB BASELINE OK; NO INTERFERENCE |

## 2. Batch: `run.py --runs 5 SC-05 SC-08` (about 13:25-15:00 UTC)

| Scenario | Pass | Runs (incident, duration) |
|---|---|---|
| SC-05 | **3/5** | PASS `inc_f5b2bbbdc3c8` 637 s, PASS `inc_8744b6c130e6` 703 s, PASS `inc_29fe9702a07d` 662 s, **FAIL `inc_047b8eece8a3`** 631 s, **FAIL `inc_81698a6c8fa9`** 722 s (both: root cause the host) |
| SC-08 | **5/5** | `inc_cf3d4058181f` 54 s, `inc_3252539c4939` 360 s, `inc_eb1c1d7747d1` 376 s, `inc_9a3e291dd8f8` 365 s, `inc_77fdfdfcad6a` 361 s |

0 errors; the runner checks NO INTERFERENCE after every run and stops the batch otherwise. SC-08's first repeated
runs: 5/5 (T-0029: 1/1). SC-05: 3/5, against 4/5 in E2E-2 step 2. With five runs each, the two results cannot be
told apart.

## 3. Reading the SC-05 misses (runs 4, 5) next to a pass (run 3)

The incidents were read from the store on vm-095 with a read-only `get_incident` / `list_evidence` in `argus-v18-worker`.

| | Run 3 `inc_29fe9702a07d` (PASS) | Runs 4 `inc_047b8eece8a3`, 5 `inc_81698a6c8fa9` (FAIL) |
|---|---|---|
| `host.disk_usage` | `vm-166:/ used=26.2%; vm-166:/srv/argus-lab-fill used=92.6% free=16 MiB` | the same |
| `container.status` filler | running, `host_mounts=/srv/argus-lab-fill(rw) other_binds=1` | **the same: the E2E-3 fact reached the model** |
| further reads | `host.disk_usage` of the mount, **`container.logs` of the filler** | none (two reads) |
| conclusion | *"the running container argus-lab-filler is intentionally filling its writable host mount … the source of the host filesystem saturation"*, root cause the filler | run 4: *"has a read-write mount on this filesystem, making it the identified likely writer, but the available evidence does not prove its write rate"*; run 5: *"a plausible writer, but the supplied evidence does not prove that it is the source"*; root cause the host, confidence high |

- **E2E-3's link works:** every run saw `host_mounts=/srv/argus-lab-fill(rw)`, and both misses name the filler as
  the likely writer. In E2E-2 the miss did not know about the link at all.
- **The remaining gap is a confirmation read, not a missing fact.** A rw mount does not prove the writer (task
  "Limits"). The model asks for proof of the write, which only the logs or the resources give, and in the misses it
  concludes without reading them. The pass read here (run 3) read the filler's logs, as did E2E-2's run 4; runs 1
  and 2 were not read.
- Next: a follow-up task. The proposal is in the task file.
