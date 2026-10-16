"""T-0044 / ACR-0015: hybrid runbook retrieval (BM25 + vectors) in a local Weaviate behind `KnowledgePort`.

Weaviate only RANKS: the passage text always comes from the local runbook library (matched by its SHA-256), so a cited
passage stays traceable to the library commit, and a stale index entry is skipped. Any failure (embeddings, Weaviate,
an empty or stale index) falls back to TF-IDF: recall never blocks an investigation. `tfidf` stays the default.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import httpx
import pytest
import yaml

from argus.adapters.outbound.config_adapters import TfidfRunbooks
from argus.adapters.outbound.rag import (HashingEmbeddings, HybridRunbooks, OpenAIEmbeddings, WeaviateIndex,
                                         passage_uuid)
from argus.infrastructure.wiring import Settings, make_knowledge

ROOT = Path(__file__).resolve().parents[1]
LIB = str(ROOT / "argus" / "runbooks")


@pytest.fixture(scope="module")
def tfidf():
    return TfidfRunbooks(LIB)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class FakeIndex:
    """What HybridRunbooks needs from Weaviate: recreate, upsert, hybrid (no live service)."""

    def __init__(self, hits=None, fail: Exception | None = None):
        self.hits, self.fail, self.objects, self.asked = hits or [], fail, [], []

    def recreate(self):
        self.objects = []

    def upsert(self, objects):
        self.objects.extend(objects)

    def count(self):
        return len(self.objects)

    def hybrid(self, query, vector, alpha, limit, runbook_ids):
        self.asked.append((query, len(vector), alpha, limit, list(runbook_ids or [])))
        if self.fail:
            raise self.fail
        return self.hits[:limit]


def hit(kb, rid, title, score=0.9, stale=False):
    body = next(b for r, _, _, s, b in kb.sections if r == rid and s == title)
    return {"runbook_id": rid, "section": title, "sha256": "0" * 64 if stale else sha(body), "score": score}


# --- embeddings ------------------------------------------------------------------------------------------------------
def test_hashing_embeddings_are_deterministic_unit_vectors_and_keyless():
    e = HashingEmbeddings(dims=64)
    a, b = e.embed(["restart loop OOM", "restart loop OOM"])
    assert a == b and len(a) == 64 and math.isclose(sum(x * x for x in a), 1.0, rel_tol=1e-6)
    assert e.embed(["disk full"])[0] != a


def test_openai_embeddings_batch_and_keep_the_order():
    calls = []

    class Client:
        class embeddings:                                        # noqa: N801 (the OpenAI client's shape)
            @staticmethod
            def create(model, input):
                calls.append((model, list(input)))
                return type("R", (), {"data": [type("D", (), {"index": i, "embedding": [float(len(t))]})()
                                               for i, t in reversed(list(enumerate(input)))]})()

    e = OpenAIEmbeddings(client=Client(), model="text-embedding-3-small", batch=2)
    assert e.embed(["a", "bb", "ccc"]) == [[1.0], [2.0], [3.0]]
    assert calls == [("text-embedding-3-small", ["a", "bb"]), ("text-embedding-3-small", ["ccc"])]


# --- the Weaviate client, on the wire --------------------------------------------------------------------------------
def test_weaviate_index_speaks_schema_batch_and_hybrid_graphql():
    seen = []

    def handler(req: httpx.Request):
        body = json.loads(req.content) if req.content else None
        seen.append((req.method, req.url.path, body))
        if req.url.path == "/v1/graphql":
            return httpx.Response(200, json={"data": {"Get": {"RunbookPassage": [
                {"runbook_id": "RB-002", "section": "Diagnostic workflow", "sha256": "ab", "_additional": {"score": "0.7"}}]}}})
        return httpx.Response(200, json={})

    ix = WeaviateIndex("http://argus-v18-weaviate:8080", "RunbookPassage",
                       client=httpx.Client(transport=httpx.MockTransport(handler), base_url="http://argus-v18-weaviate:8080"))
    ix.recreate()
    ix.upsert([{"id": "u1", "properties": {"runbook_id": "RB-002"}, "vector": [0.1, 0.2]}])
    hits = ix.hybrid('health "check"', [0.5, 0.5], 0.5, 3, ["RB-002", "RB-003"])
    assert hits == [{"runbook_id": "RB-002", "section": "Diagnostic workflow", "sha256": "ab", "score": 0.7}]
    methods = [(m, p) for m, p, _ in seen]
    assert methods[:2] == [("DELETE", "/v1/schema/RunbookPassage"), ("POST", "/v1/schema")]
    schema = seen[1][2]
    assert schema["class"] == "RunbookPassage" and schema["vectorizer"] == "none"
    assert schema["vectorIndexConfig"]["distance"] == "cosine"
    assert {p["name"] for p in schema["properties"]} >= {"runbook_id", "section", "sha256", "text"}
    batch = next(b for m, p, b in seen if p == "/v1/batch/objects")
    assert batch["objects"][0]["class"] == "RunbookPassage" and batch["objects"][0]["vector"] == [0.1, 0.2]
    gql = next(b for m, p, b in seen if p == "/v1/graphql")["query"]
    assert 'hybrid:{query:"health \\"check\\"",alpha:0.5,vector:[0.5, 0.5]}' in gql and "limit:3" in gql
    assert 'operator:ContainsAny,valueText:["RB-002", "RB-003"]' in gql


def test_a_graphql_error_is_raised_not_read_as_no_hits():
    ix = WeaviateIndex("http://w:8080", "RunbookPassage", client=httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"errors": [{"message": "no class"}]})),
        base_url="http://w:8080"))
    with pytest.raises(RuntimeError, match="no class"):
        ix.hybrid("q", [0.1], 0.5, 3, None)


# --- the hybrid retriever ---------------------------------------------------------------------------------------------
def test_weaviate_ranks_but_the_text_comes_from_the_local_library(tfidf):
    ix = FakeIndex([hit(tfidf, "RB-002", "Diagnostic workflow", 0.8), hit(tfidf, "RB-003", "Diagnostic workflow", 0.6)])
    kb = HybridRunbooks(tfidf, HashingEmbeddings(dims=32), ix, alpha=0.4)
    got = kb.search("health_check_failed unhealthy", 3, ["RB-002", "RB-003"])
    assert [(p.runbook_id, p.section) for p in got] == [("RB-002", "Diagnostic workflow"), ("RB-003", "Diagnostic workflow")]
    local = next(b for r, _, _, s, b in tfidf.sections if r == "RB-002" and s == "Diagnostic workflow")
    assert got[0].text == local and got[0].score == 0.8 and got[0].runbook_version not in ("", "?")
    assert ix.asked == [("health_check_failed unhealthy", 32, 0.4, 3, ["RB-002", "RB-003"])]


def test_k_caps_the_answer(tfidf):
    ix = FakeIndex([hit(tfidf, "RB-002", s) for s in ("Diagnostic workflow", "Incident definition", "Scope",
                                                      "Required Argus tools")])
    assert len(HybridRunbooks(tfidf, HashingEmbeddings(dims=8), ix).search("q", 3, ["RB-002"])) == 3


def test_a_stale_index_entry_is_skipped_and_all_stale_falls_back(tfidf):
    ix = FakeIndex([hit(tfidf, "RB-002", "Scope", stale=True), hit(tfidf, "RB-002", "Diagnostic workflow")])
    kb = HybridRunbooks(tfidf, HashingEmbeddings(dims=8), ix)
    assert [p.section for p in kb.search("q", 3, ["RB-002"])] == ["Diagnostic workflow"]
    kb2 = HybridRunbooks(tfidf, HashingEmbeddings(dims=8), FakeIndex([hit(tfidf, "RB-002", "Scope", stale=True)]))
    q = "health check unhealthy"
    assert kb2.search(q, 3, ["RB-002"]) == tfidf.search(q, 3, ["RB-002"]) and kb2.fallbacks == 1


@pytest.mark.parametrize("why", ["embeddings", "weaviate", "empty"])
def test_any_failure_falls_back_to_tfidf_never_raises(tfidf, why):
    class Broken:
        def embed(self, texts):
            raise TimeoutError("embeddings timed out")

    emb = Broken() if why == "embeddings" else HashingEmbeddings(dims=8)
    ix = FakeIndex(fail=ConnectionError("refused")) if why == "weaviate" else FakeIndex([])
    kb = HybridRunbooks(tfidf, emb, ix)
    q = "keeps restarting OOM killed memory limit"
    assert kb.search(q, 3, ["RB-001", "RB-008"]) == tfidf.search(q, 3, ["RB-001", "RB-008"])
    assert kb.fallbacks == 1 and kb.last_fallback


def test_the_library_metadata_is_the_tfidf_one(tfidf):
    kb = HybridRunbooks(tfidf, HashingEmbeddings(dims=8), FakeIndex())
    assert kb.ids == tfidf.ids and kb.pinned_text == tfidf.pinned_text
    assert kb.library_version == tfidf.library_version


def test_index_rebuilds_every_section_with_stable_ids_and_its_hash(tfidf):
    ix = FakeIndex()
    kb = HybridRunbooks(tfidf, HashingEmbeddings(dims=16), ix)
    n = kb.index(batch=50)
    assert n == len(tfidf.sections) == len(ix.objects)
    first = ix.objects[0]
    rid, ver, status, title, body = tfidf.sections[0]
    assert first["id"] == passage_uuid(rid, title, sha(body))
    assert first["properties"] == {"runbook_id": rid, "version": ver, "status": status, "section": title,
                                   "text": body, "sha256": sha(body)}
    assert len(first["vector"]) == 16
    assert kb.index(batch=50) == n and len(ix.objects) == n               # idempotent: a rebuild, not a duplicate


# --- composition root, settings, deployment --------------------------------------------------------------------------
def test_tfidf_stays_the_default(monkeypatch):
    for v in ("ARGUS_RETRIEVAL", "ARGUS_WEAVIATE_URL"):
        monkeypatch.delenv(v, raising=False)
    s = Settings()
    assert (s.retrieval, s.retrieval_alpha, s.weaviate_class, s.embeddings, s.embedding_model) == (
        "tfidf", 0.5, "RunbookPassage", "openai", "text-embedding-3-small")
    assert type(make_knowledge(s)) is TfidfRunbooks


def test_hybrid_is_selected_by_the_setting(monkeypatch):
    monkeypatch.setenv("ARGUS_RETRIEVAL", "hybrid")
    monkeypatch.setenv("ARGUS_WEAVIATE_URL", "http://argus-v18-weaviate:8080")
    monkeypatch.setenv("ARGUS_EMBEDDINGS", "hashing")
    kb = make_knowledge(Settings())
    assert isinstance(kb, HybridRunbooks) and isinstance(kb.embedder, HashingEmbeddings)
    assert kb.index_.url == "http://argus-v18-weaviate:8080" and kb.index_.cls == "RunbookPassage"


def test_hybrid_without_a_weaviate_url_refuses_to_start(monkeypatch):
    monkeypatch.setenv("ARGUS_RETRIEVAL", "hybrid")
    monkeypatch.delenv("ARGUS_WEAVIATE_URL", raising=False)
    with pytest.raises(SystemExit, match="ARGUS_WEAVIATE_URL"):
        make_knowledge(Settings())


def test_an_unknown_retrieval_refuses_to_start(monkeypatch):
    monkeypatch.setenv("ARGUS_RETRIEVAL", "vectors")
    with pytest.raises(SystemExit, match="ARGUS_RETRIEVAL"):
        make_knowledge(Settings())


def test_compose_runs_a_bounded_local_weaviate_and_the_worker_defaults_to_tfidf():
    core = yaml.safe_load((ROOT / "deploy" / "vm-095" / "compose.core.yml").read_text(encoding="utf-8"))["services"]
    w = core["argus-v18-weaviate"]
    assert w["image"].startswith("semitechnologies/weaviate:1.") and w["container_name"] == "argus-v18-weaviate"
    assert w["mem_limit"] == "512m" and w["memswap_limit"] == "512m" and str(w["cpus"]) == "0.5"
    assert w["networks"] == ["argus-v18-core"] and "ports" not in w           # reached by the worker only
    env = w["environment"]
    assert env["DEFAULT_VECTORIZER_MODULE"] == "none" and env["ENABLE_API_BASED_MODULES"] == "false"
    assert env["ENABLE_MODULES"] == "" and env["PERSISTENCE_LSM_ACCESS_STRATEGY"] == "pread"
    wenv = core["argus-v18-worker"]["environment"]
    assert wenv["ARGUS_RETRIEVAL"] == "${ARGUS_RETRIEVAL:-tfidf}"
    assert wenv["ARGUS_WEAVIATE_URL"] == "http://argus-v18-weaviate:8080"
    assert "argus-v18-weaviate" not in core["argus-v18-worker"].get("depends_on", {})   # fail-open: TF-IDF without it


def test_the_cli_has_runbooks_index_and_search():
    from argus.__main__ import build_parser
    p = build_parser()
    assert p.parse_args(["runbooks", "index"]).runbooks_cmd == "index"
    a = p.parse_args(["runbooks", "search", "disk full", "--k", "5", "--runbooks", "RB-005,RB-019"])
    assert (a.runbooks_cmd, a.query, a.k, a.runbooks) == ("search", "disk full", 5, "RB-005,RB-019")
