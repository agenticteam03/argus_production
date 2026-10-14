#!/usr/bin/env bash
# STEP LF-1.03 — Bounded Langfuse trial [VM vm-095, ~10–20 min]
# MUTATES: six argus-lab-lf1 containers and five NEW synthetic-only volumes; pulls images.
# Expected: Langfuse ready; 60 traces retrieved; core_unchanged true; NO INTERFERENCE; no trial volumes remain.
# Undo: sudo docker compose --project-name argus-lab-lf1 --env-file /opt/argus-v18/lab/lf-1-850fe4d2aaf2/trial.env -f /opt/argus-v18/lab/lf-1-850fe4d2aaf2/compose.yaml down --volumes --remove-orphans
# Guardrails and finally-cleanup are in trial.py; an independent 25-minute timer also cleans a stalled trial.
# Uploaded files: ops/experiments/langfuse-capacity/{compose.yaml,trial.py}, without secrets.
set -euo pipefail
grep -q 'holder=conantkd session=850fe4d2aaf2' /opt/argus-v18/SESSION
sudo -n python3 /opt/argus-v18/lab/lf-1-850fe4d2aaf2/trial.py </dev/null