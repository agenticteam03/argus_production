"""ACR-0034: a bundle is the corpus as shipped: passages with provenance, the quarantine, and a manifest of hashes.

`build` (offline: fetch, sanitise, convert, chunk, scan) writes `passages.jsonl`, `quarantine.jsonl` and
`manifest.json`. `verify` refuses a bundle whose files or passages do not match their SHA-256. `install` verifies,
copies the files and builds `reference.db` (SQLite FTS5) next to them: the keyword index the worker reads, and the
text that hybrid ranking must match by hash. A passage is at most MAX_PASSAGE_CHARS; its id is
`ref-<source>-<n>` in path order, stable for a pinned ref.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from argus.corpus import convert, fetch, sanitize, scan
from argus.corpus.sources import Source

MAX_PASSAGE_CHARS = 1800
MIN_BODY_CHARS = 20
BUNDLE_FORMAT = 1
_EXT = {".md": "markdown", ".in": "markdown", ".rst": "rst", ".xml": "docbook", ".sgml": "docbook",
        ".yaml": "openapi", ".yml": "openapi"}


class BundleRefused(RuntimeError):
    pass


def sha256(text: str | bytes) -> str:
    return hashlib.sha256(text.encode("utf-8") if isinstance(text, str) else text).hexdigest()


def _format(path: str, source: Source) -> str:
    suffix = os.path.splitext(path)[1].lower()
    if suffix[1:].isdigit():
        return "roff"
    fmt = _EXT.get(suffix)
    return fmt if fmt in source.formats else source.formats[0]


def _rel(member: str, source: Source) -> str:
    rel = member.split("/", 1)[1] if "/" in member else member        # the archive's top folder
    if source.strip_prefix and rel.startswith(source.strip_prefix):
        rel = rel[len(source.strip_prefix):]
    return rel


def _url(member: str, source: Source) -> str:
    rel = _rel(member, source)
    if source.url_style == "page":
        rel = os.path.splitext(rel)[0]
        rel = rel[:-len("/index")] if rel.endswith("/index") else rel
    return source.url_base + rel


def chunks(text: str, fallback_title: str) -> list[tuple[str, str]]:
    """(title, passage) pairs: one per heading section, split on paragraphs (then words) to stay under the cap."""
    title, heading, body, out = fallback_title, "", [], []

    def flush():
        paragraphs = [p.strip() for p in "\n".join(body).split("\n\n") if p.strip()]
        head = f"{title} — {heading}" if heading and heading != title else title
        room = MAX_PASSAGE_CHARS - len(head) - 1
        piece = ""
        for p in paragraphs:
            while len(p) > room:                             # one over-long paragraph: hard split on words
                cut = p.rfind(" ", 0, room)
                cut = cut if cut > room // 2 else room
                if piece:
                    out.append((head, piece))
                    piece = ""
                out.append((head, p[:cut].strip()))
                p = p[cut:].strip()
            if piece and len(piece) + 2 + len(p) > room:
                out.append((head, piece))
                piece = ""
            piece = f"{piece}\n\n{p}" if piece else p
        if piece:
            out.append((head, piece))
        body.clear()

    first = True
    for line in text.splitlines():
        if line.startswith("#"):
            flush()
            name = line.lstrip("#").strip()
            if first and line.startswith("# "):
                title, heading = name or title, ""
            else:
                heading = name
            first = False
            continue
        body.append(line)
    flush()
    return [(h, f"{h}\n{b}"[:MAX_PASSAGE_CHARS]) for h, b in out if len(b) >= MIN_BODY_CHARS]


def _write_jsonl(path: Path, rows: list[dict]) -> str:
    data = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows).encode("utf-8")
    path.write_bytes(data)
    return sha256(data)


def build(srcs: list[Source], out: Path, fetcher: Callable[[Source], bytes] | None = None,
          log: Callable[[str], None] = lambda _: None) -> dict:
    fetcher = fetcher or (lambda s: fetch.fetch_archive(s))
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    passages, quarantined, summary = [], [], []
    for source in srcs:
        archive = fetcher(source)
        n = q = 0
        truncated = False
        for member, raw in fetch.members(archive, source):
            text = convert.to_text(_format(member, source), sanitize.clean(raw))
            stem = os.path.splitext(os.path.basename(member))[0]
            for title, passage in chunks(sanitize.clean(text), stem):
                row = {"source": source.name, "ref": source.ref, "licence": source.licence, "trust": source.trust,
                       "path": _rel(member, source), "url": _url(member, source), "title": title,
                       "text": passage, "sha256": sha256(passage)}
                found = scan.findings(passage)
                if found:
                    quarantined.append({**row, "findings": found})
                    q += 1
                    continue
                if n >= source.max_passages:
                    truncated = True
                    break
                n += 1
                passages.append({"id": f"ref-{source.name}-{n}", **row})
        summary.append({"name": source.name, "ref": source.ref, "licence": source.licence,
                        "archive_url": source.archive_url, "archive_sha256": sha256(archive),
                        "passages": n, "quarantined": q, "truncated": truncated})
        log(f"{source.name}: {n} passage(s), {q} quarantined{' (truncated)' if truncated else ''}")
    manifest = {"format": BUNDLE_FORMAT, "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "sources": summary, "passages_sha256": _write_jsonl(out / "passages.jsonl", passages),
                "quarantine_sha256": _write_jsonl(out / "quarantine.jsonl", quarantined)}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def verify(directory: Path) -> tuple[dict, list[dict]]:
    """The manifest and its passages, or BundleRefused: a changed file, a changed passage or a repeated id."""
    d = Path(directory)
    try:
        manifest = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
        data = (d / "passages.jsonl").read_bytes()
    except (OSError, ValueError) as e:
        raise BundleRefused(f"unreadable bundle: {e}") from e
    if manifest.get("format") != BUNDLE_FORMAT:
        raise BundleRefused("unknown bundle format")
    if sha256(data) != manifest.get("passages_sha256"):
        raise BundleRefused("passages.jsonl does not match the manifest's SHA-256")
    rows, seen = [], set()
    for line in data.decode("utf-8").splitlines():
        row = json.loads(line)
        if sha256(row["text"]) != row["sha256"] or row["id"] in seen or len(row["text"]) > MAX_PASSAGE_CHARS:
            raise BundleRefused(f"passage {row.get('id')} does not match its hash, repeats, or is too long")
        seen.add(row["id"])
        rows.append(row)
    return manifest, rows


def install(src: Path, dest: Path) -> dict:
    """Verify `src`, then replace `dest`'s bundle and keyword index (built aside, renamed into place)."""
    manifest, rows = verify(src)
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    tmp = dest / "reference.db.tmp"
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    db.executescript("""
        CREATE TABLE passage (id TEXT PRIMARY KEY, source TEXT, ref TEXT, licence TEXT, trust TEXT, path TEXT,
                              url TEXT, title TEXT, text TEXT, sha256 TEXT);
        CREATE VIRTUAL TABLE passage_fts USING fts5(title, text, content='passage', content_rowid='rowid',
                                                   tokenize='porter unicode61');""")
    db.executemany("INSERT INTO passage VALUES (?,?,?,?,?,?,?,?,?,?)",
                   [(r["id"], r["source"], r["ref"], r["licence"], r["trust"], r["path"], r["url"], r["title"],
                     r["text"], r["sha256"]) for r in rows])
    db.execute("INSERT INTO passage_fts(rowid, title, text) SELECT rowid, title, text FROM passage")
    db.commit()
    db.close()
    for name in ("passages.jsonl", "quarantine.jsonl", "manifest.json"):
        if (Path(src) / name).resolve() != (dest / name).resolve():
            shutil.copyfile(Path(src) / name, dest / name)
    os.replace(tmp, dest / "reference.db")
    return manifest
