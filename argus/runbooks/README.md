# Runbook library (reviewed copy, part of this repository)

The 21 runbooks (`RB-001` ... `RB-021`), `RUNBOOK-CONVENTIONS.md` and `RUNBOOK-INDEX.md` live here, as architecture
section 2.4 specifies. They are loaded by `TfidfRunbooks` (`argus/adapters/outbound/config_adapters.py`); IDs,
versions and status come from each file's metadata block, never from the file name.

**Provenance.** Imported unchanged on 2026-10-02 from `agenticteam03/runbooks` at commit
`056b36e06f989c475a2eb6b16fc277bdda2de25e` (library v1.1.0); the only change is line endings, normalized from CRLF to LF (so section hashes in
the recall audit differ from incidents recorded before the import) - decision D-002 (`brain/OPEN_PROBLEMS.md`). That
repository keeps the earlier history and the research material (sources, assessments, gap backlog); it is no longer
read by Argus.

**Changing a runbook.** Through a pull request like any code: bump the runbook's `version` and `last_reviewed` in its
metadata, update `RUNBOOK-INDEX.md` when the set changes, and keep `RUNBOOK-CONVENTIONS.md` as the shared contract.
