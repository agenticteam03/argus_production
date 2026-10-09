# Evaluation (ARCHITECTURE §21.2, T-0025)

Replayable cases (`cases/*.yaml`) and thresholds (`thresholds.yaml`). The harness is `argus/evaluation/`:

    python -m argus.evaluation --cases tests/eval/cases [--category C] [--strategy NAME] [--trials N]

A case is replayed through the real wiring (policy, graph, evidence store) with fixture executors and a fixed metric
snapshot, then graded. Case fields:

| Field | Meaning |
|---|---|
| `id`, `category` | unique id; `class` for a diagnosable incident, otherwise the §21.2 safety row (`unsupported`, `stale_metrics`, `forbidden_target`, `healthy_check`, `tool_failure`, `ambiguous`) |
| `target`, `request`, `reason` | what is asked (`request`: `report` or `check`) |
| `metrics` | signal values per target (`{target: {signal: value}}`); `stale: true` instead = no fresh samples |
| `fixtures` | the answer of each read, per executor and path (`"*"` = any path); `{error: <category>}` makes the read fail |
| `secrets` | planted strings that must never reach a model request |
| `label` | `outcome` (or a list), `class`, `root_cause`, `abstain`, `model_calls` (exact), `diagnosis_any`, `findings_any`, `runbooks` (for recall@3) |
