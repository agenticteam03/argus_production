"""ACR-0034 local tier: a source is fetched into a staging folder, and only an administrator's approval installs it.

`fetch_to_staging` builds one allowlisted source's bundle under `<staging>/<name>/` and never touches the installed
corpus. `approve` verifies the staged bundle's hashes, merges it with the installed sources (the approved source's
old passages are replaced) and installs the result; `reject` deletes the staged bundle. The worker keeps its
read-only connection to the installed index, so it reads an approved source after its next restart.
"""
from __future__ import annotations

import json
import re
import shutil
from collections.abc import Callable
from pathlib import Path

from argus.corpus import bundle
from argus.corpus.sources import Source

NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


class StagingRefused(RuntimeError):
    pass


def _name(name: str) -> str:
    if not NAME.match(name or ""):
        raise StagingRefused(f"{name!r} is not a source name")
    return name


def fetch_to_staging(source: Source, staging: Path, fetcher: Callable[[Source], bytes] | None = None,
                     log: Callable[[str], None] = lambda _: None) -> dict:
    """Build `source` alone into `<staging>/<name>/` (built aside, renamed into place). Never installs."""
    staging = Path(staging)
    final, tmp = staging / _name(source.name), staging / f".{source.name}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    manifest = bundle.build([source], tmp, fetcher=fetcher, log=log)
    shutil.rmtree(final, ignore_errors=True)
    tmp.rename(final)
    return manifest


def _manifest(directory: Path) -> dict | None:
    path = directory / "manifest.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    except (OSError, ValueError):
        return None


def list_sources(staging: Path | None, corpus: Path | None) -> list[dict]:
    """The installed sources and the staged ones (a staged source may also be installed at another ref)."""
    out: list[dict] = []
    installed = _manifest(Path(corpus)) if corpus else None
    for s in (installed or {}).get("sources", []):
        out.append({"name": s["name"], "ref": s["ref"], "licence": s.get("licence", ""), "status": "installed",
                    "passages": s.get("passages", 0), "quarantined": s.get("quarantined", 0),
                    "at": installed.get("built_at"), "sha256": installed.get("passages_sha256", "")})
    if staging and Path(staging).is_dir():
        for d in sorted(p for p in Path(staging).iterdir() if p.is_dir() and NAME.match(p.name)):
            m = _manifest(d)
            if not m:
                continue
            for s in m.get("sources", []):
                out.append({"name": d.name, "ref": s["ref"], "licence": s.get("licence", ""), "status": "staged",
                            "passages": s.get("passages", 0), "quarantined": s.get("quarantined", 0),
                            "at": m.get("built_at"), "sha256": m.get("passages_sha256", "")})
    return out


def staged_sha256(staging: Path, name: str) -> str:
    """The staged bundle's passages hash (what an approval's step-up is bound to), or StagingRefused."""
    m = _manifest(Path(staging) / _name(name))
    if not m:
        raise StagingRefused(f"nothing staged for {name}")
    return str(m.get("passages_sha256", ""))


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line] if path.is_file() else []


def approve(name: str, staging: Path, corpus: Path, expected_sha256: str) -> dict:
    """Verify the staged bundle (its hash must be the one approved), merge it with the installed corpus, install."""
    src = Path(staging) / _name(name)
    try:
        manifest, rows = bundle.verify(src)
    except bundle.BundleRefused as e:
        raise StagingRefused(f"staged bundle refused: {e}") from e
    if manifest.get("passages_sha256") != expected_sha256:
        raise StagingRefused("the staged bundle changed after it was shown")
    corpus = Path(corpus)
    current = _manifest(corpus) or {"sources": []}
    if current.get("sources"):
        try:
            _, installed = bundle.verify(corpus)
        except bundle.BundleRefused as e:
            raise StagingRefused(f"installed corpus refused: {e}") from e
    else:
        installed = []
    merge = Path(staging) / f".{name}.merge"
    shutil.rmtree(merge, ignore_errors=True)
    merge.mkdir(parents=True)
    passages = [r for r in installed if r["source"] != name] + rows
    quarantine = [r for r in _rows(corpus / "quarantine.jsonl") if r.get("source") != name] + _rows(src / "quarantine.jsonl")
    merged = {"format": bundle.BUNDLE_FORMAT, "built_at": manifest["built_at"],
              "sources": [s for s in current.get("sources", []) if s["name"] != name] + manifest["sources"],
              "passages_sha256": bundle._write_jsonl(merge / "passages.jsonl", passages),
              "quarantine_sha256": bundle._write_jsonl(merge / "quarantine.jsonl", quarantine)}
    (merge / "manifest.json").write_text(json.dumps(merged, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    try:
        bundle.install(merge, corpus)
    finally:
        shutil.rmtree(merge, ignore_errors=True)
    shutil.rmtree(src, ignore_errors=True)
    return merged


def reject(name: str, staging: Path) -> None:
    src = Path(staging) / _name(name)
    if not _manifest(src):
        raise StagingRefused(f"nothing staged for {name}")
    shutil.rmtree(src)
