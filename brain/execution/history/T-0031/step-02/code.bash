# T-0031 step 02 — the deployment write-gate check on vm-095 (2026-10-10, conantkd, session 4ef1e84354ce, vm-095 lease).
# Run by the agent over SSH. The branch sources were copied to /tmp/argus-t0031 with git archive (the deployed
# checkout, main ebbe9c9, is not changed). READ-ONLY: docker ps / exec (a python reading files) / inspect.
# ROLLBACK: sudo rm -rf /tmp/argus-t0031.  EXPECT: WRITE GATE CLOSED; NO INTERFERENCE.
sudo bash /opt/argus-v18/app/ops/nonint-check.sh before | tail -1
sudo bash /tmp/argus-t0031/ops/write-gate-check.sh; echo "exit=$?"
sudo docker exec argus-v18-agent sh -c 'cat /app/config/policy.yaml 2>/dev/null || cat config/policy.yaml' | grep -A1 '^write_gate:'
curl -s http://127.0.0.1:18000/healthz; echo
sudo rm -rf /tmp/argus-t0031
sudo bash /opt/argus-v18/app/ops/nonint-check.sh after | tail -1
