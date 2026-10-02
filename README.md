# Argus

Argus is an SRE incident-diagnosis agent for servers and containers. When an alert fires, a schedule ticks or an
operator asks, it detects the symptom deterministically, recalls runbooks, investigates with narrow, read-only,
audited tools, and concludes or escalates to a human. It is **read-only** in this phase.

- **Start here (developers and AI agents):** [`brain/README.md`](brain/README.md).
- Architecture: [`brain/architecture/ARCHITECTURE.md`](brain/architecture/ARCHITECTURE.md) (v1.8.x).
- Where we stand: [`brain/CURRENT_STATE.md`](brain/CURRENT_STATE.md).

## Run the tests (laptop)

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test,dev]"
.\.venv\Scripts\pre-commit install          # Brain audit on every commit; refuses a push to main
.\.venv\Scripts\python -m pytest -q          # Postgres tests: see brain/policies/TDD.md
git config argus.developer <your-github-handle>
python brain/tools/brain.py status
```

## Layout

| Path | What |
|---|---|
| `argus/` | the agent (domain, ports, adapters, orchestration, tooling, policy) |
| `services/target/` | the per-host read gateway, probes and exporter |
| `config/` | inventory, policy, signals, runbook pin (`runbooks.lock`) — canonical data |
| `deploy/` | compose files, migrations, lab workloads |
| `ops/` | operational scripts (non-interference check, migrations, checks) |
| `tests/` | offline, Postgres and `brain.py` tests |
| `brain/` | the shared project Brain: state, plan, rules, guides, journal |

Runbooks live in the separate repository `agenticteam03/runbooks`, at the commit pinned in `config/runbooks.lock`.
