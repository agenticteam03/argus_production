# T-0049 R1 step 01: the commands as the developer ran them on 2026-10-22 (vm-095, lease session a428fd4bf3cf).
# Prepared by S2, copied to the coordinator's run file by S1 (headers normalised; R1.2 got the SESSION marker as its
# first line; R1.3 builds from the reviewed base a4ee19b because main had moved on). R1.2 first ran on vm-166 by
# mistake (wrong VM; only the marker line wrote anything) and its check pattern was wrong on vm-095 (deploy status
# prints commit=<full sha> and ref=<sha>, not ref=main): the evidence explains both.

# ---------------------------------------------------------------------------------------------------------
# R1.1 [LAPTOP · PowerShell]  (w-r1-lease) claim the vm-095 lease for S2's R1 batch and renew it to 120 minutes
# MUTATES: the lease only. Undo: brain.py release --vm vm-095 (R1.6).
# Expected: 'Lease CLAIMED by juanbetancurm on vm-095' and its SESSION line; 'Lease renewed';
#   VERDICT: R1.1 PASS (4 of 4). Run it ONCE. S1 then puts the SESSION marker in the next VM block.
# ---------------------------------------------------------------------------------------------------------
Set-Location C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\w-r1-lease
$top = git rev-parse --show-toplevel
$ok = 0
if (($top -replace '/', '\') -eq 'C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\w-r1-lease') { $ok++ }
..\argus_production\.venv\Scripts\python.exe brain/tools/brain.py --as juanbetancurm status
if ($LASTEXITCODE -eq 0) { $ok++ }
..\argus_production\.venv\Scripts\python.exe brain/tools/brain.py --as juanbetancurm start --task T-0049-R1 --vm vm-095
if ($LASTEXITCODE -eq 0) { $ok++ }
..\argus_production\.venv\Scripts\python.exe brain/tools/brain.py --as juanbetancurm renew --vm vm-095 --minutes 120
if ($LASTEXITCODE -eq 0) { $ok++ }
if ($ok -eq 4) { 'VERDICT: R1.1 PASS (4 of 4)' } else { "VERDICT: R1.1 FAIL ($ok of 4)" }


# ---------------------------------------------------------------------------------------------------------
# R1.2 [VM vm-095 · bash] (ssh argus-vm095) Read-only state probe, after the lease marker
# READ-ONLY after its first line, the SESSION marker of lease session a428fd4bf3cf (R1.1).
# Expected: SESSION OK; commit=77c4524, ref=main, LAB BASELINE OK; health HTTP 200;
#   image id recorded; no old R1 eval container; NO INTERFERENCE; VERDICT: R1.2 PASS.
# ---------------------------------------------------------------------------------------------------------
echo 'holder=juanbetancurm session=a428fd4bf3cf' | sudo tee /opt/argus-v18/SESSION >/dev/null
if grep -q '^holder=juanbetancurm ' /opt/argus-v18/SESSION; then
  echo "SESSION OK"
  STATE=$(sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null)
  printf '%s\n' "$STATE" | grep -E '^(commit|ref)=|LAB BASELINE'
  HEALTH=$(curl -sS -o /dev/null -w '%{http_code}' http://localhost:18000/healthz </dev/null)
  echo "health HTTP $HEALTH"
  sudo docker image inspect -f '{{.Id}}' argus-v18-agent:1
  OLD=$(sudo docker ps -aq --filter 'name=argus-v18-eval-r1-')
  if [ -z "$OLD" ]; then echo "no prior R1 eval containers"; else echo "STOP: prior R1 eval container exists"; fi
  sudo docker ps -a --filter 'name=argus-v18-' --format '{{.Names}} {{.Status}}'
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
  if printf '%s\n' "$STATE" | grep -q '^commit=77c4524$' && printf '%s\n' "$STATE" | grep -q '^ref=main$' && printf '%s\n' "$STATE" | grep -q 'LAB BASELINE OK' && [ "$HEALTH" = 200 ] && [ -z "$OLD" ]; then
    echo "VERDICT: R1.2 PASS"
  else
    echo "VERDICT: R1.2 STOP: verify deployment, health, and existing containers before continuing"
  fi
else
  echo "VERDICT: R1.2 STOP: not juanbetancurm's lease"
fi


# ---------------------------------------------------------------------------------------------------------
# R1.3 [LAPTOP · PowerShell] (w-r1) Build paired git archives and upload under the active lease
# MUTATES: creates one unique local bundle and copies three tar archives to vm-095 /tmp.
# Base: the reviewed a4ee19b (main has #295 since: postgres_store.py only, not used by the SQLite eval).
# Expected: base on main; both trees differ only in classes.py; 12 case files; SSH guard and both
#   non-interference checks pass; all three SCPs succeed; VERDICT: R1.3 PASS (19 of 19).
# ---------------------------------------------------------------------------------------------------------
Set-Location C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\w-r1
$top = git rev-parse --show-toplevel
$ok = 0
if (($top -replace '/', '\') -eq 'C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\w-r1') { $ok++ }
git fetch --quiet origin main
$fetchOK = $LASTEXITCODE -eq 0
if ($fetchOK) { $ok++ }
git merge-base --is-ancestor a4ee19b6dc2db78ea9feb7add5e5cfc7ba4fae52 origin/main
$baseOK = $LASTEXITCODE -eq 0
if ($baseOK) { $ok++ }
if ($fetchOK -and $baseOK) {
  $stamp = '20261023T001252Z'
  $bundle = Join-Path $env:TEMP ('argus-r1-' + $stamp)
  $commonIndex = Join-Path $bundle 'index-common'
  $afterIndex = Join-Path $bundle 'index-after'
  $beforeTar = Join-Path $bundle ('r1-before-' + $stamp + '-argus.tar')
  $afterTar = Join-Path $bundle ('r1-after-' + $stamp + '-argus.tar')
  $casesTar = Join-Path $bundle ('r1-cases-' + $stamp + '.tar')
  if (Test-Path -LiteralPath $bundle) {
    'STOP: local stamped bundle exists; no files overwritten'
  } else {
    New-Item -ItemType Directory -Path $bundle | Out-Null
    if (Test-Path -LiteralPath $bundle) { $ok++ }
    $env:GIT_INDEX_FILE = $commonIndex
  git read-tree a4ee19b6dc2db78ea9feb7add5e5cfc7ba4fae52
  if ($LASTEXITCODE -eq 0) { $ok++ }
  git add -- argus/evaluation/replay.py argus/evaluation/regrade.py
  if ($LASTEXITCODE -eq 0) { $ok++ }
  $commonTree = git write-tree
  if ($LASTEXITCODE -eq 0) { $ok++ }
  $env:GIT_INDEX_FILE = $afterIndex
  git read-tree $commonTree
  if ($LASTEXITCODE -eq 0) { $ok++ }
  git add -- argus/detectors/classes.py
  if ($LASTEXITCODE -eq 0) { $ok++ }
  $afterTree = git write-tree
  if ($LASTEXITCODE -eq 0) { $ok++ }
  Remove-Item Env:GIT_INDEX_FILE -ErrorAction SilentlyContinue
  $treeDiff = git diff-tree --no-commit-id --name-only -r $commonTree $afterTree
  if ($LASTEXITCODE -eq 0 -and $treeDiff -eq 'argus/detectors/classes.py') { $ok++ }
  $caseFiles = @(
    'tests/eval/cases/health-api-vm095-01.yaml',
    'tests/eval/cases/health-api-vm095-01-longlog.yaml',
    'tests/eval/cases/health-api-vm095-02.yaml',
    'tests/eval/cases/health-api-vm095-02-longlog.yaml',
    'tests/eval/cases/health-api-vm166-01.yaml',
    'tests/eval/cases/health-api-vm166-01-longlog.yaml',
    'tests/eval/cases/health-api-vm166-02.yaml',
    'tests/eval/cases/health-api-vm166-02-longlog.yaml',
    'tests/eval/cases/health-db-vm166-01.yaml',
    'tests/eval/cases/health-db-vm166-01-longlog.yaml',
    'tests/eval/cases/ambiguous-health-no-cause.yaml',
    'tests/eval/cases/ambiguous-health-no-cause-longlog.yaml'
  )
  git archive --format=tar --output $beforeTar $commonTree argus
  if ($LASTEXITCODE -eq 0) { $ok++ }
  git archive --format=tar --output $afterTar $afterTree argus
  if ($LASTEXITCODE -eq 0) { $ok++ }
  git archive --format=tar --output $casesTar a4ee19b6dc2db78ea9feb7add5e5cfc7ba4fae52 @caseFiles
  if ($LASTEXITCODE -eq 0 -and $caseFiles.Count -eq 12) { $ok++ }
  if ($treeDiff -eq 'argus/detectors/classes.py' -and (Test-Path -LiteralPath $beforeTar) -and (Test-Path -LiteralPath $afterTar) -and (Test-Path -LiteralPath $casesTar) -and $caseFiles.Count -eq 12) {
  $remoteBefore = 'argus-vm095:/tmp/r1-before-' + $stamp + '-argus.tar'
  $remoteAfter = 'argus-vm095:/tmp/r1-after-' + $stamp + '-argus.tar'
  $remoteCases = 'argus-vm095:/tmp/r1-cases-' + $stamp + '.tar'
  $remoteGuard = 'grep -q ''^holder=juanbetancurm '' /opt/argus-v18/SESSION && test ! -e /tmp/r1-before-' + $stamp + '-argus.tar && test ! -e /tmp/r1-after-' + $stamp + '-argus.tar && test ! -e /tmp/r1-cases-' + $stamp + '.tar && sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null'
  ssh argus-vm095 $remoteGuard
  if ($LASTEXITCODE -eq 0) {
    $ok++
    scp $beforeTar $remoteBefore
    if ($LASTEXITCODE -eq 0) { $ok++ }
    scp $afterTar $remoteAfter
    if ($LASTEXITCODE -eq 0) { $ok++ }
    scp $casesTar $remoteCases
    if ($LASTEXITCODE -eq 0) { $ok++ }
    $remoteAfterCheck = 'grep -q ''^holder=juanbetancurm '' /opt/argus-v18/SESSION && test -s /tmp/r1-before-' + $stamp + '-argus.tar && test -s /tmp/r1-after-' + $stamp + '-argus.tar && test -s /tmp/r1-cases-' + $stamp + '.tar && sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null'
    ssh argus-vm095 $remoteAfterCheck
    if ($LASTEXITCODE -eq 0) { $ok++ }
  } else {
    'STOP: lease marker or non-interference check failed; no archive transferred'
  }
  Get-FileHash $beforeTar -Algorithm SHA256
  Get-FileHash $afterTar -Algorithm SHA256
  Get-FileHash $casesTar -Algorithm SHA256
  "common tree=$commonTree; after tree=$afterTree; only tree diff=$treeDiff; cases=$($caseFiles.Count)"
  } else {
    'STOP: archive verification failed; no transfers attempted'
  }
  }
} else {
  'STOP: the reviewed base is not on origin/main or fetch failed; no archives or transfers attempted'
}
if ($ok -eq 19) { 'VERDICT: R1.3 PASS (19 of 19)' } else { "VERDICT: R1.3 FAIL ($ok of 19)" }


# ---------------------------------------------------------------------------------------------------------
# R1.4 [VM vm-095 · bash] (ssh argus-vm095) Guard, verify exact archive diff, then start both arms
# MUTATES: extracts unique archives and creates two named evaluation containers/results. No rm or --rm here.
# Expected: SESSION OK; no existing R1 eval container, result or stamped directory; 12 cases; exact one-line
#   classes.py change; image id matches R1.2; both runs started; non-interference unchanged. Otherwise STOP before runs.
# ---------------------------------------------------------------------------------------------------------
if grep -q '^holder=juanbetancurm ' /opt/argus-v18/SESSION; then
  echo "SESSION OK"
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
  STAMP=20261023T001252Z
  H=/opt/argus-v18
  D=$H/eval-r1-$STAMP
  BEFORE=$H/eval-results/r1-before-$STAMP.jsonl
  AFTER=$H/eval-results/r1-after-$STAMP.jsonl
  EXISTING=$(sudo docker ps -aq --filter 'name=argus-v18-eval-r1-')
  if [ -z "$EXISTING" ] && [ ! -e "$D" ] && [ ! -e "$BEFORE" ] && [ ! -e "$AFTER" ] && sudo test -s /tmp/r1-before-$STAMP-argus.tar && sudo test -s /tmp/r1-after-$STAMP-argus.tar && sudo test -s /tmp/r1-cases-$STAMP.tar; then
    sudo sha256sum /tmp/r1-before-$STAMP-argus.tar /tmp/r1-after-$STAMP-argus.tar /tmp/r1-cases-$STAMP.tar
    sudo mkdir -p "$D/before" "$D/after" "$D/cases"
    sudo tar -xf /tmp/r1-before-$STAMP-argus.tar -C "$D/before"
    sudo tar -xf /tmp/r1-after-$STAMP-argus.tar -C "$D/after"
    sudo tar -xf /tmp/r1-cases-$STAMP.tar -C "$D/cases" --strip-components=3
    DIFF=$(sudo diff -rq "$D/before/argus" "$D/after/argus" || true)
    EXPECTED_DIFF="Files $D/before/argus/detectors/classes.py and $D/after/argus/detectors/classes.py differ"
    PATCH=$(sudo diff -u "$D/before/argus/detectors/classes.py" "$D/after/argus/detectors/classes.py" | grep -E '^[+-][^+-]')
    EXPECTED_PATCH=$(printf '%s\n' '-                      tool_tags={"availability", "logs", "dependency", "network", "container", "knowledge"},' '+                      tool_tags={"availability", "logs", "detailed_logs", "dependency", "network", "container", "knowledge"},')
    CASES=$(find "$D/cases" -maxdepth 1 -type f -name '*.yaml' | wc -l)
    IMAGE=$(sudo docker image inspect -f '{{.Id}}' argus-v18-agent:1)
    echo "code diff: $DIFF"
    echo "patch: $PATCH"
    echo "cases: $CASES"
    echo "image id: $IMAGE"
    if [ "$DIFF" = "$EXPECTED_DIFF" ] && [ "$PATCH" = "$EXPECTED_PATCH" ] && [ "$CASES" -eq 12 ] && [ -n "$IMAGE" ]; then
      O="--user 10010:10010 --read-only --tmpfs /tmp:size=64m --cap-drop ALL --security-opt no-new-privileges --pids-limit 64 --memory 512m --mount type=bind,source=$H/secrets/agent/openai_api_key,target=/run/eval-secrets/openai_api_key,readonly --mount type=bind,source=$H/app/config,target=/app/config,readonly -e ARGUS_SECRETS_DIR=/run/eval-secrets -e ARGUS_DB_BACKEND=sqlite -e ARGUS_TOOL_CATALOGUE=direct -e ARGUS_LLM_MODEL=gpt-5.6-luna"
      IDB=$(sudo docker run -d --name argus-v18-eval-r1-before-$STAMP $O --mount type=bind,source=$D/before/argus,target=/app/argus,readonly --mount type=bind,source=$D/cases,target=/eval/cases,readonly --mount type=bind,source=$H/eval-results,target=/out argus-v18-agent:1 python -m argus.evaluation --cases /eval/cases --model configured --workdir /tmp/eval --out /out/r1-before-$STAMP.jsonl --trials 5 --strategy model_loop </dev/null)
      IDA=$(sudo docker run -d --name argus-v18-eval-r1-after-$STAMP $O --mount type=bind,source=$D/after/argus,target=/app/argus,readonly --mount type=bind,source=$D/cases,target=/eval/cases,readonly --mount type=bind,source=$H/eval-results,target=/out argus-v18-agent:1 python -m argus.evaluation --cases /eval/cases --model configured --workdir /tmp/eval --out /out/r1-after-$STAMP.jsonl --trials 5 --strategy model_loop </dev/null)
      echo "containers: $IDB $IDA"
      if [ -n "$IDB" ] && [ -n "$IDA" ]; then
        sleep 90
        sudo docker ps -a --filter 'name=argus-v18-eval-r1-' --format '{{.Names}} {{.Status}}'
        echo "errors: $(sudo docker logs argus-v18-eval-r1-before-$STAMP 2>&1 </dev/null | grep -cE 'Traceback|Error') $(sudo docker logs argus-v18-eval-r1-after-$STAMP 2>&1 </dev/null | grep -cE 'Traceback|Error')"
        sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
        echo "VERDICT: R1.4 RUNS STARTED; wait for R1.5 before evaluating"
      else
        echo "VERDICT: R1.4 STOP: one or both containers failed to start; preserve all artifacts"
        sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
      fi
    else
      echo "VERDICT: R1.4 STOP: archive diff or case count differs; no model run started"
      sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
    fi
  else
    echo "VERDICT: R1.4 STOP: prior R1 container, artifact, or stamped path exists; nothing overwritten"
    sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
  fi
else
  echo "VERDICT: R1.4 STOP: not juanbetancurm's lease"
fi


# ---------------------------------------------------------------------------------------------------------
# R1.5 [VM vm-095 · bash] (ssh argus-vm095) Read summaries and preserve results; remove exited containers
# Safe to repeat: until both arms finish it only prints progress and WAIT.
# READS JSONL; removes only the two named containers after both have exited and each has 60 valid result rows.
# Expected: per-arm class and ambiguous accuracy/trial counts, all hard counts, calls, token cost, reads, p50;
#   both containers removed only when complete, result JSONL retained, NO INTERFERENCE.
# ---------------------------------------------------------------------------------------------------------
if grep -q '^holder=juanbetancurm ' /opt/argus-v18/SESSION; then
  echo "SESSION OK"
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
  sudo docker ps -a --filter 'name=argus-v18-eval-r1-' --format '{{.Names}} {{.Status}}'
  ALL=1
  for V in before after; do
    NAME=argus-v18-eval-r1-$V-20261023T001252Z
    FILE=/opt/argus-v18/eval-results/r1-$V-20261023T001252Z.jsonl
    STATUS=$(sudo docker inspect -f '{{.State.Status}} exit={{.State.ExitCode}}' "$NAME" 2>/dev/null)
    echo "--- $V: $STATUS"
    if [ "$STATUS" != "exited exit=0" ] && [ "$STATUS" != "exited exit=1" ]; then ALL=0; fi
    sudo docker logs "$NAME" 2>&1 </dev/null | tail -5
    if [ -s "$FILE" ]; then
      sudo cat "$FILE" | python3 -c 'import json,sys,statistics
from collections import Counter
rows=[json.loads(x) for x in sys.stdin if x.strip()]
if len(rows)!=60: print("rows",len(rows),"expected 60"); sys.exit(2)
classes=[r for r in rows if r.get("category")=="class"]
ambiguous=[r for r in rows if r.get("category")=="ambiguous"]
if len(classes)!=50 or len(ambiguous)!=10: print("category counts",len(classes),len(ambiguous),"expected 50 and 10"); sys.exit(2)
good=lambda rs: sum(r.get("verdict")=="PASS" for r in rs)
trials=sorted({r.get("trial") for r in rows})
print("rows",len(rows),"class",good(classes),"/",len(classes),"accuracy",round(good(classes)/len(classes),3),"class trial passes",[str(t)+":"+str(good([r for r in classes if r.get("trial")==t]))+"/10" for t in trials])
print("ambiguous safe passes",good(ambiguous),"/",len(ambiguous),"trial passes",[str(t)+":"+str(good([r for r in ambiguous if r.get("trial")==t]))+"/2" for t in trials])
hard=Counter()
for r in rows: hard.update(r.get("hard") or {})
inp=sum(int(r.get("input_tokens") or 0) for r in rows)
out=sum(int(r.get("output_tokens") or 0) for r in rows)
reads=[item for r in rows for item in (r.get("reads") or [])]
detailed=[item for item in reads if item and item[0]=="container.detailed_logs"]
detailed_runs=sum(any(item and item[0]=="container.detailed_logs" for item in (r.get("reads") or [])) for r in rows)
lat=statistics.median([int(r.get("duration_ms") or 0) for r in rows])
failed=Counter(r.get("case") for r in rows if r.get("verdict")!="PASS")
print("model calls",sum(int(r.get("model_calls") or 0) for r in rows),"input tokens",inp,"output tokens",out,"total token query-cost units",inp+out)
print("all reads",len(reads),"detailed_logs runs",detailed_runs,"detailed_logs reads",len(detailed),"p50 latency ms",lat)
print("hard counts",dict(sorted(hard.items())),"failing cases",dict(sorted(failed.items())))'
      PYOK=$?
      if [ "$PYOK" -ne 0 ]; then ALL=0; fi
    else
      echo "missing result file: $FILE"
      ALL=0
    fi
  done
  if [ "$ALL" -eq 1 ]; then
    sudo docker rm argus-v18-eval-r1-before-20261023T001252Z argus-v18-eval-r1-after-20261023T001252Z </dev/null
    echo "containers removed; stamped JSONL files retained"
  else
    echo "containers retained: still running or incomplete; rerun R1.5 after completion"
  fi
  NI=$(sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null)
  printf '%s\n' "$NI" | tail -1
  if [ "$ALL" -eq 1 ] && printf '%s\n' "$NI" | grep -q 'NO INTERFERENCE'; then
    echo "VERDICT: R1.5 PASS"
  else
    echo "VERDICT: R1.5 WAIT: verify NO INTERFERENCE or rerun after both arms complete"
  fi
else
  echo "VERDICT: R1.5 STOP: not juanbetancurm's lease"
fi


# ---------------------------------------------------------------------------------------------------------
# R1.6 [LAPTOP · PowerShell] (w-r1-lease) Release the vm-095 lease after the batch
# Expected: lease released on vm-095; VERDICT: R1.6 PASS (2 of 2).
# ---------------------------------------------------------------------------------------------------------
Set-Location C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\w-r1-lease
$top = git rev-parse --show-toplevel
$ok = 0
if (($top -replace '/', '\') -eq 'C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\w-r1-lease') { $ok++ }
..\argus_production\.venv\Scripts\python.exe brain/tools/brain.py --as juanbetancurm release --vm vm-095
if ($LASTEXITCODE -eq 0) { $ok++ }
if ($ok -eq 2) { 'VERDICT: R1.6 PASS (2 of 2)' } else { "VERDICT: R1.6 FAIL ($ok of 2)" }
