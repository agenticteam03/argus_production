"""ACR-0034: the curated reference corpus (vendor documentation) and its layered defences.

`sources` (the allowlist), `fetch` (pinned archives from allowlisted hosts only), `sanitize` and `convert` (text,
nothing hidden), `scan` (quarantine), `bundle` (passages with provenance and hashes), `retrieval` (keyword search over
the installed bundle, hybrid ranking through a local Weaviate). Built offline; Argus only reads an installed bundle.
"""
