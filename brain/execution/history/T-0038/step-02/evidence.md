# T-0038 step 2 — evidence (2026-10-13 UTC, conantkd's agent over ssh; both leases, session 4f8a9d4f8dc1)

Goal: `compare_incident_baseline` against both hosts' Prometheus with the branch's code, without touching a service
(as T-0036 step 2: an image from the branch built in `/tmp`, a one-off container, `config/` read-only, no secret).

| Target, metric, earlier | Observed (`3a36322`) | Result |
|---|---|---|
| vm-166 `argus-lab-api`, memory, 24h | `ok`: now mean 1.13e7 max 2.00e7; 24h earlier mean 1.13e7 max 2.01e7; mean x0.997 | OK |
| vm-166 `argus-lab-api`, cpu, 1h | `ok`: now mean 0.00777; 1h earlier 0.00792; x0.98 | OK |
| vm-166 host, disk (declared mounts), 24h | `ok`: 0.26266 vs 0.26208; x1 | OK |
| vm-166 host, network, 1h | `ok`: 452.9 vs 452.6 bytes/s; x1 | OK |
| vm-095 host, memory, **7d** | `ok`, partial: now 0.745; **7d earlier: NO DATA (unknown, not zero)** | **finding** |
| vm-166 `argus-lab-api`, disk | `error`: "disk is not compared for a container (choose one of cpu, memory, restarts)" | OK (refused) |
| after | `checkout local modifications: 0`; `NO INTERFERENCE` | OK |

**Finding and fix:** both Prometheus keep 7 days (`--storage.tsdb.retention.time=7d`,
`deploy/monitoring/compose.monitoring.yml`), so a window ending 7 days ago falls at the edge of what is kept: NO DATA
on vm-095. The capability said so correctly (unknown, partial), but the option is useless. The offsets are now 1h,
24h and **3d** (the test says why). Left on vm-095: the image `argus-v18-agent:t0038` (not used by any service).
