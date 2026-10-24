"""Where the signed audit digests are put (ACR-0018 §5, decision 7).

A sink takes an object name and its bytes and creates it **once**: it never overwrites (the real store's credential
cannot). `put_once` answers `stored`, `exists_same` (the same bytes were already there: a re-run) or `exists_different`
(someone else's bytes under that name: reported, never replaced). `off_host` says whether the store is outside the VMs;
the local sink is for tests and the lab and says it is not.
"""
from __future__ import annotations

import base64
import hashlib
from pathlib import Path, PurePosixPath


class DigestSinkError(Exception):
    """A store refused or failed. `reason` is short and safe to record: an HTTP status and the service's error code, never
    the service's message (it carries request ids and the names of the namespace and bucket)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


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


class OciObjectSink:
    """OCI Object Storage (ACR-0018 §5). The credential can create objects and inspect them, nothing else, so a name is
    created once (`If-None-Match: *`) and, when it is taken, looked at with a HEAD: the digest's SHA-256 travels as the
    object's metadata, so the same bytes are recognised without reading the body, which the credential cannot do."""

    off_host = True

    def __init__(self, client, namespace: str, bucket: str):
        self.client, self.namespace, self.bucket = client, namespace, bucket

    def put_once(self, name: str, data: bytes) -> str:
        sha = hashlib.sha256(data).hexdigest()
        try:
            self.client.put_object(self.namespace, self.bucket, name, data, if_none_match="*",
                                   content_md5=base64.b64encode(hashlib.md5(data, usedforsecurity=False).digest()).decode(),
                                   content_type="application/json", opc_meta={"sha256": sha})
            return "stored"
        except Exception as e:
            status = getattr(e, "status", None)
            if status is None:                          # not an answer from the service (network, timeout): the job records it
                raise
            refusal = f"put refused: http {status} {getattr(e, 'code', None)}"
        # The service said no. Whether the name is taken (a precondition, or a retention rule on an existing object) or
        # the credential is wrong, a HEAD tells: an object that is there is compared, anything else is the refusal.
        try:
            head = self.client.head_object(self.namespace, self.bucket, name)
        except Exception as e:
            head_status = getattr(e, "status", None)
            if head_status is None:
                raise
            if head_status == 404:
                raise DigestSinkError(refusal) from None
            raise DigestSinkError(f"head failed: http {head_status} {getattr(e, 'code', None)}") from None
        return "exists_same" if head.headers.get("opc-meta-sha256") == sha else "exists_different"
