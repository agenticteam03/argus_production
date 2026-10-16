"""T-0044 step 3: the retrieval comparison. Each class case gives the recall node's own query (replayed offline with
TF-IDF), its runbook labels and its useful sections (`tests/eval/section_labels.yaml`); a retriever is scored on runbook
recall@3, section hit@3 and section precision@3.

    python -m argus.evaluation.retrieval --cases tests/eval/cases --labels tests/eval/section_labels.yaml > items.jsonl
    python -m argus.evaluation.retrieval ... --score      # the TF-IDF table, locally
    argus runbooks compare < items.jsonl                  # TF-IDF and the hybrid (alpha grid), where Weaviate runs
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Callable

import yaml

from argus.evaluation.cases import Case, load_cases


def load_section_labels(path: Path) -> tuple[list[str], dict[str, list[str]]]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return list(raw.get("working_sections") or []), {k: list(v) for k, v in (raw.get("extra") or {}).items()}


def useful_sections(case: Case, working: list[str], extra: dict[str, list[str]]) -> set[str]:
    runbooks = list(case.label.runbooks) + list(extra.get(case.id, []))
    return {f"{rid}#{sec}" for rid in runbooks for sec in working}


class _Spy:
    """The recall node's KnowledgePort, recording its first search (the recall query) and answering with TF-IDF."""

    def __init__(self, inner):
        self.inner, self.first = inner, None

    def search(self, query, k, runbook_ids=None):
        if self.first is None:
            self.first = (query, list(runbook_ids or []))
        return self.inner.search(query, k, runbook_ids)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def capture_queries(cases: list[Case], workdir: Path, labels: Path | None = None) -> list[dict]:
    """Replay each class case without a model and keep the query its recall node sent."""
    from argus.evaluation import replay
    from argus.infrastructure import wiring
    working, extra = load_section_labels(labels or Path("tests/eval/section_labels.yaml"))
    real = wiring.make_knowledge
    items = []
    for case in cases:
        if case.category != "class" or not case.label.runbooks:
            continue
        spy: dict = {}

        def make(s, _spy=spy):
            _spy["kb"] = _Spy(real(s))
            return _spy["kb"]
        wiring.make_knowledge = make
        try:
            replay.run_case(case, workdir)
        finally:
            wiring.make_knowledge = real
        first = spy["kb"].first if "kb" in spy else None
        if first is None:
            continue
        items.append({"case": case.id, "class": case.label.incident_class, "query": first[0],
                      "runbook_ids": first[1], "runbooks": list(case.label.runbooks),
                      "useful": sorted(useful_sections(case, working, extra))})
    return items


def score(search: Callable[[dict], list], items: list[dict], k: int = 3) -> dict:
    rows = []
    for it in items:
        got = list(search(it))[:k]
        found = {p.runbook_id for p in got}
        useful = set(it["useful"])
        hits = sum(f"{p.runbook_id}#{p.section}" in useful for p in got)
        rows.append((it["class"], sum(r in found for r in it["runbooks"]) / max(len(it["runbooks"]), 1),
                     1.0 if hits else 0.0, hits / k))

    def agg(rs):
        n = len(rs)
        return {"cases": n, "runbook_recall@3": round(sum(r[1] for r in rs) / n, 3),
                "section_hit@3": round(sum(r[2] for r in rs) / n, 3),
                "section_precision@3": round(sum(r[3] for r in rs) / n, 3)} if n else {"cases": 0}
    classes = sorted({r[0] for r in rows})
    return {"overall": agg(rows), "per_class": {c: agg([r for r in rows if r[0] == c]) for c in classes}}


def table(name: str, result: dict) -> str:
    o = result["overall"]
    lines = [f"{name:<22} runbook_recall@3={o['runbook_recall@3']:.3f}  section_hit@3={o['section_hit@3']:.3f}  "
             f"section_precision@3={o['section_precision@3']:.3f}  ({o['cases']} cases)"]
    for c, r in result["per_class"].items():
        lines.append(f"    {c:<34} hit={r['section_hit@3']:.2f} precision={r['section_precision@3']:.2f} "
                     f"runbook={r['runbook_recall@3']:.2f}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m argus.evaluation.retrieval")
    ap.add_argument("--cases", default="tests/eval/cases")
    ap.add_argument("--labels", default="tests/eval/section_labels.yaml")
    ap.add_argument("--score", action="store_true", help="print the TF-IDF table instead of the items")
    a = ap.parse_args()
    items = capture_queries(load_cases(Path(a.cases)), Path(tempfile.mkdtemp()), Path(a.labels))
    if not a.score:
        for it in items:
            sys.stdout.write(json.dumps(it) + "\n")
        return
    from argus.infrastructure.wiring import Settings, make_knowledge
    import dataclasses
    kb = make_knowledge(dataclasses.replace(Settings(), retrieval="tfidf"))
    print(table("tfidf", score(lambda it: kb.search(it["query"], 3, it["runbook_ids"]), items)))


if __name__ == "__main__":
    main()
