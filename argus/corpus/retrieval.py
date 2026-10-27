"""ACR-0034: searching the installed reference corpus.

`ReferenceCorpus`: BM25 keyword search (SQLite FTS5) over `reference.db`, read-only; the fallback and the only path
when no hybrid index is configured. `HybridReference`: BM25 + vectors in a local Weaviate (ACR-0015's design) that
only RANKS: each hit's text is taken from the local bundle and must match the SHA-256 the index stored, else it is
skipped. Both apply the same answer rules: at most PER_SOURCE passages per source, each passage once, official
documentation weighted above text read from a target. Any hybrid failure falls back to the keyword search, counted.
Vectors are computed by Argus (the provider's embeddings endpoint); Weaviate runs no model.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Protocol

import httpx

log = logging.getLogger("argus.corpus")
_WORD = re.compile(r"[a-z0-9_]{2,}")
_NS = uuid.UUID("2f0c7a64-5d1b-4a8e-b0b2-0034c0e5a0f1")             # ACR-0034's namespace for stable object ids
TRUST_WEIGHT = {"official": 1.0, "target": 0.7}


def object_uuid(passage_id: str, sha: str) -> str:
    return str(uuid.uuid5(_NS, f"{passage_id}|{sha}"))


def _apply_rules(rows: list[dict], k: int, per_source: int) -> list[dict]:
    rows = sorted(rows, key=lambda r: -r.get("score", 0.0) * TRUST_WEIGHT.get(r.get("trust", "target"), 0.7))
    out, seen, by_source = [], set(), {}
    for r in rows:
        if r["sha256"] in seen or by_source.get(r["source"], 0) >= per_source:
            continue
        seen.add(r["sha256"])
        by_source[r["source"]] = by_source.get(r["source"], 0) + 1
        out.append(r)
        if len(out) >= k:
            break
    return out


class ReferenceCorpus:
    PER_SOURCE = 2
    COLUMNS = ("id", "source", "ref", "licence", "trust", "path", "url", "title", "text", "sha256")

    def __init__(self, directory: Path | str):
        path = Path(directory) / "reference.db"
        if not path.is_file():
            raise FileNotFoundError(f"no installed reference corpus at {path}")
        self.path = path
        self.db = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, check_same_thread=False)
        manifest = Path(directory) / "manifest.json"
        self.manifest = json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else {}

    def _row(self, r) -> dict:
        return dict(zip(self.COLUMNS, r))

    def get(self, passage_id: str) -> dict | None:
        r = self.db.execute(f"SELECT {', '.join(self.COLUMNS)} FROM passage WHERE id=?", (passage_id,)).fetchone()
        return self._row(r) if r else None

    def all(self, batch: int = 256):
        cur = self.db.execute(f"SELECT {', '.join(self.COLUMNS)} FROM passage ORDER BY rowid")
        while rows := cur.fetchmany(batch):
            yield [self._row(r) for r in rows]

    def count(self) -> int:
        return int(self.db.execute("SELECT count(*) FROM passage").fetchone()[0])

    def search(self, query: str, k: int) -> list[dict]:
        words = list(dict.fromkeys(_WORD.findall(query.lower())))[:16]
        if not words:
            return []
        match = " OR ".join(f'"{w}"' for w in words)
        cols = ", ".join(f"p.{c}" for c in self.COLUMNS)
        rows = self.db.execute(f"SELECT {cols}, bm25(passage_fts) AS rank FROM passage_fts f "
                               f"JOIN passage p ON p.rowid = f.rowid WHERE passage_fts MATCH ? "
                               f"ORDER BY rank LIMIT ?", (match, max(k * 8, 20))).fetchall()
        hits = [{**self._row(r[:-1]), "score": round(-float(r[-1]), 3)} for r in rows]
        return _apply_rules(hits, k, self.PER_SOURCE)


class EmbeddingPort(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashingEmbeddings:
    """Deterministic, keyless vectors (feature hashing): offline tests and smoke runs, never quality."""

    def __init__(self, dims: int = 256):
        self.dims = dims

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            v = [0.0] * self.dims
            for w in _WORD.findall(text.lower()):
                h = int.from_bytes(hashlib.blake2b(w.encode(), digest_size=8).digest(), "big")
                v[h % self.dims] += 1.0 if (h >> 32) & 1 else -1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / n for x in v])
        return out


class OpenAIEmbeddings:
    """The model provider's embeddings endpoint (OpenAI dialect), batched, order kept."""

    def __init__(self, api_key: str | None = None, model: str = "text-embedding-3-small", timeout_s: float = 10.0,
                 batch: int = 96, client: Any = None):
        if client is None:
            from openai import OpenAI
            client = OpenAI(api_key=api_key, timeout=timeout_s, max_retries=1)
        self.client, self.model, self.batch = client, model, batch

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch):
            r = self.client.embeddings.create(model=self.model, input=texts[i:i + self.batch])
            out.extend(list(d.embedding) for d in sorted(r.data, key=lambda d: d.index))
        return out


class WeaviateIndex:
    """A thin REST/GraphQL client for the reference passages' class in the local Weaviate (no credentials)."""

    PROPERTIES = (("passage_id", "field"), ("source", "field"), ("sha256", "field"), ("text", "word"))

    def __init__(self, url: str, cls: str = "ReferencePassage", timeout_s: float = 5.0,
                 client: httpx.Client | None = None):
        self.cls = cls
        self.http = client or httpx.Client(base_url=url.rstrip("/"), timeout=timeout_s)

    def _call(self, method: str, path: str, body: Any = None) -> Any:
        r = self.http.request(method, path, json=body)
        if method == "DELETE" and r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json() if r.content else None

    def recreate(self) -> None:
        """The index is derived from the installed bundle: a rebuild drops the class and creates it again."""
        self._call("DELETE", f"/v1/schema/{self.cls}")
        self._call("POST", "/v1/schema", {
            "class": self.cls, "vectorizer": "none", "vectorIndexConfig": {"distance": "cosine"},
            "properties": [{"name": n, "dataType": ["text"], "tokenization": t} for n, t in self.PROPERTIES]})

    def upsert(self, objects: list[dict]) -> None:
        r = self._call("POST", "/v1/batch/objects", {"objects": [{"class": self.cls, **o} for o in objects]})
        errors = [x["result"]["errors"] for x in (r or []) if isinstance(x, dict) and (x.get("result") or {}).get("errors")]
        if errors:
            raise RuntimeError(f"weaviate batch: {json.dumps(errors[0])[:300]}")

    def hybrid(self, query: str, vector: list[float], alpha: float, limit: int) -> list[dict]:
        g = ("{Get{%s(hybrid:{query:%s,alpha:%s,vector:%s},limit:%d){passage_id sha256 _additional{score}}}}"
             % (self.cls, json.dumps(query), alpha, json.dumps(vector), limit))
        r = self._call("POST", "/v1/graphql", {"query": g})
        if r.get("errors"):
            raise RuntimeError(f"weaviate query: {r['errors'][0].get('message', r['errors'][0])}")
        rows = ((r.get("data") or {}).get("Get") or {}).get(self.cls) or []
        return [{"passage_id": x["passage_id"], "sha256": x["sha256"],
                 "score": float((x.get("_additional") or {}).get("score") or 0)} for x in rows]


class HybridReference:
    def __init__(self, corpus: ReferenceCorpus, embedder: EmbeddingPort, index: Any, alpha: float = 0.5):
        self.corpus, self.embedder, self.index_, self.alpha = corpus, embedder, index, alpha
        self.fallbacks, self.last_fallback = 0, ""

    def _fallback(self, why: str, query: str, k: int) -> list[dict]:
        self.fallbacks += 1
        if why != self.last_fallback:
            log.warning("hybrid reference search fell back to keywords: %s", why)
        self.last_fallback = why
        return self.corpus.search(query, k)

    def search(self, query: str, k: int) -> list[dict]:
        try:
            hits = self.index_.hybrid(query, self.embedder.embed([query])[0], self.alpha, max(k * 4, 12))
        except Exception as e:                                       # noqa: BLE001 (fail-open by design)
            return self._fallback(f"{type(e).__name__}: {str(e)[:200]}", query, k)
        rows = []
        for h in hits:
            local = self.corpus.get(h["passage_id"])
            if local is None or local["sha256"] != h["sha256"]:
                continue                                             # unknown or stale: the bundle is the truth
            rows.append({**local, "score": round(h["score"], 3)})
        out = _apply_rules(rows, k, ReferenceCorpus.PER_SOURCE)
        return out or self._fallback("no current passage in the index", query, k)

    def index(self, batch: int = 64, log_line=lambda _: None) -> int:
        """Rebuild the class from the installed bundle (idempotent): every passage, its vector, its hash."""
        self.index_.recreate()
        n = 0
        for rows in self.corpus.all(batch):
            vectors = self.embedder.embed([f"{r['title']}\n{r['text']}" for r in rows])
            self.index_.upsert([{"id": object_uuid(r["id"], r["sha256"]), "vector": v,
                                 "properties": {"passage_id": r["id"], "source": r["source"], "sha256": r["sha256"],
                                                "text": r["text"]}} for r, v in zip(rows, vectors)])
            n += len(rows)
            log_line(f"indexed {n}")
        return n
