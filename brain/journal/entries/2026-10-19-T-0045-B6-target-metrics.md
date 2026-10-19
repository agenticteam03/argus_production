## 2026-10-19 — T-0045 B6 (first half): `GET /api/v1/target-metrics`

Type: implementation
Who: juanbetancurm (+ agent)
Context: the redesigned UI opens a drawer for one box of the map with its recent charts. B6 adds two routes; this is
the one that depends on no open pull request. `/api/v1/overview` needs B3 (#175) and B4 (#176) merged first. B6 waits
for ACR-0021's least-privilege approval (#182): a new route on the public edge needs the second approval.
Decision / result:
- `GET /api/v1/target-metrics?target=<host/kind:name>&range=15m|1h` (`argus/application/target_metrics.py`): a fixed
  series list per kind, read with `MetricsPort.range` on the target's own host only. A container gives
  `container_cpu_quota_used_ratio_5m` and `container_memory_bytes`. A host gives `host_cpu_busy_ratio`,
  `host_memory_used_ratio` (1 - the available ratio, its lines flipped as in `/host-metrics`) and
  `host_disk_used_ratio`. Another kind gives no series yet.
- Each series carries `kind`, `unit`, `max` and the B1 `thresholds` (or `null`); at most ~130 points; a missing
  sample is `null`, an unreadable series is all gaps. One shared answer per (target, range) for 30 s.
- A target not in the inventory is 404; a malformed target or a range other than 15m/1h is 422 before any read. Any
  authenticated role. No PromQL, address or internal URL in or out.
- Edge: `location = /api/v1/target-metrics` (GET only, rate-limited); the contract, a sample and `API-FOR-UI.md`.
- Built in `build_api` from the existing metrics port and thresholds, so `wiring.py` (a hotspot that #174 and #175
  edit) is unchanged.
Consequences: one more public read route; the browser chooses only an inventory target and one of two ranges.
References: [ACR-0021](../../architecture/changes/ACR-0021-ui-insights-v2.md), `docs/API-FOR-UI.md`.

### Test state

`tests/test_t0045_b6_target_metrics.py` (new, red seen first: the module did not exist); the edge matrix and the UI
contract list the route; `tests/test_ui_access.py` passes the route its required `target` (a read token reads every
GET route); `contracts/ui-api.json` regenerated and `contracts/samples/target-metrics.json` added (the
other samples untouched).

### Next step

B6's `/api/v1/overview` after #175 and #176 merge; B7 after #174.
