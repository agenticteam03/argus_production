"""T-0044 / ACR-0015: hybrid runbook retrieval (BM25 + vectors) in a local Weaviate, behind `KnowledgePort`.

Weaviate only RANKS. The corpus is `TfidfRunbooks`'s (ids from metadata, one `##` section per passage, over-long
sections refused), and the text of every returned passage comes from that local library, matched by the SHA-256 the
index stored: a cited passage stays traceable to the library commit, and a stale index entry is skipped. Any failure
(embeddings, Weaviate, an empty or wholly stale index) falls back to TF-IDF, counted and logged: recall never blocks an
investigation. Vectors are computed by Argus (the model provider's embeddings); Weaviate runs no vectorizer module.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import uuid
from typing import Any, Protocol

import httpx

from argus.domain.model import Passage

log = logging.getLogger("argus.rag")
_NS = uuid.UUID("6d1c7c1e-0a44-4b2a-9a51-7e2a3f0c0044")      # T-0044's namespace for stable passage ids
_TOKEN = re.compile(r"[a-z0-9_]+")


def passage_uuid(runbook_id: str, section: str, sha256: str) -> str:
    """The same passage gets the same id at every rebuild."""
    return str(uuid.uuid5(_NS, f"{runbook_id}|{section}|{sha256}"))


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EmbeddingPort(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbeddings:
    """Deterministic, keyless vectors (feature hashing of the words): offline tests and smoke runs, never quality."""

    def __init__(self, dims: int = 256):
        self.dims = dims

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            v = [0.0] * self.dims
            for w in _TOKEN.findall(text.lower()):
                h = int.from_bytes(hashlib.blake2b(w.encode(), digest_size=8).digest(), "big")
                v[h % self.dims] += 1.0 if (h >> 32) & 1 else -1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out


class OpenAIEmbeddings:
    """The model provider's embeddings endpoint (OpenAI dialect), batched, order kept."""

    def __init__(self, api_key: str | None = None, model: str = "text-embedding-3-small", base_url: str | None = None,
                 timeout_s: float = 10.0, batch: int = 96, client: Any = None):
        if client is None:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, base_url=base_url or None, timeout=timeout_s, max_retries=1)
        self.client, self.model, self.batch = client, model, batch

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch):
            r = self.client.embeddings.create(model=self.model, input=texts[i:i + self.batch])
            out.extend(list(d.embedding) for d in sorted(r.data, key=lambda d: d.index))
        return out


class WeaviateIndex:
    """A thin REST/GraphQL client for one class of runbook passages in the local Weaviate (no credentials)."""

    PROPERTIES = (("runbook_id", "field"), ("version", "field"), ("status", "field"), ("section", "field"),
                  ("sha256", "field"), ("text", "word"))

    def __init__(self, url: str, cls: str = "RunbookPassage", timeout_s: float = 5.0, client: httpx.Client | None = None):
        self.url, self.cls = url.rstrip("/"), cls
        self.http = client or httpx.Client(base_url=self.url, timeout=timeout_s)

    def _call(self, method: str, path: str, body: Any = None) -> Any:
        r = self.http.request(method, path, json=body)
        if method == "DELETE" and r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json() if r.content else None

    def recreate(self) -> None:
        """The index is derived from the library: a rebuild drops the class and creates it again."""
        self._call("DELETE", f"/v1/schema/{self.cls}")
        self._call("POST", "/v1/schema", {
            "class": self.cls, "vectorizer": "none", "vectorIndexConfig": {"distance": "cosine"},
            "properties": [{"name": n, "dataType": ["text"], "tokenization": t} for n, t in self.PROPERTIES]})

    def upsert(self, objects: list[dict]) -> None:
        r = self._call("POST", "/v1/batch/objects", {"objects": [{"class": self.cls, **o} for o in objects]})
        errors = [x["result"]["errors"] for x in (r or []) if isinstance(x, dict) and (x.get("result") or {}).get("errors")]
        if errors:
            raise RuntimeError(f"weaviate batch: {json.dumps(errors[0])[:300]}")

    def count(self) -> int:
        r = self._call("POST", "/v1/graphql", {"query": "{Aggregate{%s{meta{count}}}}" % self.cls})
        return int(((r.get("data") or {}).get("Aggregate") or {}).get(self.cls, [{}])[0].get("meta", {}).get("count", 0))

    def hybrid(self, query: str, vector: list[float], alpha: float, limit: int,
               runbook_ids: list[str] | None) -> list[dict]:
        where = (",where:{path:[\"runbook_id\"],operator:ContainsAny,valueText:%s}" % json.dumps(list(runbook_ids))
                 if runbook_ids else "")
        g = ("{Get{%s(hybrid:{query:%s,alpha:%s,vector:%s},limit:%d%s)"
             "{runbook_id section sha256 _additional{score}}}}"
             % (self.cls, json.dumps(query), alpha, json.dumps(vector), limit, where))
        r = self._call("POST", "/v1/graphql", {"query": g})
        if r.get("errors"):
            raise RuntimeError(f"weaviate query: {r['errors'][0].get('message', r['errors'][0])}")
        rows = ((r.get("data") or {}).get("Get") or {}).get(self.cls) or []
        return [{"runbook_id": x["runbook_id"], "section": x["section"], "sha256": x["sha256"],
                 "score": float((x.get("_additional") or {}).get("score") or 0)} for x in rows]


class HybridRunbooks:
    """`KnowledgePort` over a local Weaviate; the library (ids, pinned conventions, version) and the fallback are the
    TF-IDF ones."""

    def __init__(self, tfidf: Any, embedder: EmbeddingPort, index: Any, alpha: float = 0.5, skip_titles: bool = False):
        self.tfidf, self.embedder, self.index_, self.alpha = tfidf, embedder, index, alpha
        # step 3: a runbook's title stub ("RB-001 — Container OOM restart loop") matches a class name almost exactly
        # but tells the model nothing; skip_titles over-fetches by the number of runbooks and drops them
        self.skip_titles = skip_titles
        self.ids, self.pinned_text, self.library_version = tfidf.ids, tfidf.pinned_text, tfidf.library_version
        self._local = {(rid, sec, _sha(body)): (rid, ver, st, sec, body) for rid, ver, st, sec, body in tfidf.sections}
        self.fallbacks, self.last_fallback = 0, ""

    def _fallback(self, why: str, query: str, k: int, runbook_ids: list[str] | None) -> list[Passage]:
        self.fallbacks += 1
        if why != self.last_fallback:
            log.warning("hybrid recall fell back to TF-IDF: %s", why)
        self.last_fallback = why
        return self.tfidf.search(query, k, runbook_ids)

    def search(self, query: str, k: int, runbook_ids: list[str] | None = None) -> list[Passage]:
        try:
            vector = self.embedder.embed([query])[0]
            extra = (len(runbook_ids) if runbook_ids else 3) if self.skip_titles else 0
            hits = self.index_.hybrid(query, vector, self.alpha, k + extra, runbook_ids)
        except Exception as e:                                           # noqa: BLE001 (fail-open by design)
            return self._fallback(f"{type(e).__name__}: {str(e)[:200]}", query, k, runbook_ids)
        out = []
        for h in hits:
            local = self._local.get((h["runbook_id"], h["section"], h["sha256"]))
            if local is None or (runbook_ids and local[0] not in runbook_ids):
                continue                                                 # stale entry, or outside the class
            if self.skip_titles and local[3].startswith(f"{local[0]} "):
                continue                                                 # the title stub
            rid, ver, st, sec, body = local
            out.append(Passage(runbook_id=rid, runbook_version=ver, runbook_status=st, section=sec, text=body,
                               score=round(h["score"], 3)))
        if not out:
            return self._fallback("no current passage in the index", query, k, runbook_ids)
        return out[:k]

    def index(self, batch: int = 64) -> int:
        """Rebuild the class from the library (idempotent): every section, its vector, its hash."""
        secs, titles = self.tfidf.sections, getattr(self.tfidf, "titles", {})
        self.index_.recreate()
        for i in range(0, len(secs), batch):
            chunk = secs[i:i + batch]
            # step 3: each section carries its runbook's title, so "Diagnostic workflow" of RB-001 (OOM) and of
            # RB-008 (crash loop) stay apart once the title stubs are skipped
            vectors = self.embedder.embed([f"{rid} {titles.get(rid, '')} — {sec}\n{body}"
                                           for rid, _, _, sec, body in chunk])
            self.index_.upsert([{
                "id": passage_uuid(rid, sec, _sha(body)), "vector": vec,
                "properties": {"runbook_id": rid, "version": ver, "status": st, "section": sec, "text": body,
                               "sha256": _sha(body)}} for (rid, ver, st, sec, body), vec in zip(chunk, vectors)])
        return len(secs)
