# =====================================================================================
# Argus — commands for the current task (brain/policies/CODE_BASH.md)
#
# Every block says WHERE to run it:
#   [LAPTOP · PowerShell]   a PowerShell window on your laptop
#   [VM vm-095 · bash]      ssh argus-vm095
#   [VM vm-166 · bash]      ssh argus-vm166
# Paste what the terminal printed into brain/execution/current/output.bash (gitignored, never committed)
# and tell the agent "output.bash updated".
# =====================================================================================
# T-0047 H5 step 2 B, step 02: the model batch for #274 BEFORE it merges (conantkd's review). Same deployed image
# (afb72e8) for both runs; the code under /app/argus is a read-only bind of a git archive: "before" = main, "after" =
# the PR branch (they differ only in argus/detectors/classes.py, the anomaly tag). The 12 cases of the two classes,
# --strategy model_loop, 5 trials each, both runs in parallel. No image build, no deploy, no ops/ change.
# MUTATES (vm-095): the new folder /opt/argus-v18/eval-h5b/ (archives and the 12 cases), two one-off containers
#   argus-v18-eval-h5b-before/-after (removed by H5B.4), two results files eval-results/h5b-before|after.jsonl.
# UNDO: sudo docker rm -f argus-v18-eval-h5b-before argus-v18-eval-h5b-after; sudo rm -rf /opt/argus-v18/eval-h5b
#   /opt/argus-v18/eval-results/h5b-before.jsonl /opt/argus-v18/eval-results/h5b-after.jsonl. Nothing else changes.


# ---------------------------------------------------------------------------------------------------------
# H5B.2 [LAPTOP · PowerShell]  claim the vm-095 lease for the batch and extend it to 120 minutes
# Expected: 'Lease CLAIMED by juanbetancurm on vm-095' and its SESSION line (its session id goes into H5B.3);
#   'Lease renewed'; VERDICT: H5B.2 PASS (2 of 2).
# ---------------------------------------------------------------------------------------------------------
Set-Location C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\w-h5s2
git rev-parse --show-toplevel
$ok = 0
..\argus_production\.venv\Scripts\python.exe brain/tools/brain.py start --task T-0047-H5B --vm vm-095
if ($LASTEXITCODE -eq 0) { $ok++ }
..\argus_production\.venv\Scripts\python.exe brain/tools/brain.py renew --vm vm-095 --minutes 120
if ($LASTEXITCODE -eq 0) { $ok++ }
if ($ok -eq 2) { 'VERDICT: H5B.2 PASS (2 of 2)' } else { "VERDICT: H5B.2 FAIL ($ok of 2)" }

# ---------------------------------------------------------------------------------------------------------
# H5B.3 [VM vm-095 · bash]  (ssh argus-vm095) marker, before; main's and the branch's code; the 12 cases; both runs
# Replace <session> with the session id H5B.2 printed. Everything after the marker runs only if SESSION is ours.
# Expected: SESSION OK; ref=afb72e8 and LAB BASELINE OK; a before snapshot; 'branch sha=b3cc16c...';
#   'code diff:' naming ONLY argus/detectors/classes.py; 'cases: 12'; 'per-target series: 6';
#   'before offers anomaly to: []' and 'after offers anomaly to: ['container_restart_loop', 'dependency_unavailable']'
#   (both from /app/argus); two container ids; after 90 s both 'Up' and 'errors: 0 0'.
#   A different diff or offer list: STOP, nothing has run yet (the runs start only after both checks).
# ---------------------------------------------------------------------------------------------------------
echo 'holder=juanbetancurm session=<session>' | sudo tee /opt/argus-v18/SESSION >/dev/null
if grep -q 'holder=juanbetancurm session=' /opt/argus-v18/SESSION; then
  echo "SESSION OK"
  sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^(commit|ref)=|LAB BASELINE'
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
  export GIT_SSH_COMMAND="ssh -i /opt/argus-v18/secrets/deploy/id_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=/opt/argus-v18/secrets/deploy/known_hosts -o StrictHostKeyChecking=yes -o BatchMode=yes"
  G="git -C /opt/argus-v18/app -c safe.directory=/opt/argus-v18/app"
  sudo --preserve-env=GIT_SSH_COMMAND $G fetch --quiet origin main </dev/null
  MAIN=$(sudo $G rev-parse FETCH_HEAD); echo "main sha=$MAIN"
  sudo --preserve-env=GIT_SSH_COMMAND $G fetch --quiet origin task/T-0047-h5s2b-anomaly-offer </dev/null
  BR=$(sudo $G rev-parse FETCH_HEAD); echo "branch sha=$BR"
  D=/opt/argus-v18/eval-h5b
  sudo rm -rf $D && sudo mkdir -p $D/before $D/after $D/cases
  sudo $G archive "$MAIN" argus tests/eval/cases | sudo tar -x -C $D/before
  sudo $G archive "$BR" argus | sudo tar -x -C $D/after
  for f in $D/before/tests/eval/cases/dep-*.yaml $D/before/tests/eval/cases/ambiguous-dep-all-running.yaml $D/before/tests/eval/cases/restart-*.yaml; do sudo cp "$f" $D/cases/; done
  DIFF=$(sudo diff -rq $D/before/argus $D/after/argus | sed "s#$D/##g")
  echo "code diff: $DIFF"
  echo "cases: $(ls $D/cases | wc -l)"
  echo "per-target series: $(grep -l range_by_target $D/cases/*.yaml | wc -l)"
  H=/opt/argus-v18
  O="--user 10010:10010 --read-only --tmpfs /tmp:size=64m --cap-drop ALL --security-opt no-new-privileges --pids-limit 64 --memory 512m --mount type=bind,source=$H/secrets/agent/openai_api_key,target=/run/eval-secrets/openai_api_key,readonly --mount type=bind,source=$H/app/config,target=/app/config,readonly -e ARGUS_SECRETS_DIR=/run/eval-secrets -e ARGUS_DB_BACKEND=sqlite -e ARGUS_TOOL_CATALOGUE=direct -e ARGUS_LLM_MODEL=gpt-5.6-luna"
  echo "--- the deployed ops/eval-run.sh docker run:"
  sed -n '/"$DOCKER" run/,/--out/p' $H/app/ops/eval-run.sh
  echo "--- this block's (per V): docker run -d --name argus-v18-eval-h5b-V $O --mount <D/V/argus>:/app/argus:ro --mount $D:/eval:ro --mount $H/eval-results:/out argus-v18-agent:1 python -m argus.evaluation --cases /eval/cases --model configured --workdir /tmp/eval --out /out/h5b-V.jsonl --trials 5 --strategy model_loop"
  for V in before after; do
    echo "$V offers anomaly to: $(sudo docker run --rm $O --mount type=bind,source=$D/$V/argus,target=/app/argus,readonly argus-v18-agent:1 python -c 'import argus; from argus.detectors.classes import CLASSES; assert argus.__file__.startswith("/app/argus"); print(sorted(c.name for c in CLASSES if "anomaly" in c.tool_tags))' </dev/null)"
  done
  case "$BR:$DIFF" in
    b3cc16c*":Files before/argus/detectors/classes.py and after/argus/detectors/classes.py differ")
      for V in before after; do
        sudo rm -f $H/eval-results/h5b-$V.jsonl
        sudo docker run -d --name argus-v18-eval-h5b-$V $O --mount type=bind,source=$D/$V/argus,target=/app/argus,readonly --mount type=bind,source=$D,target=/eval,readonly --mount type=bind,source=$H/eval-results,target=/out argus-v18-agent:1 python -m argus.evaluation --cases /eval/cases --model configured --workdir /tmp/eval --out /out/h5b-$V.jsonl --trials 5 --strategy model_loop </dev/null | cut -c1-12
      done
      sleep 90
      sudo docker ps --filter 'name=argus-v18-eval-h5b-' --format '{{.Names}} {{.Status}}'
      echo "errors: $(sudo docker logs argus-v18-eval-h5b-before 2>&1 </dev/null | grep -cE 'Traceback|Error') $(sudo docker logs argus-v18-eval-h5b-after 2>&1 </dev/null | grep -cE 'Traceback|Error')"
      ;;
    *) echo "H5B.3 STOP: branch or code diff not as expected; nothing started" ;;
  esac
else
  echo "NOT YOUR SESSION - stop here"
fi

# ---------------------------------------------------------------------------------------------------------
# H5B.4 [VM vm-095 · bash]  (ssh argus-vm095) about 30 min after H5B.3: both summaries, per class, after
# Expected: both containers 'Exited'; each log's last lines (summary, per-class table, 'hard: 0 0 0 0'); for
#   h5b-before.jsonl and h5b-after.jsonl, 'dep' and 'restart' lines: trials of 6, mean, failing cases, the runs that
#   read analysis.anomaly_summary (before: 0), hard 0; the two containers removed; NO INTERFERENCE.
#   If a container still says 'Up', it is still running: wait and run H5B.4 again (nothing is removed then).
# ---------------------------------------------------------------------------------------------------------
if grep -q 'holder=juanbetancurm session=' /opt/argus-v18/SESSION; then
  echo "SESSION OK"
  sudo docker ps -a --filter 'name=argus-v18-eval-h5b-' --format '{{.Names}} {{.Status}}'
  for V in before after; do
    echo "--- $V"
    sudo docker logs argus-v18-eval-h5b-$V 2>&1 </dev/null | tail -6
    sudo cat /opt/argus-v18/eval-results/h5b-$V.jsonl | python3 -c 'import json, sys
rows = [json.loads(x) for x in sys.stdin if x.strip()]
for p in ("dep-", "restart-"):
    r = [x for x in rows if x["case"].startswith(p) or x["case"] == "ambiguous-dep-all-running" and p == "dep-"]
    t = {}
    for x in r:
        t.setdefault(x["trial"], []).append(x["verdict"] == "PASS")
    per = [sum(v) for k, v in sorted(t.items())]
    bad = {}
    for x in r:
        if x["verdict"] != "PASS":
            bad[x["case"]] = bad.get(x["case"], 0) + 1
    calls = sum(any(e[0] == "analysis.anomaly_summary" for e in x.get("reads") or []) for x in r)
    hard = sum(sum((x.get("hard") or {}).values()) for x in r)
    print(p.rstrip("-"), "trials", per, "of", [len(v) for k, v in sorted(t.items())],
          "mean", round(sum(per) / max(1, sum(len(v) for v in t.values())), 2), "failing", bad, "anomaly runs", calls, "hard", hard)'
  done
  if [ -z "$(sudo docker ps -q --filter 'name=argus-v18-eval-h5b-' </dev/null)" ]; then
    sudo docker rm argus-v18-eval-h5b-before argus-v18-eval-h5b-after </dev/null
  fi
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
else
  echo "NOT YOUR SESSION - stop here"
fi

# ---------------------------------------------------------------------------------------------------------
# H5B.5 [LAPTOP · PowerShell]  release the vm-095 lease (run it also if a step above failed)
# Expected: 'Lease released on vm-095.'; VERDICT: H5B.5 PASS (1 of 1).
# ---------------------------------------------------------------------------------------------------------
Set-Location C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\w-h5s2
git rev-parse --show-toplevel
$ok = 0
..\argus_production\.venv\Scripts\python.exe brain/tools/brain.py release --vm vm-095
if ($LASTEXITCODE -eq 0) { $ok++ }
if ($ok -eq 1) { 'VERDICT: H5B.5 PASS (1 of 1)' } else { "VERDICT: H5B.5 FAIL ($ok of 1)" }
