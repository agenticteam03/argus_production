"""ACR-0034 layer 1 (origin): download a source's pinned archive and read its matching files, nothing else.

Redirects are followed by hand, each hop checked against the source's own hosts (HTTPS only); the body is streamed
with a byte cap. The archive is never extracted to disk: matching regular files are read in memory (no symlink, no
device, no path escapes possible), each under its own cap. Nothing from an archive is ever executed.
"""
from __future__ import annotations

import fnmatch
import io
import tarfile
from collections.abc import Iterator
from urllib.parse import urljoin, urlsplit

import httpx

from argus.corpus.sources import Source, host_of

MAX_REDIRECTS = 5


class FetchRefused(RuntimeError):
    pass


def fetch_archive(source: Source, client: httpx.Client | None = None) -> bytes:
    http = client or httpx.Client(timeout=60.0, follow_redirects=False)
    url = source.archive_url
    for _ in range(MAX_REDIRECTS + 1):
        if urlsplit(url).scheme != "https" or host_of(url) not in source.hosts:
            raise FetchRefused(f"{source.name}: {host_of(url) or url} is not allowlisted for this source")
        with http.stream("GET", url, follow_redirects=False) as r:
            if r.status_code in (301, 302, 303, 307, 308):
                url = urljoin(url, r.headers.get("location", ""))
                continue
            if r.status_code != 200:
                raise FetchRefused(f"{source.name}: HTTP {r.status_code}")
            buf = bytearray()
            for chunk in r.iter_bytes():
                buf.extend(chunk)
                if len(buf) > source.max_archive_bytes:
                    raise FetchRefused(f"{source.name}: archive larger than {source.max_archive_bytes} bytes")
            return bytes(buf)
    raise FetchRefused(f"{source.name}: too many redirects")


def _wanted(name: str, source: Source) -> bool:
    return (any(fnmatch.fnmatchcase(name, g) for g in source.include)
            and not any(fnmatch.fnmatchcase(name, g) for g in source.exclude))


def members(data: bytes, source: Source) -> Iterator[tuple[str, str]]:
    """(member path, text) of each wanted regular file, in path order."""
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tar:
        for m in sorted(tar.getmembers(), key=lambda m: m.name):
            if not m.isreg() or m.size > source.max_member_bytes or not _wanted(m.name, source):
                continue
            f = tar.extractfile(m)
            if f is None:
                continue
            yield m.name, f.read().decode("utf-8", errors="replace")
