#!/usr/bin/env bash
# T-0025 step 3 (ARCHITECTURE §21.2): run the evaluation cases with the configured model, on vm-095, in a ONE-OFF
# container from the agent image. It gets only what it needs: the model key (one file, read-only) and the cases
# (read-only); an output folder for the results. No executor token, no database credential, not on argus-v18-core:
# the replay answers every read from the case fixtures, so it can reach nothing but the model's API.
#   sudo bash ops/eval-run.sh --as <lease holder> [--trials N] [--category C] [--strategy S]
# Last lines: the summary, the per-class table, "hard: a b c"; the results are in $OUT (one JSON line per run).
set -euo pipefail

HOME_DIR=${ARGUS_DEPLOY_HOME:-/opt/argus-v18}
DOCKER=${ARGUS_DOCKER:-docker}
IMAGE=${ARGUS_EVAL_IMAGE:-argus-v18-agent:1}
KEY="$HOME_DIR/secrets/agent/openai_api_key"
CASES=${ARGUS_EVAL_CASES:-$HOME_DIR/app/tests/eval}   # the tests/eval folder of the evaluated branch
OUTDIR="$HOME_DIR/eval-results"
WHO=""
EXTRA=()

stop() { echo "EVAL STOP: $*"; exit 1; }
while [ $# -gt 0 ]; do
  case "$1" in
    --as) shift; WHO=${1:-} ;;
    --trials|--category|--strategy) EXTRA+=("$1" "${2:-}"); shift ;;
    *) stop "unknown argument $1" ;;
  esac
  shift
done

[ -n "$WHO" ] || stop "needs --as <lease holder>"
grep -q "^holder=$WHO " "$HOME_DIR/SESSION" 2>/dev/null || stop "NOT YOUR SESSION"
[ -s "$KEY" ] || stop "model key missing"
[ -d "$CASES/cases" ] || stop "no cases at $CASES/cases (is the checkout on a branch with T-0025?)"
mkdir -p "$OUTDIR" && chown 10010:10010 "$OUTDIR"
OUT="eval-$(date -u +%Y%m%d-%H%M%S).jsonl"

"$DOCKER" run --rm --name argus-v18-eval --user 10010:10010 --read-only --tmpfs /tmp:size=64m \
  --cap-drop ALL --security-opt no-new-privileges --pids-limit 64 --memory 512m \
  --mount "type=bind,source=$KEY,target=/run/eval-secrets/openai_api_key,readonly" \
  --mount "type=bind,source=$CASES,target=/eval,readonly" \
  --mount "type=bind,source=$OUTDIR,target=/out" \
  -e ARGUS_SECRETS_DIR=/run/eval-secrets -e ARGUS_DB_BACKEND=sqlite -e ARGUS_TOOL_CATALOGUE=direct \
  -e ARGUS_LLM_MODEL="${ARGUS_LLM_MODEL:-gpt-5.6-luna}" \
  "$IMAGE" python -m argus.evaluation --cases /eval/cases --model configured --workdir /tmp/eval \
  --out "/out/$OUT" "${EXTRA[@]}"
echo "results: $OUTDIR/$OUT"
