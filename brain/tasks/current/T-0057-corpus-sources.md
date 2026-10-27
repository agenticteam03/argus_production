# T-0057 - Local corpus sources: staged fetch and approval API

Status: implemented (code only), not deployed. Architecture 1.8.40. ACR: [ACR-0034](../../architecture/changes/ACR-0034-reference-corpus.md) (local tier).

## Goal

An installation adds a reference source without a developer: a fetch stages it, an administrator approves it.

## Done

- `argus corpus fetch --source <name> [--local-sources FILE]`: stages one allowlisted source, never installs.
- `argus-v18-corpus` (compose profile `corpus`): internal network, egress proxy only, no secret, writes the staging
  folder only. The egress filter is unchanged: the documentation hosts wait for a per-client filter (the scheduler shares the proxy).
- `GET /api/v1/ops/corpus/sources`, `POST /api/v1/ops/corpus/sources/{name}/approve|reject`: role `admin`
  (`manage_corpus`, privileged), step-up bound to `corpus:<name>:<sha256>`, hashes verified, merged install, audited.

## Next

- T-0058: the UI screen for these routes.
- Deploy: create `/opt/argus-v18/corpus-staging`, rebuild the egress image and the agent; an `admin` user
  (`argus user add --role admin`) with two security keys; restart the worker after an approval.
- Later: inventory-driven proposals of missing sources.
