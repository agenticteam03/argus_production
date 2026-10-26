# =====================================================================================
# Argus — T-0046 L6 offer measurement, review of PR #322 (2026-10-25, conantkd)
# Goal / Why: measure the `link_states` offer as two arms on the same branch and cases:
#   control = no class has the tag, treatment = the three reviewed classes have it.
# MUTATES: nothing on the VMs; laptop only, throwaway SQLite stores in a temp folder.
# Scope: deterministic baseline only (`--strategy baseline`, `--model none`). The model arm is not measured here.
# =====================================================================================

# --- T0046.L6.1 [LAPTOP · bash] control arm: the same CLI with `link_states` removed from every class's tool_tags
python - --cases tests/eval/cases --strategy baseline --out control.jsonl <<'PY'
import sys
from argus.detectors.classes import CLASSES
for spec in CLASSES:
    spec.tool_tags = set(spec.tool_tags) - {"link_states"}
from argus.evaluation.cli import main
sys.exit(main(sys.argv[1:]))
PY

# --- T0046.L6.2 [LAPTOP · bash] treatment arm: the branch as it is
python -m argus.evaluation --cases tests/eval/cases --strategy baseline --out treatment.jsonl

# --- T0046.L6.3 [LAPTOP · bash] compare the two arms
python -m argus.evaluation.compare --before control.jsonl --after treatment.jsonl --cases tests/eval/cases > compare.json
