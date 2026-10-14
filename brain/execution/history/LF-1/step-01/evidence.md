# LF-1 step 01 — capacity baseline and architecture discovery

Status: executed and verified on vm-095. Session: 850fe4d2aaf2, conantkd.

- VM deployed commit: 8ee48c4, task/T-0016-playwright; checkout clean. The public-UI record PR #146 explains why it is newer than main. No agent deployment was performed here.
- aarch64, one online CPU, 5900 MiB RAM, 4408 MiB available, no swap.
- Disk: 73846 MiB available on the filesystem containing /opt/argus-v18.
- Core API/worker/scheduler/Postgres: running, restarts 0, OOM false.
- LAB BASELINE OK; NO INTERFERENCE.
- Initial /health probe returned 404: corrected to the declared /healthz endpoint before any capacity mutation. All ten corrected requests returned 200; latency 2.18–6.33 ms.
- The six candidate images all advertise arm64: Langfuse web/worker :4, ClickHouse :25.12, Chainguard MinIO, Redis :7, Postgres :17. Tags will be resolved to immutable digests for the actual trial.

The archived command is the corrected health and manifest discovery. The preceding read-only resource probe also ran deploy.sh status, uname, getconf, free, df, vmstat, Docker state/stats and nonint-check.sh after. Output is sanitized; no addresses or secrets.

Next: a bounded, synthetic-data-only, isolated six-container trial. No public listeners, no Argus database or agent changes. Dedicated containers and volumes only; clean them up at the end.