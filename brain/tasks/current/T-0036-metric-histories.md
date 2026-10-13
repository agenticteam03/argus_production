# T-0036 — The missing Level 2 metric histories: CPU, disk and network

| Field | Value |
|---|---|
| Status | `in review` — step 1 (code) and step 2 (read on both hosts, [evidence](../../execution/history/T-0036/step-02/evidence.md)) done 2026-10-13; step 3 (offer to a class) later |
| Phase | 9 — Level 2 capabilities ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)) |
| Architecture | no change (no ACR): implements the §12 Level 2 table as written (`get_cpu_history`, `get_disk_history`, `get_network_history`); §"extension": a metric-history capability = a signal template + a capability |
| Branch | `task/T-0036-metric-histories` (from `main`) |
| Owner | `conantkd` (+ agent) |
| Needs the VM lease | step 2 only (one-off read-only container on vm-095; no service changes) |

## Goal (plain language)

The architecture lists four metric histories for the model; only memory (and restarts) existed. This adds CPU, disk
and network, the same way: named signal templates, a bounded window, NO DATA = unknown, never free-form PromQL. They
are offered to no class until an evaluation batch measures them (as the snapshot, T-0034).

## Design

- **Signals** (`config/signals.yaml`, read only by these capabilities): `container_cpu_cores` (cAdvisor, 3m rate),
  `host_disk_used_ratio_mounts` (the fullest of the host's declared mounts), `host_network_bytes_per_s`
  (node-exporter, received + sent on the real interfaces: not `lo`, `veth*`, `docker*`, `br-*`). The host CPU uses
  the existing `host_cpu_busy_ratio`.
- **Capabilities** (Level 2, `READ_ONLY_SAFE`, executor `prometheus`, `max_per_incident` 4):
  - `metrics.cpu_history` / `get_cpu_history`: a container's cores in use, or a host's busy share;
  - `metrics.disk_history` / `get_disk_history`: host only; the declared mounts come from the inventory (as
    detection's `$mounts`); none declared = NO DATA (unknown), never a guess of `/`;
  - `metrics.network_history` / `get_network_history`: a **host's** bytes per second. Step 2 found that cAdvisor
    runs with `--disable_metrics=…,network` (memory): there is no per-container traffic series. Per-container
    traffic needs that decision (enable cAdvisor's network metrics and measure its memory) — not taken here.
- **`PrometheusClient.expr/range(..., mounts=)`**: fills `$mounts`, plain absolute paths only (the inventory's own
  check); anything else is refused. The evaluation replay accepts the parameter.
- Tags `cpu_history`, `disk_history`, `network_history`: no class has them yet.

## Tests

`tests/test_t0036_metric_histories.py`, 14 (red seen: no `mounts` parameter in the client): the three specs (level,
safety, executor, target kinds, policy entry), offered to no class, the signals are named templates on the host, CPU
by target kind, disk from the declared mounts (none = unknown), network, no samples = unknown, the client refuses a
mount that is not a plain path, the replay accepts the parameter.

## Steps

1. **Code (offline)** — done 2026-10-13.
2. **Read on the VMs:** an image from this branch, a one-off container on vm-095 (read-only, nothing restarted) runs
   the three capabilities against both hosts' Prometheus: real samples, labels, and NO DATA where expected.
3. **Offer to a class** (later, with an evaluation batch), as for the snapshot.
