"""ACR-0034 layer 1 (origin): the allowlist of `config/corpus/sources.yaml`, validated before anything is fetched."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import yaml

MOVING_REFS = {"main", "master", "head", "latest", "trunk", "develop"}
FORMATS = {"markdown", "rst", "roff", "docbook", "openapi"}


@dataclass(frozen=True)
class Source:
    name: str
    description: str
    archive_url: str
    hosts: tuple[str, ...]
    ref: str
    licence: str
    formats: tuple[str, ...]
    include: tuple[str, ...]
    url_base: str
    max_archive_bytes: int
    max_member_bytes: int
    strip_prefix: str = ""
    exclude: tuple[str, ...] = ()
    url_style: str = "page"              # page: url_base + path without its extension; file: url_base + path
    max_passages: int = 4000
    trust: str = "official"


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def _check(s: Source) -> None:
    where = f"source {s.name!r}"
    if urlsplit(s.archive_url).scheme != "https":
        raise ValueError(f"{where}: archive_url must be HTTPS")
    if host_of(s.archive_url) not in s.hosts:
        raise ValueError(f"{where}: {host_of(s.archive_url)} is not one of its hosts")
    if not s.ref or s.ref.lower() in MOVING_REFS or s.ref not in s.archive_url:
        raise ValueError(f"{where}: needs a pinned ref (a tag or a commit) that the archive_url names")
    if not s.licence or not s.include or not s.url_base.startswith("https://"):
        raise ValueError(f"{where}: needs a licence, include globs and an HTTPS url_base")
    if not set(s.formats) <= FORMATS or not s.formats:
        raise ValueError(f"{where}: formats must be among {sorted(FORMATS)}")
    if s.max_archive_bytes <= 0 or s.max_member_bytes <= 0 or s.max_passages <= 0:
        raise ValueError(f"{where}: size caps must be positive")
    if s.url_style not in ("page", "file") or s.trust not in ("official", "target"):
        raise ValueError(f"{where}: url_style page|file, trust official|target")


def load(path: Path | str) -> list[Source]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    out, seen = [], set()
    for row in raw.get("sources") or []:
        row = dict(row)
        for key in ("hosts", "formats", "include", "exclude"):
            row[key] = tuple(str(x).lower() if key == "hosts" else str(x) for x in (row.get(key) or ()))
        s = Source(**row)
        _check(s)
        if s.name in seen:
            raise ValueError(f"source {s.name!r} listed twice")
        seen.add(s.name)
        out.append(s)
    return out
