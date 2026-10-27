"""T-0056 (ACR-0034): the corpus's converters, Weaviate client, embeddings, wiring and CLI paths. No network: HTTP is
a mock transport, the embeddings client is a fake."""
from __future__ import annotations

import io
import json
import tarfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import yaml

from argus.corpus import bundle, convert, fetch, sources
from argus.corpus.retrieval import (HashingEmbeddings, HybridReference, OpenAIEmbeddings, ReferenceCorpus,
                                    WeaviateIndex, object_uuid)
from test_t0056_reference_corpus import SOURCES, _source, _tar

ROOT = Path(__file__).resolve().parents[1]


# --- converters ----------------------------------------------------------------------------------------------------
def test_markdown_drops_hugo_shortcodes():
    out = convert.to_text("markdown", "# Run\n{{< tabs >}}Use `docker run`.{{< /tabs >}}")
    assert "{{" not in out and "docker run" in out


def test_rst_titles_become_headings_and_roles_keep_their_text():
    out = convert.to_text("rst", ".. _label:\n\nOut of memory\n=============\n\nSee :ref:`cgroup v2 <cgroup-v2>` and "
                                 "``oom_score_adj``.\n\n.. note::\n   kept\n")
    assert "## Out of memory" in out and "cgroup v2" in out and "_label" not in out and "`oom_score_adj`" in out


def test_roff_man_pages_become_text_with_headings():
    page = ('.\\" a comment\n.TH SYSTEMCTL 1 2024\n.SH NAME\nsystemctl \\- control systemd\n.SH DESCRIPTION\n'
            '.B systemctl\nmay be used to \\fBintrospect\\fR units.\n.PP\n.IP\nmore\n.br\n')
    out = convert.to_text("roff", page)
    assert out.startswith("# SYSTEMCTL 1") and "## Name" in out and "## Description" in out
    assert "systemctl - control systemd" in out and "introspect units" in out and "comment" not in out


def test_docbook_and_xml_keep_titles_and_text_and_decode_entities():
    xml = ("<!-- hidden note --><refentry><refnamediv><refname>journalctl</refname>"
           "<refpurpose>Print log entries</refpurpose></refnamediv><refsect1><title>Options</title>"
           "<para>Use <option>-u</option> &lt;unit&gt; &amp; more.</para></refsect1></refentry>")
    out = convert.to_text("docbook", xml)
    assert "## journalctl" in out and "## Options" in out and "-u <unit> & more." in out and "hidden" not in out


def test_openapi_gives_one_section_per_operation():
    spec = yaml.safe_dump({"info": {"title": "Docker Engine API"}, "paths": {"/containers/{id}/restart": {
        "post": {"summary": "Restart a container", "description": "Restarts it.",
                 "parameters": [{"name": "t", "in": "query", "description": "seconds to wait"}]},
        "parameters": ["not an operation"]}, "/bad": "nope"}})
    out = convert.to_text("openapi", spec)
    assert out.startswith("# Docker Engine API") and "## POST /containers/{id}/restart" in out
    assert "Restart a container" in out and "parameter `t` (query): seconds to wait" in out
    assert convert.to_text("openapi", "key: [unclosed") == ""


def test_file_formats_are_chosen_by_extension_within_the_source():
    src = _source(formats=("markdown", "roff", "docbook"))
    assert bundle._format("x/man/man1/ls.1", src) == "roff"
    assert bundle._format("x/doc/a.sgml", src) == "docbook"
    assert bundle._format("x/doc/a.md.in", src) == "markdown"
    assert bundle._format("x/doc/a.txt", src) == "markdown"                  # unknown: the source's first format
    assert bundle._url("demo-1/docs/guide/index.md", src) == "https://docs.demo.test/guide"
    assert bundle._url("demo-1/docs/a.md", replace(src, url_style="file")) == "https://docs.demo.test/a.md"


# --- sources and fetch edge cases -----------------------------------------------------------------------------------
def _write(tmp_path, rows):
    p = tmp_path / "s.yaml"
    p.write_text(yaml.safe_dump({"sources": rows}), encoding="utf-8")
    return p


@pytest.mark.parametrize("bad", [
    {"licence": ""}, {"formats": ["pdf"]}, {"max_member_bytes": 0}, {"url_style": "web"},
    {"url_base": "http://docs.example/"},
])
def test_more_refused_sources(tmp_path, bad):
    row = yaml.safe_load(SOURCES.read_text(encoding="utf-8"))["sources"][0]
    with pytest.raises(ValueError):
        sources.load(_write(tmp_path, [{**row, **bad}]))


def test_a_source_listed_twice_is_refused(tmp_path):
    row = yaml.safe_load(SOURCES.read_text(encoding="utf-8"))["sources"][0]
    with pytest.raises(ValueError, match="twice"):
        sources.load(_write(tmp_path, [row, row]))


def test_fetch_refuses_an_error_status_and_a_redirect_loop():
    with pytest.raises(fetch.FetchRefused, match="HTTP 404"):
        fetch.fetch_archive(_source(), httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404))))
    loop = httpx.MockTransport(lambda r: httpx.Response(302, headers={"location": str(r.url)}))
    with pytest.raises(fetch.FetchRefused, match="too many redirects"):
        fetch.fetch_archive(_source(), httpx.Client(transport=loop))
    with pytest.raises(fetch.FetchRefused, match="not allowlisted"):
        fetch.fetch_archive(_source(archive_url="http://github.com/demo/docs/archive/v1.0.tar.gz"),
                            httpx.Client(transport=loop))


def test_excluded_members_are_not_read():
    data = _tar({"d-1/docs/a.md": "# A", "d-1/docs/release-1.md": "# R"})
    names = [n for n, _ in fetch.members(data, _source(exclude=("*/release-*",)))]
    assert names == ["d-1/docs/a.md"]


# --- bundle edge cases -----------------------------------------------------------------------------------------------
def test_max_passages_truncates_and_is_reported(tmp_path):
    files = {f"docs-1.0/docs/p{i}.md": f"# P{i}\n\nParagraph number {i} about container networking.\n"
             for i in range(5)}
    m = bundle.build([_source(max_passages=2)], tmp_path / "b", fetcher=lambda s: _tar(files))
    assert m["sources"][0]["passages"] == 2 and m["sources"][0]["truncated"] is True


def test_an_unreadable_bundle_an_unknown_format_or_a_changed_file_is_refused(tmp_path):
    with pytest.raises(bundle.BundleRefused, match="unreadable"):
        bundle.verify(tmp_path / "missing")
    out = tmp_path / "b"
    bundle.build([_source()], out, fetcher=lambda s: _tar({"docs-1.0/docs/a.md": "# A\n\nThe daemon socket path.\n"}))
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    (out / "manifest.json").write_text(json.dumps({**manifest, "format": 99}), encoding="utf-8")
    with pytest.raises(bundle.BundleRefused, match="format"):
        bundle.verify(out)
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with (out / "passages.jsonl").open("a", encoding="utf-8") as f:
        f.write("\n")
    with pytest.raises(bundle.BundleRefused, match="manifest"):
        bundle.verify(out)


def test_install_replaces_a_previous_bundle_in_place(tmp_path):
    out = tmp_path / "b"
    bundle.build([_source()], out, fetcher=lambda s: _tar({"docs-1.0/docs/a.md": "# A\n\nThe daemon socket path.\n"}))
    bundle.install(out, out)                                             # installing into the bundle's own folder
    assert ReferenceCorpus(out).count() == 1


# --- retrieval: Weaviate client, embeddings, hybrid index -----------------------------------------------------------
class _Weaviate:
    def __init__(self, hits=None, errors=None, query_errors=None):
        self.calls, self.objects = [], []
        self.hits, self.errors, self.query_errors = hits or [], errors, query_errors

    def __call__(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content) if req.content else None
        self.calls.append((req.method, req.url.path, body))
        if req.method == "DELETE":
            return httpx.Response(404)
        if req.url.path == "/v1/batch/objects":
            self.objects += body["objects"]
            return httpx.Response(200, json=[{"result": {"errors": self.errors}}] if self.errors else [{}])
        if req.url.path == "/v1/graphql":
            if self.query_errors:
                return httpx.Response(200, json={"errors": [{"message": self.query_errors}]})
            return httpx.Response(200, json={"data": {"Get": {"ReferencePassage": self.hits}}})
        return httpx.Response(200, json={})


def _installed(tmp_path) -> ReferenceCorpus:
    out = tmp_path / "b"
    bundle.build([_source()], out, fetcher=lambda s: _tar({
        "docs-1.0/docs/oom.md": "# OOM\n\nA container killed by the OOM killer exits with code 137.\n",
        "docs-1.0/docs/net.md": "# Networks\n\nA container on another network cannot resolve the name.\n"}))
    bundle.install(out, tmp_path / "d")
    return ReferenceCorpus(tmp_path / "d")


def test_the_weaviate_client_builds_the_class_upserts_and_queries(tmp_path):
    corpus = _installed(tmp_path)
    first = next(corpus.all())[0]
    fake = _Weaviate(hits=[{"passage_id": first["id"], "sha256": first["sha256"], "_additional": {"score": "0.5"}}])
    index = WeaviateIndex("http://weaviate.test", client=httpx.Client(base_url="http://weaviate.test",
                                                                       transport=httpx.MockTransport(fake)))
    hybrid = HybridReference(corpus, HashingEmbeddings(8), index)
    assert hybrid.index(batch=1) == 2
    assert [c[0] for c in fake.calls[:2]] == ["DELETE", "POST"] and fake.calls[1][2]["vectorizer"] == "none"
    assert {o["id"] for o in fake.objects} == {object_uuid(r["id"], r["sha256"]) for rows in corpus.all() for r in rows}
    hits = hybrid.search("oom 137", 2)
    assert hits[0]["id"] == first["id"] and hits[0]["text"] == first["text"] and hybrid.fallbacks == 0


def test_weaviate_errors_are_raised_not_read_as_no_hits(tmp_path):
    def client(fake):
        return WeaviateIndex("http://w", client=httpx.Client(base_url="http://w", transport=httpx.MockTransport(fake)))
    with pytest.raises(RuntimeError, match="batch"):
        client(_Weaviate(errors=[{"message": "bad"}])).upsert([{"id": "x"}])
    with pytest.raises(RuntimeError, match="query"):
        client(_Weaviate(query_errors="syntax")).hybrid("q", [0.0], 0.5, 3)
    corpus = _installed(tmp_path)
    hybrid = HybridReference(corpus, HashingEmbeddings(8), client(_Weaviate(query_errors="syntax")))
    assert hybrid.search("oom 137", 1) and hybrid.fallbacks == 1 and "RuntimeError" in hybrid.last_fallback


def test_openai_embeddings_are_batched_and_keep_their_order():
    class Client:
        def __init__(self):
            self.batches = []
            self.embeddings = self

        def create(self, model, input):
            self.batches.append(list(input))
            data = [SimpleNamespace(index=i, embedding=[float(len(t))]) for i, t in enumerate(input)]
            return SimpleNamespace(data=list(reversed(data)))
    c = Client()
    out = OpenAIEmbeddings(client=c, batch=2).embed(["a", "bb", "ccc"])
    assert out == [[1.0], [2.0], [3.0]] and c.batches == [["a", "bb"], ["ccc"]]


def test_hashing_embeddings_are_deterministic_unit_vectors():
    a, b = HashingEmbeddings(16).embed(["oom killer", "oom killer"])
    assert a == b and abs(sum(x * x for x in a) - 1.0) < 1e-9


def test_a_query_without_words_and_a_missing_corpus():
    with pytest.raises(FileNotFoundError):
        ReferenceCorpus("does-not-exist")


def test_a_query_without_words_finds_nothing(tmp_path):
    assert _installed(tmp_path).search("!!", 3) == []


# --- wiring ----------------------------------------------------------------------------------------------------------
def test_the_wiring_reads_no_corpus_without_a_bundle_and_keywords_by_default(tmp_path, monkeypatch):
    from argus.infrastructure.wiring import Settings, make_reference
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert make_reference(Settings(corpus_dir="")) is None
    assert make_reference(Settings(corpus_dir=str(tmp_path / "none"))) is None
    _installed(tmp_path)
    s = Settings(corpus_dir=str(tmp_path / "d"), secrets_dir=tmp_path / "secrets")
    assert isinstance(make_reference(s), ReferenceCorpus)
    assert isinstance(make_reference(replace(s, corpus_retrieval="hybrid")), ReferenceCorpus)   # no key: keywords


def test_the_wiring_builds_the_hybrid_path_with_the_worker_key(tmp_path, monkeypatch):
    import argus.corpus.retrieval as retrieval
    from argus.infrastructure.wiring import Settings, make_reference
    _installed(tmp_path)
    secrets = tmp_path / "secrets"
    secrets.mkdir()
    (secrets / "openai_api_key").write_text("k" * 20, encoding="utf-8")
    s = Settings(corpus_dir=str(tmp_path / "d"), secrets_dir=secrets, corpus_retrieval="hybrid")
    monkeypatch.setattr(retrieval, "OpenAIEmbeddings", lambda key, model: HashingEmbeddings(4))
    assert isinstance(make_reference(s), HybridReference)

    def broken(key, model):
        raise RuntimeError("no client")
    monkeypatch.setattr(retrieval, "OpenAIEmbeddings", broken)
    assert isinstance(make_reference(s), ReferenceCorpus)                 # fail-open


# --- CLI paths ------------------------------------------------------------------------------------------------------
def _cli(*args):
    import argus.__main__ as cli
    return cli.corpus(cli.build_parser().parse_args(["corpus", *args]))


def test_the_cli_refuses_a_tampered_bundle_and_missing_folders(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("ARGUS_CORPUS_DIR", raising=False)
    out = tmp_path / "b"
    bundle.build([_source()], out, fetcher=lambda s: _tar({"docs-1.0/docs/a.md": "# A\n\nThe daemon socket path.\n"}))
    (out / "passages.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(SystemExit, match="REFUSED"):
        _cli("import", str(out), "--dest", str(tmp_path / "d"))
    with pytest.raises(SystemExit, match="--dest"):
        _cli("import", str(out))
    with pytest.raises(SystemExit, match="--dir"):
        _cli("search", "x")
    with pytest.raises(SystemExit, match="no hybrid path"):
        _cli("index", "--dir", str(tmp_path / "empty"))


def test_the_cli_indexes_through_the_hybrid_path(tmp_path, monkeypatch, capsys):
    import argus.infrastructure.wiring as wiring
    _installed(tmp_path)

    class FakeHybrid(HybridReference):
        def __init__(self):
            pass

        def index(self, batch=64, log_line=lambda _: None):
            return 2
    monkeypatch.setattr(wiring, "make_reference", lambda s, hybrid=None: FakeHybrid())
    _cli("index", "--dir", str(tmp_path / "d"))
    assert "indexed 2 passage(s)" in capsys.readouterr().out


def test_the_cli_builds_only_the_named_sources(tmp_path, monkeypatch, capsys):
    raw = yaml.safe_load(SOURCES.read_text(encoding="utf-8"))
    srcs = tmp_path / "sources.yaml"
    srcs.write_text(yaml.safe_dump(raw), encoding="utf-8")
    seen = []

    def fake(source, client=None):
        seen.append(source.name)
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz"):
            pass
        return buf.getvalue()
    monkeypatch.setattr(fetch, "fetch_archive", fake)
    _cli("build", "--sources", str(srcs), "--out", str(tmp_path / "b"), "--only", "nginx,podman")
    assert seen == ["podman", "nginx"] and "0 passage(s)" in capsys.readouterr().out
