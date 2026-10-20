## 2026-10-20 — CLEANUP-eval-offers: EVAL-offers leftovers removed from vm-095

Type: maintenance
Who: conantkd (+ agent)
Context: EVAL-offers (2026-10-19) left 13 images `argus-v18-agent:eo-*` and `/tmp/eo-*` on vm-095, used by no
service. Its results are archived in its evidence. NEXT_STEP listed their removal as a small item.
Decision / result:
- Listed first: no container used an `eo-` image.
- 13 images and every `/tmp/eo-*` removed; about 2 GB of disk freed.
- Services unchanged; LAB BASELINE OK; NO INTERFERENCE before and after.
Consequences:
- vm-095 holds only the images of the running services and its build cache.
References: [evidence](../../execution/history/CLEANUP-eval-offers/step-01/evidence.md).

### Test state

No code change.

### Next step

None for this item.
