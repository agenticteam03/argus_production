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

# =====================================================================================
# OP-013 step 02 — the model on the held-out set, vm-095 (developer decision 2026-10-22 06:00)      [~30 min]
# Why: D-003 put two classes on the baseline from cases its rules were written from; the baseline scores 6/12 on the
#   held-out set (offline). This measures the model strategies those classes had before D-003, on the same 12 cases.
# What: the deployed image and config (no build, no deploy); the cases are this branch's commit 45869b8, archived to
#   /opt/argus-v18/eval-op013. Two runs of ops/eval-run.sh, 12 cases x 5 trials each: model_loop, then
#   plan_then_reason (120 model runs, a few model calls each). Detached on the VM; OP13.4 reads the results.
# MUTATES: /opt/argus-v18/eval-op013 (new) and two results files in /opt/argus-v18/eval-results. Nothing else.
# UNDO: sudo rm -rf /opt/argus-v18/eval-op013 (the results files are kept as evidence).
# Run OP13.5 (release) at the end, also if a step fails.
# =====================================================================================

# ---------------------------------------------------------------------------------------------------------
# OP13.2 [LAPTOP · PowerShell]  claim the vm-095 lease for OP-013 and extend it to 120 minutes
# brain.py start needs a clean tree: this code.bash is stashed during the claim and restored right after.
# Expected: 'Lease CLAIMED by juanbetancurm on vm-095', the SESSION line (copy its session id into OP13.3),
#   'Lease renewed'; git status shows only code.bash; VERDICT: OP13.2 PASS (2 of 2).
# ---------------------------------------------------------------------------------------------------------
Set-Location C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\w-op013
git rev-parse --show-toplevel
$ok = 0
git stash push -q -- brain/execution/current/code.bash
..\argus_production\.venv\Scripts\python.exe brain/tools/brain.py start --task OP-013 --vm vm-095
if ($LASTEXITCODE -eq 0) { $ok++ }
..\argus_production\.venv\Scripts\python.exe brain/tools/brain.py renew --vm vm-095 --minutes 120
if ($LASTEXITCODE -eq 0) { $ok++ }
git stash pop -q
git status --short
if ($ok -eq 2) { 'VERDICT: OP13.2 PASS (2 of 2)' } else { "VERDICT: OP13.2 FAIL ($ok of 2)" }

# ---------------------------------------------------------------------------------------------------------
# OP13.3 [VM vm-095 · bash]  (ssh argus-vm095) marker, before, the held-out cases, start both runs detached
# Replace <session> with the session id OP13.2 printed. Everything after the marker runs only if SESSION is ours.
# Expected: SESSION OK; ref= and LAB BASELINE OK; a before snapshot; 'cases sha=45869b8...'; 'cases: 12';
#   'runs started'; a minute later a count > 0 of PASS/FAIL lines in the log.
# ---------------------------------------------------------------------------------------------------------
echo 'holder=juanbetancurm session=<session>' | sudo tee /opt/argus-v18/SESSION >/dev/null
if grep -q 'holder=juanbetancurm session=' /opt/argus-v18/SESSION; then
  echo "SESSION OK"
  sudo bash /opt/argus-v18/app/ops/deploy.sh status </dev/null | grep -E '^(commit|ref)=|LAB BASELINE'
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh before </dev/null | tail -1
  export GIT_SSH_COMMAND="ssh -i /opt/argus-v18/secrets/deploy/id_ed25519 -o IdentitiesOnly=yes -o UserKnownHostsFile=/opt/argus-v18/secrets/deploy/known_hosts -o StrictHostKeyChecking=yes -o BatchMode=yes"
  G="git -C /opt/argus-v18/app -c safe.directory=/opt/argus-v18/app"
  sudo --preserve-env=GIT_SSH_COMMAND $G fetch --quiet origin task/OP-013-held-out-set </dev/null
  SHA=$(sudo $G rev-parse FETCH_HEAD); echo "cases sha=$SHA"
  case $SHA in
    45869b8*)
      sudo rm -rf /opt/argus-v18/eval-op013 && sudo mkdir -p /opt/argus-v18/eval-op013
      sudo $G archive "$SHA" tests/eval/heldout | sudo tar -x -C /opt/argus-v18/eval-op013
      echo "cases: $(ls /opt/argus-v18/eval-op013/tests/eval/heldout/cases | wc -l)"
      L=/opt/argus-v18/eval-results/op013.log
      R="env ARGUS_EVAL_CASES=/opt/argus-v18/eval-op013/tests/eval/heldout bash /opt/argus-v18/app/ops/eval-run.sh --as juanbetancurm --trials 5"
      sudo sh -c "nohup sh -c '$R --strategy model_loop; $R --strategy plan_then_reason' > $L 2>&1 &"
      echo "runs started"
      sleep 60; sudo grep -cE ' (PASS|FAIL) ' $L
      ;;
    *) echo "OP13.3 STOP: the branch is not at 45869b8" ;;
  esac
else
  echo "NOT YOUR SESSION - stop here"
fi


# (OP13.3b was written by S1)
# ---------------------------------------------------------------------------------------------------------
# OP13.3b [VM vm-095 · bash]  (ssh argus-vm095) are the OP-013 runs alive? Read-only.
# Expected: SESSION OK; the log may still be empty (Python buffers it); one or more eval processes and an eval container 'Up'.
# ---------------------------------------------------------------------------------------------------------
if grep -q 'holder=juanbetancurm session=' /opt/argus-v18/SESSION; then
  echo "SESSION OK"
  L=/opt/argus-v18/eval-results/op013.log
  sudo wc -l $L; sudo tail -15 $L
  echo "PASS/FAIL lines: $(sudo grep -cE '(PASS|FAIL)' $L)"
  pgrep -fa 'eval-run|argus.evaluation' | cut -c1-150
  sudo docker ps --format '{{.Names}} {{.Image}} {{.Status}}' | grep -i eval
else
  echo "NOT YOUR SESSION - stop here"
fi

# ---------------------------------------------------------------------------------------------------------
# OP13.3c [VM vm-095 · bash]  (ssh argus-vm095) the deployed image is 6c83da3, before T-0047 H4: its Case model
#   forbids `label.expected_hypotheses`. Remove that key from the VM copy of the 12 cases only (the repo is
#   unchanged), then start both runs again with a new log. PASS/FAIL is graded the same on 6c83da3 and main
#   (checked offline: the stripped copies load with 6c83da3's code; its offline baseline is 6/12, same failing cases).
# Expected: SESSION OK; 'labels before: 10'; 'labels after: 0'; 'cases: 12'; 'runs started'; after 90 s
#   'argus-v18-eval Up ...' and 'errors: 0'.
# ---------------------------------------------------------------------------------------------------------
if grep -q 'holder=juanbetancurm session=' /opt/argus-v18/SESSION; then
  echo "SESSION OK"
  D=/opt/argus-v18/eval-op013/tests/eval/heldout
  echo "labels before: $(sudo grep -l 'expected_hypotheses:' $D/cases/heldout-*.yaml | wc -l)"
  sudo python3 -c 'import glob, sys
for f in glob.glob(sys.argv[1] + "/*.yaml"):
    o, s = [], None
    for x in open(f, newline="").read().splitlines(True):
        i = len(x) - len(x.lstrip(" "))
        if s is not None and x.strip() and i <= s and not (i == s and x.lstrip().startswith("- ")):
            s = None
        if s is not None:
            continue
        if x.strip() == "expected_hypotheses:":
            s = i
            continue
        o.append(x)
    open(f, "w", newline="").write("".join(o))' $D/cases
  echo "labels after: $(sudo grep -l 'expected_hypotheses:' $D/cases/heldout-*.yaml | wc -l)"
  echo "cases: $(ls $D/cases | wc -l)"
  L=/opt/argus-v18/eval-results/op013c.log
  R="env ARGUS_EVAL_CASES=$D bash /opt/argus-v18/app/ops/eval-run.sh --as juanbetancurm --trials 5"
  sudo sh -c "nohup sh -c '$R --strategy model_loop; $R --strategy plan_then_reason' > $L 2>&1 &"
  echo "runs started"
  sleep 90
  sudo docker ps --format '{{.Names}} {{.Status}}' | grep argus-v18-eval
  echo "errors: $(sudo grep -cE 'Traceback|EVAL STOP' $L)"
else
  echo "NOT YOUR SESSION - stop here"
fi

# ---------------------------------------------------------------------------------------------------------
# OP13.4 [VM vm-095 · bash]  (about 60 min after OP13.3c) both summaries, the per-class counts, after
# Each class counts only its 6 cases from its own run (D-003 counts the ambiguous one too): passes per trial of 6.
# Expected: two 'results:' lines; two summaries with 'hard: 0 0 0' (6c83da3 has three hard checks);
#   'dep model_loop: trials [...] mean ...'; 'nginx plan_then_reason: trials [...] mean ...'; NO INTERFERENCE.
#   If the second 'results:' is missing, the second run is still going: wait and run OP13.4 again.
# ---------------------------------------------------------------------------------------------------------
if grep -q 'holder=juanbetancurm session=' /opt/argus-v18/SESSION; then
  L=/opt/argus-v18/eval-results/op013c.log
  sudo grep -E '^cases|runs|^hard|^results|EVAL STOP' $L
  F1=$(sudo grep '^results:' $L | sed -n 1p | cut -d' ' -f2); F2=$(sudo grep '^results:' $L | sed -n 2p | cut -d' ' -f2)
  for pair in "heldout-dep $F1 model_loop" "heldout-nginx $F2 plan_then_reason"; do
    set -- $pair
    sudo cat "$2" | python3 -c 'import json, sys
p, s = sys.argv[1], sys.argv[2]
rows = [json.loads(x) for x in sys.stdin if x.strip() and json.loads(x)["case"].startswith(p)]
t = {}
for r in rows:
    t.setdefault(r["trial"], []).append(r["verdict"] == "PASS")
per = [sum(v) for k, v in sorted(t.items())]
bad = sorted({r["case"][8:] for r in rows if r["verdict"] != "PASS"})
print(p[8:], s + ":", "trials", per, "of", [len(v) for k, v in sorted(t.items())],
      "mean", round(sum(per) / max(1, 6 * len(per)), 2), "worst", min(per or [0]), "failing", bad)' "$1" "$3"
  done
  sudo bash /opt/argus-v18/app/ops/nonint-check.sh after </dev/null | tail -1
else
  echo "NOT YOUR SESSION - stop here"
fi


# (OP13.4b was written by S1: the 6c83da3 eval-run.sh printed no 'results:' line)
ubuntu@argus-vm095:~$ ---------------------------------------------------------------------------------------------------------
# OP13.4b [VM vm-095 · bash]  (ssh argus-vm095) per-class trials and failing cases from the two newest results files. Read-only.
# Expected: SESSION OK; two eval-*.jsonl names; for each file, "dep" and "nginx" lines with trials, mean, failing.
# ---------------------------------------------------------------------------------------------------------
if grep -q 'holder=juanbetancurm session=' /opt/argus-v18/SESSION; then
  echo "SESSION OK"
  for f in $(sudo ls -1t /opt/argus-v18/eval-results/eval-*.jsonl | head -2 | sort); do
    echo "file: $f lines: $(sudo wc -l "$f" | cut -d" " -f1)"
    sudo cat "$f" | python3 -c 'import json, sys
rows = [json.loads(x) for x in sys.stdin if x.strip()]
for p in ("heldout-dep", "heldout-nginx"):
    r = [x for x in rows if x["case"].startswith(p)]
    t = {}
    for x in r:
        t.setdefault(x["trial"], []).append(x["verdict"] == "PASS")
    per = [sum(v) for k, v in sorted(t.items())]
    bad = {}
    for x in r:
        if x["verdict"] != "PASS":
            bad[x["case"][8:]] = bad.get(x["case"][8:], 0) + 1
    print(p[8:], "trials", per, "of", [len(v) for k, v in sorted(t.items())], "mean", round(sum(per) / max(1, sum(len(v) for v in t.values())), 2), "failing", bad)'
  done
else
  echo "NOT YOUR SESSION - stop here"
fi

# ---------------------------------------------------------------------------------------------------------
# OP13.5 [LAPTOP · PowerShell]  release the vm-095 lease (run it also if a step above failed)
# Expected: 'Lease released on vm-095.'; VERDICT: OP13.5 PASS (1 of 1).
# >>> Paste everything into w-op013\brain\execution\current\output.bash and tell the agent "output updated". <<<
# ---------------------------------------------------------------------------------------------------------
Set-Location C:\repos\ml_course_tasks\agent_frameworks\wwfinal_project\w-op013
git rev-parse --show-toplevel
$ok = 0
..\argus_production\.venv\Scripts\python.exe brain/tools/brain.py release --vm vm-095
if ($LASTEXITCODE -eq 0) { $ok++ }
if ($ok -eq 1) { 'VERDICT: OP13.5 PASS (1 of 1)' } else { "VERDICT: OP13.5 FAIL ($ok of 1)" }
