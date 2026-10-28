## 2026-10-28 - The cache's dependents probe it with Redis PING, not only a TCP connect

Type: fix
Who: conantkd (+ agent)
Context: in the second S1 rehearsal the judge doubted the `container.start` on the cache: "RB-003 requires
confirmation that the dependency itself accepts the intended protocol under normal credentials; this is not
evidenced." It was right. `argus_probe_success`, behind `dependency_probe_min` and the proposal's verification, was
only a TCP connect, so a Redis that accepted connections but did not answer would read as healthy.
Decision / result:
- `config/inventory.yaml`: the cache target declares `protocol: redis`.
- `ops/render_target_config.py`: a dependency's probe carries its `protocol`; an unknown protocol stops the render.
  `deploy/target/config/vm-166.json` is re-rendered: both cache probes (api, jobworker) carry `redis`.
- `services/target/service.py`: `redis_ping` sends `PING` and wants `+PONG` (it reads and changes nothing); a connect
  failure keeps its kind, any other answer is `kind="protocol"`. `probe_lines` uses it for a probe with that protocol
  and a TCP connect otherwise.
- `argus/application/links.py`: the map's broken link says "no protocol answer" for that kind.
- From vm-166's exporter, `PING` to `argus-lab-cache:6379` answers `+PONG`.
Consequences: `dependency_probe_min` for the cache's dependents now means the cache answered its protocol, which is
what the S1 proposal's verification checks. The judge's packet still does not say what the signal measures; a short
ACR amending ACR-0019 section 3.8 (verification and precheck plans in the packet) follows the demo.
References: [demo plan](../../tasks/current/DEMO-argus-acts.md), RB-003, ACR-0021, T-0045 B8.

### Test state

`tests/test_redis_protocol_probe.py`, five tests, all red without the change: PONG only is ok (a NOAUTH answer and
silence are `protocol`), a closed port keeps `refused`, a probe with a protocol asks it and one without only connects,
the rendered vm-166 config and the refused unknown protocol, and the link reason. The neighbouring probe, link and
render files pass locally (the stale-config test included); CI is the full check.

### Next step

Merge, rebuild vm-166's target, and repeat S1.
