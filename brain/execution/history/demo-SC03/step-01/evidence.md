# DEMO-SC03 step 01 — evidence (2026-10-05, class demo run by juanbetancurm)

SC-03 (dependency unavailable) shown live in class on the LangGraph runner (vm-095 `ARGUS_RUNNER=langgraph`).

| Check | Expected | Observed |
|---|---|---|
| Before: `argus-lab-api` health, Argus `--check` | healthy, `HEALTHY` | reported OK by the developer |
| `docker stop argus-lab-cache` on vm-166 | api becomes `unhealthy` | reported OK by the developer |
| Argus investigation of `vm-166/container:argus-lab-api` | `DIAGNOSED`, root cause `vm-166/container:argus-lab-cache` | reported OK by the developer ("It worked") |
| `docker start argus-lab-cache` | api `healthy` again | reported OK by the developer |

**Status: reported, not verified.** The terminal output (incident id, root-cause line) was not pasted into
`output.bash`, so it is not archived here. `nonint-check.sh after` was not reported.
To count SC-03 as verified on LangGraph, re-run it with archived output (Phase 12).

Problems on the way (fixed in the archived `code.bash`):
- a lease released too early by the first version's last block: the next run of block 0 gave `VERDICT STOP`;
- a vm-166 block pasted on vm-095 (helpers defined only on vm-166): the final version has no helpers and labels
  every block with the VM prompt name.
