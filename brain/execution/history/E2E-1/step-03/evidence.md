# E2E-1 step 03 — evidence: what the misses read, and batch 2 (2026-10-10, juanbetancurm, session cf7b8b638801)

Both VMs on `main` (SC-04-SC-08 code as deployed by DEPLOY-MAIN-2). Commands: `code.bash` in this folder. Sanitized:
no addresses, no secrets. The incident texts below are quoted from the store on vm-095 (read-only).

## 1. The three misses of batch 1, read from the store (plus one SC-05 pass)

| Incident | What the model read | What it concluded |
|---|---|---|
| SC-05 run 1 `inc_3e6af419ab13` (FAIL) | metric snapshot `host_disk_used_ratio_5m` 0.926; `host.disk_usage` **twice, both `vm-166:/ used=28.0%`**; the filler running | escalated: *"Evidence is contradictory … the incident metric reports 92.6% used … while two direct host probes … report / at 28.0% used"* |
| SC-05 run 3 `inc_c18ea3c6bcf3` (FAIL) | the same, `host.disk_usage` **four times, every one on `/`** | escalated, the same contradiction |
| SC-05 run 2 `inc_e95c47cbfdc9` (PASS) | the same `/` reads, plus the filler's logs | diagnosed the filler, **confidence medium**, still noting *"the direct host probe shows vm-166:/ at only 28.0% used … contradicting"* |
| SC-07 run 4 `inc_e7e415955549` (FAIL) | `container.status` of both: client `networks=argus-lab-app`, backend `networks=argus-lab-iso`, healthy; RB-009 | *"attached to different Docker networks … a network attachment/topology mismatch (RB-009 H2), with the client as the victim"*, but root cause **the client** |

## 2. Batch 2: `--runs 5 SC-07 SC-05` (17:29-18:33 UTC)

| Scenario | Pass | Runs (incident, root cause named) |
|---|---|---|
| SC-07 | **2/5** | FAIL `inc_f4296f4ad078` client, PASS `inc_fbf0b1b92b2d` backend, FAIL `inc_a6829f60f3f2` client, PASS `inc_f03ea2b598ca` backend, FAIL `inc_f5c71b0ab881` **host** |
| SC-05 | **3/5** | PASS `inc_b78fe0d48333`, FAIL `inc_e5c1d54d24ee` escalated, PASS `inc_825810ea7a65`, FAIL `inc_06902e660f38` escalated, PASS `inc_4bbd0df32c3f` |

0 errors, every reset clean, NO INTERFERENCE after every run. **Over both batches: SC-07 6/10, SC-05 6/10.**

## 3. Reading: two gaps in the evidence, not model noise

- **SC-05: Argus reads the wrong filesystem.** The detector fires on a declared mount (`/srv/argus-lab-fill`, 92.6 %)
  and its finding says only "a declared filesystem"; `host.disk_usage`'s `mount` defaults to `/`, so every read the
  model made returned the root disk (28 %). Faced with 93 % vs 28 %, escalating is the right behaviour on that evidence.
- **SC-07: the assigned network is not in the evidence.** The scenario's truth is that the backend is on the wrong
  network (`argus-lab-iso`; the lab's network is `argus-lab-app`), but that is written only in comments
  (`config/inventory.yaml`, `compose.lab.yml`). Argus sees two containers on two networks and must guess which one is
  misplaced: it named the client 4 times and the host once in 10. The label (backend) is right.

Both fixes give the model the missing fact; they are code (E2E-2): `host.disk_usage` without a mount reports every
declared mount, and the inventory declares each container's networks so `container.status` shows a container that is
not on them.
