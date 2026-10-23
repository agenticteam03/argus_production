"""Where the signed audit digests are put (ACR-0018 §5, decision 7).

A sink takes an object name and its bytes and creates it **once**: it never overwrites (the real store's credential
cannot). `put_once` answers `stored`, `exists_same` (the same bytes were already there: a re-run) or `exists_different`
(someone else's bytes under that name: reported, never replaced). `off_host` says whether the store is outside the VMs;
the local sink is for tests and the lab and says it is not.
"""
from __future__ import annotations

from pathlib import Path, PurePosixPath


class LocalDirSink:
    off_host = False

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def _path(self, name: str) -> Path:
        p = PurePosixPath(name)
        if p.is_absolute() or ".." in p.parts or not p.parts:
            raise ValueError(f"not a relative name inside the store: {name!r}")
        return self.root.joinpath(*p.parts)

    def put_once(self, name: str, data: bytes) -> str:
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "xb") as f:                 # exclusive create: it fails if the name is taken
                f.write(data)
            return "stored"
        except FileExistsError:
            return "exists_same" if path.read_bytes() == data else "exists_different"
