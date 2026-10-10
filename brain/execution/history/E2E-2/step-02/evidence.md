# E2E-2 step 02 — evidence: vm-095's agent on `main`, and SC-05 / SC-07 ×5 again (2026-10-10, conantkd, session 2a68b62c2aee)

Both leases. D.1 and D.2 run by the agent over SSH; B.1 (the batch, the shared password) by `conantkd` on the laptop.
Commands: `code.bash` in this folder. The incident texts in §3 are quoted from the store on vm-095 (a read-only
`get_incident` / `list_evidence` in `argus-v18-worker`). Sanitized: no addresses, no secrets.

## 1. Deploy (22:00-22:02 UTC)

| Check | Result |
|---|---|
| D.1 vm-166 | `deploy.sh main`: `DEPLOY OK 0f076f2`; no rebuild (nothing there changed); LAB BASELINE OK; lab filesystem mounted; NO INTERFERENCE |
| D.2 backup | `BACKUP OK argus-20261010T220044Z.dump` (12 tables, 18076 rows) |
| D.2 deploy + rebuild | `DEPLOY OK 0f076f2 (main)`; agent, worker, scheduler recreated, running, restarts 0 |
| D.2 database | `20/20 database checks passed` |
| D.2 `/healthz` | ok; `policy_version=987032aaddc8` (unchanged), `inventory_version=60b8907a2584` (was `06c170840543`: the declared networks) |
| D.2 new code loaded | `DiskArgs().mount` is `None`; SC-07's client and backend declare `argus-lab-app` |
| D.2 write gate | `WRITE GATE CLOSED: argus-v18-agent,argus-v18-worker,argus-v18-scheduler read-only` |
| D.2 after | LAB BASELINE OK; NO INTERFERENCE |

## 2. Batch: `run.py --runs 5 SC-05 SC-07` (22:27-23:30 UTC)

| Scenario | Pass | Runs (incident, duration) |
|---|---|---|
| SC-05 | **4/5** | PASS `inc_5ab2c6efa7b7` 636 s, PASS `inc_05d6cda889a3` 662 s, PASS `inc_10149f1a00a1` 668 s, PASS `inc_8f50182d5700` 667 s, **FAIL `inc_de65a12688bc`** 688 s (root cause the host) |
| SC-07 | **5/5** | `inc_1b7e2c7438a0` 85 s, `inc_6a26ba1794fc` 70 s, `inc_a8e3fc7f3585` 80 s, `inc_c0d12a72470e` 65 s, `inc_dce072190f52` 75 s; all root cause the backend, RB-003 |

0 errors, every reset clean, NO INTERFERENCE after every run (the runner stops the batch otherwise). Before E2E-2:
SC-05 6/10, SC-07 6/10 ([E2E-1 step 3](../../E2E-1/step-03/evidence.md)).

## 3. Reading the SC-05 miss (run 5) next to a pass (run 4)

| | Run 4 `inc_8f50182d5700` (PASS) | Run 5 `inc_de65a12688bc` (FAIL) |
|---|---|---|
| `host.disk_usage` | `vm-166:/ used=28.0%; vm-166:/srv/argus-lab-fill used=92.6% free=16 MiB` | the same |
| `container.status` filler | running, restarts 0, `networks=none` | the same |
| further reads | **`container.logs` and `container.resources` of the filler** | none |
| conclusion | *"the running argus-lab-filler container deliberately allocated and is holding 202 MiB on /srv/argus-lab-fill"*, root cause the filler | *"/srv/argus-lab-fill is the saturated mount … the evidence does not prove it is the writer"*, root cause the host, confidence high |

- **The SC-05 gap is closed.** Every run read the right filesystem (92.6 %), so none escalated on the 93 % / 28 %
  contradiction; before E2E-2, 4 of 10 runs did that.
- **The miss is a different one: nothing links the filler to the mount.** In run 5 the model stopped after one round of
  reads. The only proof that the filler writes `/srv/argus-lab-fill` is in its logs. Without reading them, naming
  the host and saying the writer is unproven is a correct reading of what it had. The diagnosis is honest; the label
  (the filler) is right.
- **SC-07's gap is closed:** 5/5 named the backend (before: the client 4 times and the host once in 10).

Possible general fix (not done here): `container.status` reports the container's host mounts, as it now reports its
declared networks. Then the read that shows the filler running would also show that it writes the full filesystem.
