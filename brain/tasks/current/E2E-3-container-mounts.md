# E2E-3 — `container.status` shows the host filesystems a container writes (the SC-05 writer link)

| Field | Value |
|---|---|
| Status | `in progress` — proposed 2026-10-10 by `conantkd`; step 1 (offline) done 2026-10-11 by `juanbetancurm`; step 2 after the merge |
| Phase | 12 (end-to-end tests) — [`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md) |
| Found by | [E2E-2 step 2](E2E-2-evidence-gaps.md): SC-05 4/5, the miss `inc_de65a12688bc` ([evidence](../../execution/history/E2E-2/step-02/evidence.md)) |
| Architecture | no change expected (no ACR): one more field from the container inspect the read-gateway already does; read-only, no new access |
| Branch | `task/E2E-3-container-mounts` (from `main`) |
| Owner | `juanbetancurm` (+ agent), quality lane |
| Needs the VM lease | step 2: **both** (the read-gateway on vm-166, the agent on vm-095), then vm-166 for the re-run |

## Goal (plain language)

In SC-05 the model sees `/srv/argus-lab-fill` at 92.6 % and the filler running, but nothing in that evidence says the
filler writes that filesystem; only its logs do. When it does not read them (run 5) it names the host and says the
writer is unproven. Give it the link as a fact: which declared host filesystems a container has mounted, and whether
read-write.

Docker already knows this, so nothing is declared per container (unlike E2E-2's networks, which are an intent). It
holds for any container and scenario, not only SC-05.

## Plan

### Step 1 (offline, test first)

- **Read-gateway** (`services/target/service.py`, `inspect()`): add `mounts`, the bind sources with `rw`/`ro`, from
  the same `/containers/<name>/json` call it already makes.
- **Catalogue** (`argus/capabilities/catalog.py`, `container_status`): match each source to the host's declared mounts
  (`config/inventory.yaml`, the longest prefix) and add e.g. `host_mounts=/srv/argus-lab-fill(rw)` to the model text.
  A source under no declared mount other than `/` is counted, not named. Nothing under the deploy home's `secrets/`
  is printed, and the stored `values` hold no more than the model text names.
- Tests: the gateway with `rw` and `ro` binds and no bind; the match to declared mounts; an undeclared path is not
  named; a container without mounts gives the same text as today.

**As built (2026-10-11):** the matching is done **in the read-gateway**, not in the catalogue: `inspect()` matches
each bind source to the host's declared mounts (its own config, rendered from the inventory; the longest prefix, `/`
names nothing) and returns only `host_mounts` (the declared mount and `rw`) and `other_binds` (a count). A source
outside the declared mounts never leaves the gateway, so nothing under the deploy home or its `secrets/` can reach the
agent, the store or the model (stricter than "not printed": not even in `values`). Docker volumes are not binds and
are skipped. `container.status` adds `host_mounts=/srv/argus-lab-fill(rw)` and `other_binds=N` when present; a
container without them, or an older gateway, gives exactly today's text. Tests: `tests/test_e2e3_container_mounts.py`
(5; red seen 4/5, the fifth pins the unchanged text); every test that loads the gateway passes; the baseline
evaluation is unchanged (45/47, hard 0 0 0). **Review of #75 (`conantkd`):** the tool's description and "when" now
say it returns the host mounts ("in a disk incident, which container writes the full filesystem"): the SC-05 miss
never read the filler, so the model must know the link is there before it reads (the same lesson as SC-07, whose
description gained "networks"). + 1 test (red seen).

### Step 2 (after the merge, both leases)

1. vm-166: `deploy.sh main`, rebuild the read-gateway; vm-095: backup, `deploy.sh main`, rebuild agent, worker and
   scheduler, `argus db check`, `/healthz`, WRITE GATE CLOSED, NO INTERFERENCE.
2. `ops/e2e/run.py --runs 5 SC-05` (about 55 minutes). Done when SC-05 is 5/5, or the misses are read and explained.

## Limits

A read-write mount does not prove the container is the one filling it. With two writers on one filesystem the model
still needs logs or resources to tell them apart. In SC-05 the filler is the only in-scope container with that mount.

## Not chosen

- `writes_to:` in the inventory: faster, but a hand-written fact per container that Docker already knows.
- `host.disk_usage` listing the containers on each mount: the best view from a host incident, but the host-probe has no
  Docker access; crossing two executors in one capability can come later on top of this.
- A runbook or prompt line "read the logs before naming the host": it nudges the model, it does not give it the fact.
