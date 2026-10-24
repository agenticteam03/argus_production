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
| `prior_incidents` | closed precedents stored before the run, for `knowledge.prior_incidents` (T-0049 R1): each `class`, `target`, `diagnosis`, `root_cause`, `closed_at` (and `outcome`, `confidence`, `findings`); a reviewed fixture that may help (the same cause before) or mislead (another cause on the same target and class) |
| `label` | `outcome` (or a list), `class`, `root_cause`, `abstain`, `model_calls` (exact), `diagnosis_any`, `findings_any`, `runbooks` (for recall@3), `expected_hypotheses` (`supported`, `ruled_out`: targets or cause classes; ACR-0024 §3.8) |

With hypotheses (ACR-0024, T-0047 H4), the summary adds a `hypotheses:` line over the runs that stated them: top-1
and top-3 root-cause accuracy over Argus's ranking (a hypothesis matching `expected_hypotheses.supported`, else
`root_cause`), ruled-out recall, the `ranking_disagrees` rate and the share of model runs with an H1 problem. The
hard line adds `unsupported_root_cause`: a diagnosis whose root cause the run never observed (no `ok` observation or metric
snapshot of it, and no `ok` observation on its host that names it, as the database's sessions name a leaking client).

