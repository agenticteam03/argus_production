# T-0037 — The missing Level 2 docker_read verbs: processes, Docker disk use, windowed and searched logs

| Field | Value |
|---|---|
| Status | `in review` — step 1 (code) and step 2 (the routes on vm-166, [evidence](../../execution/history/T-0037/step-02/evidence.md)) done 2026-10-13; step 3 after the merge |
| Phase | 4 / 9 — tools; Level 2 capabilities ([`../../IMPLEMENTATION_PLAN.md`](../../IMPLEMENTATION_PLAN.md)) |
| Architecture | no change (no ACR): implements four rows of the §12 Level 2 table as written |
| Branch | `task/T-0037-docker-read-verbs` (from `main`) |
| Owner | `conantkd` (+ agent) |
| Needs the VM lease | step 2 (a one-off read-only container on vm-166; no service changed) and the AFTER-MERGE |

## Goal (plain language)

Four reads the architecture lists for diagnosis were missing: what runs inside a container, how much disk Docker
itself uses, the logs of a time window, and whether a known kind of failure appears in the logs. They are added to
the read gateway (exact GET routes on this host's allowlisted containers) and to the catalogue, offered to no class
until an evaluation batch measures them.

## Design

| Capability (model name) | Gateway route | What leaves the host |
|---|---|---|
| `container.processes` (`get_container_processes`) | `/containers/{name}/top` | PID, PPID and the command's **name** only, at most 50; never its arguments (a command line can carry a password; `host.process_details` keeps the same rule) |
| `docker.disk_usage` (`get_docker_disk_usage`, host target) | `/docker/df` | `/system/df` reduced to totals: images, containers, volumes (each with its unused part), build cache; **no name** |
| `container.detailed_logs` (`get_detailed_logs`) | `/containers/{name}/logs_window?minutes=&stream=` | 1–120 minutes, at most 500 lines (500 characters each), `both` / `stdout` / `stderr`; redacted on the agent side as every observation |
| `container.search_logs` (`search_logs`) | `/containers/{name}/search?pattern=&minutes=` | one of a **fixed set of named patterns** (`error`, `timeout`, `refused`, `oom`, `disk_full`, `auth`, `restart`; never free text, never a regex from the model): the count and up to 50 matching lines |

The pattern names are the same on both sides (`LOG_PATTERNS` in the gateway, `SEARCH_PATTERNS` in the catalogue; a
test keeps them equal). Level 2, `READ_ONLY_SAFE`; `max_per_incident` 4 / 2 / 4 / 6; tags `processes`,
`docker_disk`, `detailed_logs`, `search_logs`: no class has them yet.

## Tests

`tests/test_t0037_docker_read_verbs.py`, 12 (red seen: no route, no capability): the processes never carry arguments
(a `--db-password=` in the fixture), the disk use carries no name, the log window and stream are bounded and refused
outside, only a named pattern is accepted (also by the args model), a container outside the allowlist is refused, the
pattern names match, the four specs and their policy entries, each capability's route and text.

## Steps

1. **Code (offline)** — done 2026-10-13.
2. **The routes on vm-166:** the branch's `service.py` run in a one-off container with the Docker socket read-only
   (no service changed): the four routes on lab containers.
3. **After the merge:** the target services rebuilt on both hosts (AFTER-MERGE); then offer to a class with an
   evaluation batch.
