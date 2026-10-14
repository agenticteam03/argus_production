#!/usr/bin/env bash
# STEP LF-1.05 — Temporary Langfuse trial, user-authorized shared lease [VM vm-095]
# MUTATES: six dedicated containers and five NEW synthetic-only volumes; image downloads.
# No Argus deployment, credentials, database or public listener is changed.
# Expected: ready, 60 synthetic traces retrieved, core unchanged, no trial volumes remain, NO INTERFERENCE.
# Undo: sudo docker compose --project-name argus-lab-lf1 --env-file /opt/argus-v18/lab/lf-1-dc432c3ff537/trial.env -f /opt/argus-v18/lab/lf-1-dc432c3ff537/compose.yaml down --volumes --remove-orphans
set -euo pipefail
grep -q 'holder=conantkd session=dc432c3ff537' /opt/argus-v18/SESSION
sudo -n python3 /opt/argus-v18/lab/lf-1-dc432c3ff537/trial.py </dev/null
# Optional READ-ONLY progress checks during the run:
# sudo docker ps -a --filter name=argus-lab-lf1 --format '{{.Names}} {{.State}}'
# free -m
# curl --max-time 5 -s -o /dev/null -w 'healthz=%{http_code} latency_s=%{time_total}\n' http://127.0.0.1:18000/healthz