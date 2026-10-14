#!/usr/bin/env bash
# STEP LF-1.02 — Correct health endpoint and image architecture discovery [VM vm-095]
# READ-ONLY: inspect manifests and local health; no containers are started.
# Expected: healthz=200 and arm64 manifests for the six candidate images.
set -euo pipefail
grep -q 'holder=conantkd session=850fe4d2aaf2' /opt/argus-v18/SESSION
for i in $(seq 1 10); do
 curl --max-time 5 -s -o /dev/null -w 'argus_healthz=%{http_code} latency_s=%{time_total}\n' http://127.0.0.1:18000/healthz </dev/null
 sleep 1
done
for image in docker.langfuse.com/langfuse/langfuse:4 docker.langfuse.com/langfuse/langfuse-worker:4 clickhouse/clickhouse-server:25.12 cgr.dev/chainguard/minio:latest redis:7 postgres:17; do
 printf 'IMAGE %s\n' "$image"
 sudo -n docker manifest inspect "$image" </dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print("platforms:", ",".join(sorted({m.get("platform",{}).get("architecture","unknown") for m in d.get("manifests",[])})))'
done
sudo -n ss -tlnH | awk '{print $4}' | grep -q ':18020$' && { echo 'STOP: port 18020 occupied'; exit 1; } || true
echo 'LF-1 DISCOVERY COMPLETE'