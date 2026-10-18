## 2026-10-18 — LF-3 step 03: vm-095's worker exports to Langfuse Cloud (EU), ACR-0016 applied

Type: deployment
Who: conantkd (+ agent)
Context: ACR-0013 and ACR-0016 were accepted in the review of #156 (juanbetancurm); this push applies them
(`ARCHITECTURE.md` 1.8.16, Hobby plan with two named users) and records the deployment.
Decision / result: vm-095 runs 7e6e33c (the head of #156, deployed before its merge because the compose line for
`ARGUS_TRACING_ENDPOINT` is only there). The worker traces to Cloud: a healthy check and an SC-02 crash loop produced
traces whose attributes are exactly the allowlist (no input or output); with Cloud unreachable SC-02 still passed, one
dropped-telemetry line, same duration, full audit. The self-hosted stack, its volumes, images and secrets were
removed. The team keeps option C (no prompts, results or tool arguments in Langfuse; audit in Argus).
Consequences: operators open the trace from the incident view; the Agent page shows only the trace id. Takeover of an
EXPIRED lease of juanbetancurm (DEPLOY-164) on both VMs. The next deploy of `main` replaces 7e6e33c.
References: [evidence](../../execution/history/LF-3/step-03/evidence.md),
[ACR-0016](../../architecture/changes/ACR-0016-langfuse-cloud.md).

### Test state

No code change in this push (the Brain only). The existing tracing and compose tests were green on the PR.

### Next step

#156 is merged (`f7df417`). Deploy `main` to vm-095 (`ref=main`) with the usual state probe. Name the two Hobby users in Cloud. Restore vm-166's `argus-lab-cache` in the next vm-166 session.
