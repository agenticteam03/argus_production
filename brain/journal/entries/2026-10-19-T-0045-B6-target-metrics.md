## 2026-10-19 — T-0045 B6: `GET /api/v1/target-metrics` and `GET /api/v1/overview`

Type: implementation
Who: juanbetancurm (+ agent)
Context: the redesigned UI has a dashboard and, for one box of the map, a drawer with its recent charts. Step B6 of
[T-0045](../../tasks/current/T-0045-ui-insights-backend.md) adds the two routes. `/target-metrics` was built first (it
depended on no open pull request); `/overview` after B3 (#175) and B4 (#176) merged. ACR-0021's least-privilege
approval for the two public-edge routes was given by `juanes6554` on #182.
Decision / result:
- `GET /api/v1/target-metrics?target=<host/kind:name>&range=15m|1h` (`argus/application/target_metrics.py`): a fixed
  series list per kind, read with `MetricsPort.range` on the target's own host only. A container gives
  `container_cpu_quota_used_ratio_5m` and `container_memory_bytes`. A host gives `host_cpu_busy_ratio`,
  `host_memory_used_ratio` (1 - the available ratio, its lines flipped as in `/host-metrics`) and
  `host_disk_used_ratio`. Another kind gives no series yet. Each series carries `kind`, `unit`, `max` and the B1
  `thresholds` (or `null`); at most ~130 points; missing is `null`, an unreadable series is all gaps. Shared 30 s per
  (target, range). A target not in the inventory is 404; a malformed target or another range is 422 before any read.
- `GET /api/v1/overview` (`argus/application/overview.py`): `status` (the worst open severity, `ok` when nothing is
  open), `open_incidents` by severity, the 5 newest open incidents (severity and summary from B4; `info` while the class
  is unknown; `next_action` `null` until B4's `next_actions` are filled), `hosts` (the `/host-metrics` rows: one shared
  20 s snapshot for both routes), `fleet` (boxes by B3 `health`), `links` (`ok`/`total` of the declared dependencies),
  `last_closed_at`. Built from the newest `incidents_limit_cap` incidents and the topology and host-metrics snapshots:
  no new host read, no executor call. Shared 15 s.
- Any authenticated role for both; no PromQL, address or internal URL in or out.
- Edge: `location = /api/v1/target-metrics` and `location = /api/v1/overview` (GET only, rate-limited); the contract,
  two samples and `API-FOR-UI.md`.
- Built in `build_api` from the existing metrics port, thresholds, store and topology, so `wiring.py` is unchanged.
- `ARCHITECTURE.md` 1.8.18 → 1.8.19: the two §7.1 rows, the public-edge paragraph and the changelog; ACR-0021's
  rows say applied through B6. The `GET /api/v1/incidents` row loses filters the route never had (`limit` and
  `parent_id` only).
Consequences: two more public read routes; the browser chooses only an inventory target and one of two ranges.
References: [ACR-0021](../../architecture/changes/ACR-0021-ui-insights-v2.md), `docs/API-FOR-UI.md`.

### Test state

`tests/test_t0045_b6_target_metrics.py` and `tests/test_t0045_b6_overview.py` (new, red seen first: the modules did not
exist); the edge matrix and the UI contract list both routes; `tests/test_ui_access.py` passes `/target-metrics` its
required `target` (a read token reads every GET route); `contracts/ui-api.json` regenerated and
`contracts/samples/target-metrics.json` and `overview.json` added (the other samples untouched).

### Next step

B7 (baseline, long ranges, deploy events); the `ARCHITECTURE.md` text of ACR-0021 (§5.8, §7.1, §8.1) now that B1-B4
are merged.
