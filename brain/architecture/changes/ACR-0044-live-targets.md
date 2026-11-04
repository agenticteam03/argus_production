# ACR-0044 — Which inventory targets exist and run; Podman, systemd units and host processes as targets

| Field | Value |
|---|---|
| Status | `proposed` |
| Proposed by | conantkd (+ agent) · 2026-10-30 |
| Accepted by | — (review of the pull request) |
| Second approval (safety principle only) | **required**: secrets (each host's Prometheus now holds the `host_probe` token, as it holds `db_probe`'s since T-0020) |
| Architecture version | 1.8.51 → 1.8.52 |
| Task / PR | [T-0059](../../tasks/current/T-0059-live-targets.md) · the pull request that adds this file |

## 1. Detect and explain

The UI's "Start an investigation" form lists every target of `config/inventory.yaml` (`GET /api/v1/targets`, ACR-0012): 17
targets today, most of them lab scenario containers that exist only while their scenario runs. An operator cannot tell which
of them are on the host. The data is almost there: the exporter inspects every declared container every 10 s, but it
publishes nothing for a container Docker does not know, and nothing that says "stopped" in a way the map reads. The map
(ACR-0017) derives a container's state from `restarts_10m` and `health_unhealthy`; a stopped container still publishes its
restart count, so `restarts_10m` = 0 showed it as **running** (`tests/test_t0059_live_targets.py`, red before this change).

Beyond Docker: a host may run its applications under Podman, as systemd units, or as plain scripts. Argus can name a
`service` target (a registered kind since v1.8) but nothing observes one, and a process cannot be a target at all.

## 2. Why the current architecture is insufficient

- §4.1 lists what the argus-exporter publishes (lifecycle facts) but no contract for "this target exists / runs", so each
  consumer guesses from other signals.
- §4.6 gives the host probe no verb for a systemd unit or a declared process, and §5.1's kinds have no `process`.
- §1.3 has no class for a service or a process; `classes_for("service")` is empty, so an investigation of one ends
  `unsupported`.
- §4.4 and §4.5 assume Docker's socket path.

## 3. Smallest reasonable change

1. **A presence contract (§4.1).** Every observer publishes, for each declared target it watches,
   `argus_target_present{kind,name}` (1 the target is on the host, 0 it is not) and `argus_target_up{kind,name}` (1 it
   runs). No series means the observer did not say: `unknown`, never absent. Named signals `target_present` and
   `target_up` (`$kind` joins `$host` and `$name` as a template parameter, filled from the validated `TargetRef`).
   - The **exporter** says it for containers (Docker's 404 is absent; any other failed read publishes nothing).
   - The **host probe** says it for systemd units (present: a unit file is installed; up: a process is in the unit's
     cgroup, read from `/proc/<pid>/cgroup`, no D-Bus, no `systemctl`) and for declared processes (found by `comm` or a
     `pidfile`; declared, so always present; up while one runs). Its `/metrics` is scraped with its own token, as the
     db-probe's is.
2. **State, not a new list (§5.8, §7.1).** The inventory stays the only list of what Argus may investigate. The map's
   boxes get `presence` (`running`, `stopped`, `absent`, `unknown`); `GET /api/v1/targets` adds `state` from the same
   shared readings (no new host read); the UI hides `absent` targets unless the operator asks for all of them.
3. **Podman (§4.4, §4.5).** `ARGUS_CONTAINER_SOCKET` in a host's env file names the runtime's socket (Podman's
   Docker-compatible API); inside the gateway containers the path stays `/var/run/docker.sock`, so the code is the same.
4. **Two kinds (§5.1).** `service` is a systemd unit `<name>.service`; `process` (new) is a host process with
   `process: {comm}` (at most 15 characters) or `process: {pidfile}` (a plain absolute path). Never a command line.
5. **Reads and a class (§1.3, §4.6, §12.2).** `service.status` and `process.status` (Level 1, `READ_ONLY_SAFE`, host
   probe), tagged so that no model class is offered them. A new class `target_down` (availability; RB-023; strategy
   `evidence_pack`: the read of the unit or process and the host's memory and CPU, then escalation, no diagnosis claimed)
   for a target that is present and not up; alert `TargetDown` (`for: 1m`) opens it.

**Alternatives considered:**
- A: **Discover targets** (list every container, unit and process on the host and make them investigable). Rejected: the
  inventory is the scope boundary (policy, service cards, write pairs); discovery may later *suggest* inventory entries.
- B: **Filter on the existing signals only** (`restarts_10m` present means running). Rejected: a stopped container reads
  as running, an absent one is indistinguishable from a monitoring gap.
- C: **Give the exporter `/proc` and `/rootfs`** for units and processes. Rejected: the exporter's `/metrics` has no token
  and it would gain host mounts; the host probe already has them behind its token.
- D: **Ask systemd over D-Bus.** Rejected: a socket into PID 1's manager is more privilege than reading cgroup files;
  the restart count it would add is left for later.

## 4. Consequences

- Code: `services/target/service.py` (exporter presence lines; host probe `/metrics`, `services/<unit>/status`,
  `processes/<name>/status`), `ops/render_target_config.py` (`services`, `processes`), `config/signals.yaml`,
  `argus/adapters/outbound/config_adapters.py` (`$kind`; inventory validation of service and process targets),
  `argus/application/topology.py` (`presence`), `GET /api/v1/targets` (`state`), the catalog, policy, class, alert,
  evidence pack, alert intake (`kind`/`name` labels name the target), RB-023, the UI form.
- Deployment: render the target config, rebuild the target services on both hosts, copy the host-probe token into
  `/opt/argus-v18/secrets/prometheus/host_probe_token` (owner nobody, 400) and reload Prometheus, then the core and the UI.
  Before the exporter is rebuilt, every state reads `unknown` and nothing is hidden.
- Risk: a host whose `/proc/<pid>/cgroup` does not name the unit (a unit with `Delegate=` sub-cgroups still does) reads as
  not running; `scrape_targets_down` now also counts the host-probe job, so a host probe that cannot be scraped is a
  blind spot (as it should be). A stale pidfile whose pid was reused reads as running.
- How to reverse it: drop the `argus-v18-host-probe` scrape job and the `TargetDown` rule; the UI shows every target again
  when `state` is absent from the answer.
- Does it touch a **safety principle**? **Yes, secrets**: a second consumer (Prometheus) holds the host-probe token. Read-only,
  host isolation and the write gate are unchanged: every new verb is a read on the target host, allowlisted by the
  rendered config.

## 5. Decision

Proposed; to be accepted in the pull request's review, with the second approval for the secrets principle.

## 6. Applied

- [x] `ARCHITECTURE.md` updated, version bumped, changelog line added (with this ACR's link)
- [x] journal entry
- [x] the ACR, the architecture change and the first code that needs it are in the same pull request
