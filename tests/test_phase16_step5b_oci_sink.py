"""ACR-0018 §5 / phase 16 step 5b: the OCI Object Storage sink for the signed audit digests.

The bucket is the one proved by hand on 2026-10-23: a create-only credential (`OBJECT_CREATE` and `OBJECT_INSPECT`), a
time-bound retention rule, versioning off. The sink creates an object **once**; if the name is taken it looks at the
object (a HEAD, which `OBJECT_INSPECT` allows) and says whether it holds the same digest. It never overwrites, and it
never reads a body (the credential cannot). These tests use a fake client; the last one runs against a real bucket only
when `ARGUS_TEST_OCI_CONFIG` and `ARGUS_TEST_OCI_BUCKET` are set.
"""
from __future__ import annotations

import base64
import hashlib
import os
import uuid
from types import SimpleNamespace

import pytest

from argus.adapters.outbound.digest_sinks import DigestSinkError, OciObjectSink

NAME = "audit-digest/2026/2026-10-20.json"
DATA = b'{"digest":{"day":"2026-10-20"}}\n'
SHA = hashlib.sha256(DATA).hexdigest()


class ServiceError(Exception):
    """What `oci.exceptions.ServiceError` carries that the sink reads: a status and a short code."""

    def __init__(self, status: int, code: str, message: str = "namespace axxx bucket secret-bucket request ids"):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class FakeClient:
    def __init__(self, put_error: Exception | None = None, head: object = None):
        self.put_error, self.head, self.calls = put_error, head, []

    def put_object(self, namespace_name, bucket_name, object_name, put_object_body, **kwargs):
        self.calls.append(("put", namespace_name, bucket_name, object_name, put_object_body, kwargs))
        if self.put_error:
            raise self.put_error
        return SimpleNamespace(status=200, headers={})

    def head_object(self, namespace_name, bucket_name, object_name, **kwargs):
        self.calls.append(("head", namespace_name, bucket_name, object_name))
        if isinstance(self.head, Exception):
            raise self.head
        return SimpleNamespace(status=200, headers=self.head or {})


def sink(client) -> OciObjectSink:
    return OciObjectSink(client, "ns", "bkt")


# --- creating -----------------------------------------------------------------------------------------------------------
def test_a_new_name_is_created_once_with_a_checksum_and_the_digest_hash():
    c = FakeClient()
    assert sink(c).off_host is True
    assert sink(c).put_once(NAME, DATA) == "stored"
    (_, ns, bucket, name, body, kwargs), = c.calls
    assert (ns, bucket, name, body) == ("ns", "bkt", NAME, DATA)
    assert kwargs["if_none_match"] == "*"                              # create only: the service refuses a taken name
    assert kwargs["content_md5"] == base64.b64encode(hashlib.md5(DATA).digest()).decode()
    assert kwargs["content_type"] == "application/json"
    assert kwargs["opc_meta"] == {"sha256": SHA}                       # lets a later HEAD recognise the same bytes


# --- a taken name ---------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("status, code", [(412, "PreconditionFailed"), (403, "RetentionRuleViolation"),
                                          (409, "ObjectAlreadyExists")])
def test_a_taken_name_with_the_same_digest_is_exists_same_whatever_the_refusal(status, code):
    c = FakeClient(put_error=ServiceError(status, code), head={"opc-meta-sha256": SHA})
    assert sink(c).put_once(NAME, DATA) == "exists_same"
    assert [x[0] for x in c.calls] == ["put", "head"]


def test_a_taken_name_with_other_bytes_or_none_of_ours_is_exists_different():
    other = hashlib.sha256(b"someone else").hexdigest()
    assert sink(FakeClient(ServiceError(412, "PreconditionFailed"), {"opc-meta-sha256": other})).put_once(
        NAME, DATA) == "exists_different"
    assert sink(FakeClient(ServiceError(412, "PreconditionFailed"), {})).put_once(NAME, DATA) == "exists_different"


# --- failures ---------------------------------------------------------------------------------------------------------------
def test_a_refusal_with_no_object_behind_it_is_an_error_that_names_the_status_and_code_only():
    c = FakeClient(ServiceError(404, "BucketNotFound"), ServiceError(404, "NotAuthorizedOrNotFound"))
    with pytest.raises(DigestSinkError) as e:
        sink(c).put_once(NAME, DATA)
    assert e.value.reason == "put refused: http 404 BucketNotFound"
    assert "ns" not in e.value.reason.split() and "secret-bucket" not in str(e.value) and "axxx" not in str(e.value)


def test_a_head_that_fails_for_another_reason_is_an_error_too():
    c = FakeClient(ServiceError(412, "PreconditionFailed"), ServiceError(500, "InternalServerError"))
    with pytest.raises(DigestSinkError) as e:
        sink(c).put_once(NAME, DATA)
    assert e.value.reason == "head failed: http 500 InternalServerError"


def test_a_transport_error_is_not_a_refusal_and_looks_at_nothing():
    c = FakeClient(put_error=ConnectionError("reset"))
    with pytest.raises(ConnectionError):
        sink(c).put_once(NAME, DATA)
    assert [x[0] for x in c.calls] == ["put"]


# --- the job says why -----------------------------------------------------------------------------------------------------------
def test_a_failed_digest_event_carries_the_sinks_reason_and_nothing_else(tmp_path):
    from datetime import datetime, timezone

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from argus.adapters.outbound.sqlite_store import SqliteStore
    from argus.domain.model import AuditRecord
    from argus.infrastructure.audit_digest import AuditDigestJob

    store = SqliteStore(str(tmp_path / "a.db"))
    store.append(AuditRecord(audit_id="aud_0", incident_id=None, at=datetime(2026, 10, 20, 12, tzinfo=timezone.utc),
                             category="access", event="access.login", actor="u"))
    job = AuditDigestJob(store, Ed25519PrivateKey.generate(), sink(FakeClient(ServiceError(404, "BucketNotFound"),
                                                                              ServiceError(404, "x"))),
                         clock=lambda: datetime(2026, 10, 23, 8, tzinfo=timezone.utc))
    assert job.run_once().startswith("failed at 2026-10-20: DigestSinkError")
    (event,) = [a for _, b, _, _ in store.audit_chain() if (a := AuditRecord.model_validate(b)).event ==
                "security.audit_digest_failed"]
    assert event.detail == {"day": "2026-10-20", "error": "DigestSinkError", "off_host": True,
                            "reason": "put refused: http 404 BucketNotFound"}


# --- the setting ---------------------------------------------------------------------------------------------------------------
def test_the_oci_sink_needs_its_namespace_bucket_and_credential_files(monkeypatch, tmp_path):
    from argus.infrastructure.wiring import Settings, make_digest_sink
    monkeypatch.setenv("ARGUS_SECRETS_DIR", str(tmp_path))
    monkeypatch.setenv("ARGUS_AUDIT_DIGEST_SINK", "oci:onlyonepart")
    with pytest.raises(SystemExit, match="oci:<namespace>/<bucket>"):
        make_digest_sink(Settings())
    monkeypatch.setenv("ARGUS_AUDIT_DIGEST_SINK", "oci:ns/bkt")
    with pytest.raises(SystemExit, match="oci_digest/config"):          # names the missing file, before importing oci
        make_digest_sink(Settings())
    (tmp_path / "oci_digest").mkdir()
    (tmp_path / "oci_digest" / "config").write_text("[DEFAULT]\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="oci_digest/key.pem"):
        make_digest_sink(Settings())


def test_the_key_beside_the_config_wins_over_the_path_written_in_it(monkeypatch, tmp_path):
    """`key_file` in the config is a path on the person's laptop; in the container the key sits beside the config."""
    oci = pytest.importorskip("oci")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    from argus.infrastructure.wiring import oci_object_client
    d = tmp_path / "oci_digest"
    d.mkdir()
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (d / "key.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                                  serialization.NoEncryption()))
    (d / "config").write_text("[DEFAULT]\nuser=ocid1.user.oc1..aaaa\nfingerprint=aa:bb:cc:dd:ee:ff:00:11:22:33:44:55:66:77:88:99\n"
                              "tenancy=ocid1.tenancy.oc1..aaaa\nregion=sa-bogota-1\nkey_file=C:\\\\laptop\\\\old.pem\n",
                              encoding="utf-8")
    client = oci_object_client(d / "config")
    assert isinstance(client, oci.object_storage.ObjectStorageClient)


# --- against a real bucket (opt-in) ---------------------------------------------------------------------------------------------
@pytest.mark.skipif(not (os.getenv("ARGUS_TEST_OCI_CONFIG") and os.getenv("ARGUS_TEST_OCI_BUCKET")),
                    reason="set ARGUS_TEST_OCI_CONFIG (a config file) and ARGUS_TEST_OCI_BUCKET (namespace/bucket)")
def test_the_real_bucket_creates_once_and_recognises_the_same_bytes():
    """Leaves one small object under `selftest/` per run (a retention rule keeps it until the rule is removed)."""
    oci = pytest.importorskip("oci")
    config = oci.config.from_file(os.environ["ARGUS_TEST_OCI_CONFIG"], os.getenv("ARGUS_TEST_OCI_PROFILE", "DEFAULT"))
    namespace, bucket = os.environ["ARGUS_TEST_OCI_BUCKET"].split("/", 1)
    real = OciObjectSink(oci.object_storage.ObjectStorageClient(config), namespace, bucket)
    name = f"selftest/{uuid.uuid4().hex}.json"
    assert real.put_once(name, DATA) == "stored"
    assert real.put_once(name, DATA) == "exists_same"
    assert real.put_once(name, DATA + b"x") == "exists_different"
