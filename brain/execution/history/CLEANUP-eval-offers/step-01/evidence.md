# CLEANUP-eval-offers step 01 — evidence: EVAL-offers leftovers removed from vm-095 (2026-10-20, conantkd, session f14c4089c29d)

Goal: remove what EVAL-offers left on vm-095. Its own evidence lists the leftovers
([`../../EVAL-offers/step-01/evidence.md`](../../EVAL-offers/step-01/evidence.md), last note): the images
`argus-v18-agent:eo-*` and `/tmp/eo-*` (sources, driver scripts and logs). Its results are archived there.

Lease: vm-095 only (no agent change). Commands: [`code.bash`](code.bash). Times are UTC.

| Block | Observed | Result |
|---|---|---|
| C.1 list | 13 images `argus-v18-agent:eo-{e0,e1,e2,e3,e4a,f0,f1,f2,f3,f4,f5,g0,h1}` (418 MB each, 17 to 25 hours old); `/tmp/eo-*`: 13 source copies (6.2 MB each), their build, run and done logs, 6 driver scripts and logs; **no container uses an `eo-` image** | OK |
| C.2 remove | `nonint-check before` saved (54 lines); **13 images removed**; no `/tmp/eo-*` left; disk used 31G → 30G, available 65G → 67G | OK |
| C.2 after | `argus-v18-ui` healthy, agent, worker, scheduler up (unchanged, about an hour), `argus-v18-postgres` healthy (10 days); `commit=2c7248b48c09` `ref=2c7248b`; `LAB BASELINE OK`; `NO INTERFERENCE: non-Argus objects unchanged` | OK |
