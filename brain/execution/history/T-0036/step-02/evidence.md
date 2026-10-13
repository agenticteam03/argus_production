# T-0036 step 2 — evidence (2026-10-13 UTC, conantkd's agent over ssh; both leases, session 4f8a9d4f8dc1)

Goal: the three histories read on both hosts' Prometheus with the branch's code, without touching a service.

How: on vm-095 the branch was fetched into the checkout's git (no checkout change: `checkout local modifications: 0`),
exported with `git archive` to `/tmp`, built as `argus-v18-agent:t0036`, and a one-off container on `argus-v18-core`
(the branch's `config/` read-only, no secret mounted) called each capability's `impl` with a `PrometheusClient` on the
inventory's Prometheus URL (vm-166 through the tunnel). `/tmp` was removed after.

| Run | Capability, target | Observed | Result |
|---|---|---|---|
| 1 (`9f7cd59`) | `get_cpu_history` vm-166 `argus-lab-api` | `ok`, 61 samples, 0.006–0.009 cores | OK |
| 1 | `get_cpu_history` vm-166 host | `ok`, 61 samples, busy share 0.036–0.100 | OK |
| 1 | `get_disk_history` vm-166 host (mounts `/`, `/srv/argus-lab-fill`) | `ok`, 61 samples, 0.2626–0.2629 | OK |
| 1 | `get_disk_history` vm-095 host | `ok`, 61 samples, 0.2127–0.2200 | OK |
| 1 | `get_network_history` `argus-lab-api` on vm-166 and vm-095 | `error` NO DATA (unknown, not zero) on both | **finding** |
| 2 (`4b67800`) | the four above again | the same values | OK |
| 2 | `get_network_history` vm-166 host | `ok`, 61 samples, 409–454 bytes/s | OK |
| 2 | `get_network_history` vm-095 host | `ok`, 61 samples, 444–461 bytes/s | OK |
| after | NO INTERFERENCE | `NO INTERFERENCE: non-Argus objects unchanged` | OK |

**Finding and fix:** the per-container network history had no data on either host because cAdvisor runs with
`--disable_metrics=…,network` (`deploy/monitoring/compose.monitoring.yml`, to keep its memory low): no
`container_network_*` series exist. The capability answered NO DATA as designed (unknown, never zero). Fixed in
`4b67800`: `get_network_history` reads the host's traffic on its real interfaces (node-exporter,
`host_network_bytes_per_s`). Per-container traffic needs a separate decision (enable cAdvisor's network metrics and
measure its memory).

Left on vm-095: the image `argus-v18-agent:t0036` (not used by any service).
