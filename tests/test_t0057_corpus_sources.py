"""T-0057 (ACR-0034 local tier): a source is staged by `argus corpus fetch`, and only an administrator installs it.

Staging never installs; an administrator's approval (human, full token, second factor, a step-up bound to
`corpus:<name>:<passages sha256>`) verifies the staged hashes, merges the source into the installed corpus and audits
it; a rejection needs a reason. The fetch service has no secret and leaves only through the egress proxy.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from pwdlib import PasswordHash

from argus.adapters.inbound.http import build_api
from argus.corpus import bundle, sources, staging
from test_core import make_app  # noqa: F401
from test_t0056_reference_corpus import _source, _tar

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = "a-long-password"


def _fetcher(text: str):
    return lambda s: _tar({f"docs-1.0/docs/{s.name}.md": f"# {s.name}\n{text}"})


def _stage(tmp_path, name="demo", text="restart policy always restarts the container") -> Path:
    stage = tmp_path / "staging"
    staging.fetch_to_staging(_source(name=name), stage, fetcher=_fetcher(text))
    return stage


def test_fetch_stages_one_source_and_never_installs(tmp_path):
    stage = _stage(tmp_path)
    corpus = tmp_path / "corpus"
    assert (stage / "demo" / "manifest.json").is_file() and not corpus.exists()
    [row] = staging.list_sources(stage, corpus)
    assert row["status"] == "staged" and row["name"] == "demo" and row["passages"] == 1


def test_a_local_source_may_name_only_hosts_of_the_base_allowlist(tmp_path):
    base = sources.load(ROOT / "config" / "corpus" / "sources.yaml")
    good = {"name": "redis", "description": "x", "archive_url": "https://github.com/redis/docs/archive/v7.2.0.tar.gz",
            "hosts": ["github.com", "codeload.github.com"], "ref": "v7.2.0", "licence": "CC-BY-SA-4.0",
            "formats": ["markdown"], "include": ["*/docs/*.md"], "url_base": "https://redis.io/docs/",
            "max_archive_bytes": 1000, "max_member_bytes": 100}
    path = tmp_path / "local.yaml"
    path.write_text(yaml.safe_dump({"sources": [good]}), encoding="utf-8")
    assert [s.name for s in sources.load_local(path, base)] == ["redis"]
    bad = {**good, "archive_url": "https://evil.example/redis/v7.2.0.tar.gz", "hosts": ["evil.example"]}
    path.write_text(yaml.safe_dump({"sources": [bad]}), encoding="utf-8")
    with pytest.raises(ValueError, match="not in the base allowlist"):
        sources.load_local(path, base)


def test_approve_verifies_the_hash_merges_and_replaces_the_old_passages(tmp_path):
    corpus = tmp_path / "corpus"
    stage = _stage(tmp_path, text="the old text about the restart policy of a container")
    staging.approve("demo", stage, corpus, staging.staged_sha256(stage, "demo"))
    stage = _stage(tmp_path, name="other", text="nginx reloads its configuration on SIGHUP")
    staging.approve("other", stage, corpus, staging.staged_sha256(stage, "other"))
    stage = _stage(tmp_path, text="the new text about the restart policy of a container")
    staging.approve("demo", stage, corpus, staging.staged_sha256(stage, "demo"))
    manifest, rows = bundle.verify(corpus)
    assert sorted(s["name"] for s in manifest["sources"]) == ["demo", "other"]
    assert {r["source"]: r["text"] for r in rows}["demo"].endswith("the new text about the restart policy of a container") and len(rows) == 2
    assert not (stage / "demo").exists() and (corpus / "reference.db").is_file()


def test_approve_refuses_a_tampered_or_changed_staged_bundle(tmp_path):
    stage = _stage(tmp_path)
    digest = staging.staged_sha256(stage, "demo")
    with pytest.raises(staging.StagingRefused, match="changed after"):
        staging.approve("demo", stage, tmp_path / "corpus", "0" * 64)
    p = stage / "demo" / "passages.jsonl"
    p.write_text(p.read_text(encoding="utf-8").replace("restart", "rm -rf"), encoding="utf-8")
    with pytest.raises(staging.StagingRefused, match="refused"):
        staging.approve("demo", stage, tmp_path / "corpus", digest)
    with pytest.raises(staging.StagingRefused):
        staging.staged_sha256(stage, "../etc")
    with pytest.raises(staging.StagingRefused, match="nothing staged"):
        staging.reject("other", stage)


def _admin(make_app, monkeypatch, tmp_path, role="admin"):
    app = make_app()
    app.settings.corpus_staging_dir = str(tmp_path / "staging")
    app.settings.corpus_dir = str(tmp_path / "corpus")
    app.store.upsert_principal("ada", "human", role, ["lab"], PasswordHash.recommended().hash(PASSWORD))
    api = build_api(app)
    client = TestClient(api)
    token = client.post("/api/v1/auth/token", data={"username": "ada", "password": PASSWORD}).json()["access_token"]
    monkeypatch.setattr(api.state.second_factor, "privileged_ready", lambda user, session: True)
    seen: list = []
    monkeypatch.setattr(api.state.second_factor, "consume_step_up",
                        lambda token, user, session, obj: seen.append((token, user, obj)))
    return app, client, {"Authorization": f"Bearer {token}"}, seen


def test_an_administrator_lists_and_approves_with_a_step_up_bound_to_the_bundle(make_app, monkeypatch, tmp_path):  # noqa: F811
    app, client, auth, seen = _admin(make_app, monkeypatch, tmp_path)
    stage = _stage(tmp_path)
    digest = staging.staged_sha256(stage, "demo")
    listed = client.get("/api/v1/ops/corpus/sources", headers=auth)
    assert listed.status_code == 200 and listed.json()[0]["status"] == "staged"
    r = client.post("/api/v1/ops/corpus/sources/demo/approve", headers=auth, json={"step_up_token": "one"})
    assert r.status_code == 200, r.text
    assert seen == [("one", "ada", f"corpus:demo:{digest}")]
    assert [x["status"] for x in client.get("/api/v1/ops/corpus/sources", headers=auth).json()] == ["installed"]
    events = [b for _, b, _, _ in app.store.audit_chain() if b["event"] == "corpus.source_approved"]
    assert events and events[0]["actor"] == "ada" and events[0]["detail"]["source"] == "demo"
    again = client.post("/api/v1/ops/corpus/sources/demo/approve", headers=auth, json={"step_up_token": "two"})
    assert again.status_code == 409                                            # nothing staged any more


def test_an_approver_manages_the_corpus_like_an_administrator(make_app, monkeypatch, tmp_path):  # noqa: F811
    """ACR-0040: an approver lists, approves and rejects staged sources, each decision with its own step-up."""
    app, client, auth, seen = _admin(make_app, monkeypatch, tmp_path, role="approver")
    stage = _stage(tmp_path)
    digest = staging.staged_sha256(stage, "demo")
    assert client.get("/api/v1/ops/corpus/sources", headers=auth).json()[0]["status"] == "staged"
    r = client.post("/api/v1/ops/corpus/sources/demo/approve", headers=auth, json={"step_up_token": "one"})
    assert r.status_code == 200, r.text
    assert seen == [("one", "ada", f"corpus:demo:{digest}")]
    events = [b for _, b, _, _ in app.store.audit_chain() if b["event"] == "corpus.source_approved"]
    assert events and events[0]["actor"] == "ada"
    me = client.get("/api/v1/me", headers=auth).json()
    assert "manage_corpus" in me["actions"]                              # the UI shows Reference sources


def test_me_lists_the_corpus_action_only_with_the_second_factor(make_app, monkeypatch, tmp_path):  # noqa: F811
    """The UI shows Reference sources when /me lists manage_corpus (ACR-0001); it did not list it before ACR-0040."""
    for role in ("admin", "approver"):
        _, client, auth, _ = _admin(make_app, monkeypatch, tmp_path / role, role=role)
        assert "manage_corpus" in client.get("/api/v1/me", headers=auth).json()["actions"], role
    app = make_app()
    app.settings.corpus_staging_dir = str(tmp_path / "staging")
    app.store.upsert_principal("ada", "human", "approver", ["lab"], PasswordHash.recommended().hash(PASSWORD))
    client = TestClient(build_api(app))                                 # privileged_ready false: no key yet
    token = client.post("/api/v1/auth/token", data={"username": "ada", "password": PASSWORD}).json()["access_token"]
    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert "manage_corpus" not in me["actions"] and "manage_corpus" not in me["permissions"]


def test_an_operator_cannot_manage_the_corpus(make_app, monkeypatch, tmp_path):  # noqa: F811
    for role in ("operator", "viewer"):
        _, client, auth, seen = _admin(make_app, monkeypatch, tmp_path / role, role=role)
        assert client.get("/api/v1/ops/corpus/sources", headers=auth).status_code == 403
        assert client.post("/api/v1/ops/corpus/sources/demo/approve", headers=auth,
                           json={"step_up_token": "x"}).status_code == 403 and seen == []


def test_a_tampered_staged_bundle_is_409_and_a_rejection_needs_a_reason(make_app, monkeypatch, tmp_path):  # noqa: F811
    app, client, auth, seen = _admin(make_app, monkeypatch, tmp_path)
    stage = _stage(tmp_path)
    p = stage / "demo" / "passages.jsonl"
    p.write_text(p.read_text(encoding="utf-8").replace("restart", "rm -rf"), encoding="utf-8")
    assert client.post("/api/v1/ops/corpus/sources/demo/approve", headers=auth,
                       json={"step_up_token": "one"}).status_code == 409
    assert client.post("/api/v1/ops/corpus/sources/demo/reject", headers=auth,
                       json={"step_up_token": "two"}).status_code == 422             # no reason
    r = client.post("/api/v1/ops/corpus/sources/demo/reject", headers=auth,
                    json={"reason": "tampered", "step_up_token": "three"})
    assert r.status_code == 200 and not (stage / "demo").exists()
    events = [b for _, b, _, _ in app.store.audit_chain() if b["event"] == "corpus.source_rejected"]
    assert events[0]["detail"]["reason"] == "tampered"


def test_without_a_staging_folder_a_decision_is_409(make_app, monkeypatch, tmp_path):  # noqa: F811
    app, client, auth, _ = _admin(make_app, monkeypatch, tmp_path)
    app.settings.corpus_staging_dir = ""
    assert client.post("/api/v1/ops/corpus/sources/demo/approve", headers=auth,
                       json={"step_up_token": "one"}).status_code == 409


def test_the_fetch_service_has_no_secret_is_off_by_default_and_leaves_through_the_proxy():
    compose = yaml.safe_load((ROOT / "deploy" / "vm-095" / "compose.core.yml").read_text(encoding="utf-8"))
    svc = compose["services"]["argus-v18-corpus"]
    assert svc["profiles"] == ["corpus"] and svc["networks"] == ["argus-v18-sched"]
    assert svc["environment"]["HTTPS_PROXY"] == "http://argus-v18-egress:8888" and svc["read_only"] is True
    assert not any("secret" in v for v in svc["volumes"])
    writable = [v for v in svc["volumes"] if not v.endswith(":ro")]
    assert writable == ["/opt/argus-v18/corpus-staging:/corpus-staging"]
    worker = compose["services"]["argus-v18-worker"]["volumes"]
    assert "/opt/argus-v18/corpus:/corpus:ro" in worker                     # the worker still only reads


def test_the_cli_fetch_stages_only_an_allowlisted_source(tmp_path, monkeypatch):
    import argus.__main__ as cli
    import argus.corpus.staging as st
    monkeypatch.chdir(ROOT)
    with pytest.raises(SystemExit, match="not an allowlisted source"):
        cli.corpus(cli.build_parser().parse_args(["corpus", "fetch", "--source", "nope", "--staging", str(tmp_path)]))
    monkeypatch.delenv("ARGUS_CORPUS_STAGING_DIR", raising=False)
    with pytest.raises(SystemExit, match="needs --staging"):
        cli.corpus(cli.build_parser().parse_args(["corpus", "fetch", "--source", "nginx"]))
    calls = []
    monkeypatch.setattr(st, "fetch_to_staging",
                        lambda src, d, log=print: calls.append((src.name, d)) or {"passages_sha256": "a" * 64})
    cli.corpus(cli.build_parser().parse_args(["corpus", "fetch", "--source", "nginx", "--staging", str(tmp_path)]))
    assert calls == [("nginx", tmp_path)]
