# T-0038 — `compare_incident_baseline`: one metric now against the same window earlier

| Field | Value |
|---|---|
| Status | `in progress` — step 1 (code, offline) done 2026-10-13; step 2 (read on the VMs) next |
| Phase | 4 / 9 — Level 3 capabilities ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)) |
| Architecture | no change (no ACR): the §12 Level 3 row `metrics.compare_baseline` ("same signals over an earlier healthy window; no stored baseline") |
| Branch | `task/T-0038-compare-baseline`, **on top of `task/T-0036-metric-histories`** (it uses T-0036's signals and the client's `mounts`): merge #119 first |
| Owner | `conantkd` (+ agent) |
| Needs the VM lease | step 2 only (one-off read-only container on vm-095) |

## Goal (plain language)

"Is this level unusual for this target, or is it normal for it?" The model names a metric and how far back to look;
Argus reads the same named signal for the current window and for the same window 1 hour, 24 hours or 7 days earlier,
and answers the mean and maximum of each and the change. Nothing is stored. Offered to no class until measured.

## Design

- **Args:** `metric` ∈ memory, cpu, restarts, disk, network (never a signal name or PromQL); `minutes` 5–240;
  `earlier` ∈ 1h, 24h, 7d.
- **Metric → signal by target kind:** container: memory `container_memory_bytes`, cpu `container_cpu_cores`, restarts
  `container_restart_count`; host: memory `host_memory_available_ratio`, cpu `host_cpu_busy_ratio`, disk
  `host_disk_used_ratio_mounts` (the declared mounts), network `host_network_bytes_per_s`. A pair that does not
  exist (a container's disk) is refused (`invalid_args`), never guessed.
- **`PrometheusClient.range(..., end_offset_s=)`**: the same window ending that many seconds ago.
- A window without samples is said so ("NO DATA (unknown, not zero)", `partial`); both empty = an error result.
- Level 3, `READ_ONLY_SAFE`, executor `prometheus`, `max_per_incident` 2, tag `baseline` (no class has it).

## Tests

`tests/test_t0038_compare_baseline.py`, 14 (red seen: no capability): spec and policy; now vs 24 h earlier (both
reads, offsets, text, values); the signal per metric and kind; disk with the declared mounts and 7 days; refused
pairs; a window without samples; the model cannot name a signal, an unknown offset or a window above 240; the client
and the replay take the offset.

## Steps

1. **Code (offline)** — done 2026-10-13.
2. **Read on the VMs** from a one-off container (as T-0036 step 2).
3. **Offer to a class** with an evaluation batch (later).
