"""T-0044 step 3: section-level labels and the TF-IDF vs hybrid comparison.

Runbook-level recall@3 is 1.00 for every class (the candidates are the class's runbooks), so it cannot tell two
retrievers apart. A case's USEFUL sections are the diagnostic sections (`tests/eval/section_labels.yaml`) of the
runbooks it is labelled with, plus per-case extras (a network cause also needs RB-009). Measured per retriever:
runbook recall@3, section hit@3 (at least one useful section in the top 3) and section precision@3 (useful share of 3).
"""
from __future__ import annotations

from pathlib import Path

import yaml

from argus.adapters.outbound.config_adapters import TfidfRunbooks
from argus.adapters.outbound.rag import HashingEmbeddings, HybridRunbooks
from argus.domain.model import Passage
from argus.evaluation.cases import load_cases
from argus.evaluation.retrieval import capture_queries, load_section_labels, score, useful_sections

ROOT = Path(__file__).resolve().parents[1]
CASES = {c.id: c for c in load_cases(ROOT / "tests" / "eval" / "cases")}
LABELS = ROOT / "tests" / "eval" / "section_labels.yaml"


def test_every_labelled_section_exists_in_the_library():
    kb = TfidfRunbooks(str(ROOT / "argus" / "runbooks"))
    have = {f"{rid}#{sec}" for rid, _, _, sec, _ in kb.sections}
    working, extra = load_section_labels(LABELS)
    for case in CASES.values():
        missing = useful_sections(case, working, extra) - have
        assert not missing, (case.id, sorted(missing))
    assert set(extra) <= set(CASES)                                   # extras name real cases


def test_a_case_needs_the_diagnostic_sections_of_its_own_runbooks():
    working, extra = load_section_labels(LABELS)
    oom = useful_sections(CASES["restart-oom-01"], working, extra)
    assert "RB-001#Diagnostic workflow" in oom and not any(s.startswith("RB-008#") for s in oom)
    crash = useful_sections(CASES["restart-crash-01"], working, extra)
    assert "RB-008#Decision tree" in crash and not any(s.startswith("RB-001#") for s in crash)
    net = useful_sections(CASES["dep-backend-wrong-network"], working, extra)
    assert "RB-003#Diagnostic workflow" in net and "RB-009#Diagnostic workflow" in net
    assert not any("Lab validation" in s or "References" in s or " — " in s for s in oom | crash | net)


def test_the_queries_are_the_recall_nodes_own(tmp_path):
    items = capture_queries([CASES["health-api-vm095-01"], CASES["restart-oom-01"], CASES["healthy-check-api"]],
                            tmp_path)
    by = {i["case"]: i for i in items}
    assert set(by) == {"health-api-vm095-01", "restart-oom-01"}            # a healthy check never recalls
    h = by["health-api-vm095-01"]
    assert h["class"] == "health_check_failed" and h["query"].startswith("health_check_failed ")
    assert CASES["health-api-vm095-01"].reason in h["query"]
    assert h["runbook_ids"] == ["RB-002", "RB-003"] and h["runbooks"] == ["RB-002"]
    assert "RB-002#Diagnostic workflow" in h["useful"]


def test_score_counts_runbook_recall_section_hit_and_precision():
    items = [{"case": "a", "class": "c1", "query": "q", "runbook_ids": ["RB-001"], "runbooks": ["RB-001"],
              "useful": ["RB-001#Diagnostic workflow", "RB-001#Decision tree"]},
             {"case": "b", "class": "c2", "query": "q", "runbook_ids": ["RB-002"], "runbooks": ["RB-002"],
              "useful": ["RB-002#Diagnostic workflow"]}]

    def p(rid, sec):
        return Passage(runbook_id=rid, runbook_version="1", runbook_status="active", section=sec, text="t", score=1.0)

    answers = {"a": [p("RB-001", "Diagnostic workflow"), p("RB-001", "Decision tree"), p("RB-001", "Scope")],
               "b": [p("RB-002", "Scope"), p("RB-002", "References")]}
    r = score(lambda item: answers[item["case"]], items)
    assert r["overall"] == {"cases": 2, "runbook_recall@3": 1.0, "section_hit@3": 0.5, "section_precision@3": 0.333}
    assert r["per_class"]["c1"]["section_precision@3"] == 0.667 and r["per_class"]["c2"]["section_hit@3"] == 0.0


def test_skip_titles_drops_the_title_sections():
    tfidf = TfidfRunbooks(str(ROOT / "argus" / "runbooks"))
    import hashlib
    body = {(r, s): b for r, _, _, s, b in tfidf.sections}

    def h(rid, sec):
        return {"runbook_id": rid, "section": sec, "sha256": hashlib.sha256(body[(rid, sec)].encode()).hexdigest(),
                "score": 0.9}
    title = next(s for r, _, _, s, _ in tfidf.sections if r == "RB-001" and s.startswith("RB-001 "))

    class Index:
        def __init__(self):
            self.limits = []

        def hybrid(self, query, vector, alpha, limit, ids):
            self.limits.append(limit)
            return [h("RB-001", title), h("RB-001", "Diagnostic workflow"), h("RB-001", "Decision tree"),
                    h("RB-001", "Symptoms")][:limit]

    ix = Index()
    got = HybridRunbooks(tfidf, HashingEmbeddings(dims=8), ix, skip_titles=True).search("q", 3, ["RB-001"])
    assert [p.section for p in got] == ["Diagnostic workflow", "Decision tree", "Symptoms"] and ix.limits == [4]
    assert HybridRunbooks(tfidf, HashingEmbeddings(dims=8), Index()).search("q", 3, ["RB-001"])[0].section == title


def test_the_cli_has_runbooks_compare():
    from argus.__main__ import build_parser
    a = build_parser().parse_args(["runbooks", "compare", "--alphas", "0,0.5,1", "--skip-titles"])
    assert (a.runbooks_cmd, a.alphas, a.skip_titles) == ("compare", "0,0.5,1", True)


def test_the_labels_file_is_small_and_explicit():
    raw = yaml.safe_load(LABELS.read_text(encoding="utf-8"))
    assert raw["working_sections"] == ["Symptoms", "Plausible causes / hypotheses", "Required evidence",
                                       "Diagnostic workflow", "Decision tree", "Evidence interpretation"]
    assert raw["extra"]["dep-backend-wrong-network"] == ["RB-009"]


def test_every_section_is_embedded_with_its_runbook_title():
    """Step 3: without the title stubs, a section must still say which runbook it belongs to (OOM vs crash loop)."""
    tfidf = TfidfRunbooks(str(ROOT / "argus" / "runbooks"))
    seen = []

    class Rec(HashingEmbeddings):
        def embed(self, texts):
            seen.extend(texts)
            return super().embed(texts)

    class Index:
        def recreate(self):
            pass

        def upsert(self, objects):
            pass

    HybridRunbooks(tfidf, Rec(dims=8), Index()).index()
    dw = next(t for t in seen if t.startswith("RB-008 ") and "Diagnostic workflow" in t.splitlines()[0])
    assert dw.splitlines()[0] == f"RB-008 {tfidf.titles['RB-008']} — Diagnostic workflow"
