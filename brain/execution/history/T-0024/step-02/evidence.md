# T-0024 steps 02-04 — evidence: SC-05 on vm-166, DIAGNOSED from the pulled alert (2026-10-09, conantkd, session 21a9ce710773)

Mutating, both VMs, run by the agent over SSH on `conantkd`'s order (`code.bash` in this folder). Sanitized: no
addresses, no secrets. Ref `task/T-0024-sc05-disk` `b049086` on both hosts.

| Check | Result |
|---|---|
| B.1 vm-095 | `DEPLOY OK: b049086113f7`; agent/worker/scheduler rebuilt (class `disk_pressure`, the filler in the inventory); target services recreated (host-probe `rslave`); node-exporter recreated (`rslave`); Prometheus recreated; TOOLS ISOLATION OK; LAB BASELINE OK; NO INTERFERENCE |
| M.1 vm-166 | `SESSION OK`; `DEPLOY OK: b049086113f7`; `lab-fill: mounted /srv/argus-lab-fill size=224M used=1%`; target services, node-exporter and Prometheus recreated |
| M.2 the mount seen | node-exporter: `/` 49436 MiB, `/srv/argus-lab-fill` 224 MiB, `ext4`; `host_disk_used_ratio_5m` 0.272 (the root disk is the worst declared mount); host-probe `/disk?mount=/srv/argus-lab-fill`: total 223 MiB, 2.3 % used (not the root disk's 27 %); LAB BASELINE OK |
| S.1 fill | filler 11:09: "/fill is 223 MiB ... writing 2 MiB every 3 s up to 92%"; lab fs 92.6 % by ~11:14 ("reached 92.6% after 202 MiB; holding"); `used_5m` 0.908 at 11:19:09, 0.926 at 11:19:39 with **`HostDiskPressure` firing**, present in vm-166's Alertmanager |
| Step 4 pull | scheduler 11:19:49 `{'vm-166': {'started': 1}}`; 11:20:49 `{'duplicate': 1}` |
| Step 4 incident | `inc_4d78232433a1`, target `vm-166/host:vm-166`, principal `alertmanager@vm-166`, **DIAGNOSED**, `disk_pressure`, root cause `vm-166/container:argus-lab-filler`; findings "93% used for at least 5 minutes", time to full; reads `host.disk_usage`, `container.list` (host), `container.status`, `container.logs`, `container.resources` (filler), all on vm-166; diagnosis: the filler wrote and holds 202 MiB on `/srv/argus-lab-fill` (92.6 %, 16 MiB free), the root fs is separate (27.7 %); human action: stop the filler and remove only its known fixture; **no unscoped prune or deletion of unrelated data** |
| S.2 reset | filler and its file removed; lab fs 1 % (kept mounted, empty); 0 active alerts 11:21:08; LAB BASELINE OK; NO INTERFERENCE (vm-166 and vm-095) |

**Observation:** `host_disk_hours_to_full` uses a 15-minute `deriv`, so after the filler stopped growing it still
reported ~1 min to full (the finding said so). Correct while it grows; it lags a stop by up to 15 minutes.

**Result:** T-0024 steps 2-4 done: SC-05 detected from node-exporter, alerted, pulled and DIAGNOSED with the writer as
the root cause, without proposing to delete unrelated data.
