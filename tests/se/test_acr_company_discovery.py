"""Isolated discovery study contracts; no scientific gates are modified."""

import hashlib
import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

STUDY = Path(__file__).resolve().parents[2] / "research/se_acr_company_discovery_v1"


def harness():
    spec = importlib.util.spec_from_file_location("study_acquire", STUDY / "acquire.py")
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def test_preregistration_and_name_free_queries_are_frozen():
    for line in (STUDY / "FROZEN.sha256").read_text().splitlines():
        digest, path = line.split(maxsplit=1)
        assert hashlib.sha256((STUDY / path).read_bytes()).hexdigest() == digest
    spec = json.loads((STUDY / "search_spec.json").read_text())
    ref = json.loads((STUDY / "evaluation/reference.json").read_text())
    query_text = " ".join(q["q"].lower() for q in spec["queries"])
    for row in ref["entries"]:
        assert row["name"].lower() not in query_text
    assert len(spec["queries"]) == 4
    assert "reference.json" not in (STUDY / "acquire.py").read_text()


def test_selection_preserves_rank_excludes_pdfs_and_caps():
    m = harness()
    spec = {
        "queries": [{"id": "Q1", "q": "generic", "family": "company"}],
        "max_documents_per_family": 1,
    }
    receipt = {
        "query_id": "Q1",
        "query": "generic",
        "response": "PDF (https://issuer.test/file.pdf)\n"
        "First (https://issuer.test/first)\n"
        "Second (https://issuer.test/second)\n",
    }
    rows = m.select(spec, {"Q1": receipt}, {"issuer.test": "Issuer"})
    assert [r["rank"] for r in rows if r["selected"]] == [2]
    assert rows[2]["reason"] == "family cap reached"
    with pytest.raises(ValueError, match="frozen query"):
        m.select(spec, {"Q1": {**receipt, "query": "seeded product"}}, {})


def test_acquisition_nomination_does_not_read_reference(tmp_path, monkeypatch):
    m = harness()
    spec = {
        "as_of": date.today().isoformat(),
        "max_documents_per_family": 1,
        "max_page_bytes": 2000,
        "queries": [{"id": "Q1", "q": "CD19 engager autoimmune"}],
    }
    rows = [
        {
            "url": "https://issuer.test/product",
            "family": "company",
            "selected": True,
            "declared_publisher": "Issuer",
        }
    ]
    raw = "<html><body>ZX-9321 is a CD19 CD3 bispecific antibody for lupus.</body></html>"
    original_read = Path.read_text

    def guarded(path, *args, **kwargs):
        if path.name == "reference.json":
            raise AssertionError("reference leaked into acquisition")
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", guarded)
    calls = []
    m.acquire(spec, rows, tmp_path / "one", fetch_fn=lambda url: calls.append(url) or raw)
    assert len(calls) == 1
    result = json.loads((tmp_path / "one/nominations.json").read_text())
    assert any(row["name"] == "ZX-9321" for row in result)
    from bve.se.acquisition.corpus_store import CorpusStore

    docs = CorpusStore(tmp_path / "one/corpus").documents()
    assert m.nominate(docs) == result == m.nominate(docs)
    seal = json.loads((tmp_path / "one/NOMINATIONS_SEALED.json").read_text())
    assert seal["seeded_names"] == []
    assert seal["scientific_eligibility"] == "NOT_EVALUATED"
    assert any(name.endswith(".html") for name in seal["files"])
    with pytest.raises(FileExistsError):
        m.acquire(spec, rows, tmp_path / "one", fetch_fn=lambda _: raw)


def test_oversized_page_is_a_failure_not_a_nomination(tmp_path):
    m = harness()
    spec = {
        "as_of": date.today().isoformat(),
        "max_documents_per_family": 1,
        "max_page_bytes": 20,
        "queries": [],
    }
    rows = [
        {
            "url": "https://issuer.test/large",
            "family": "company",
            "selected": True,
            "declared_publisher": "Issuer",
        }
    ]
    m.acquire(spec, rows, tmp_path / "out", fetch_fn=lambda _: "X" * 21)
    assert json.loads((tmp_path / "out/nominations.json").read_text()) == []
    health = json.loads((tmp_path / "out/health.json").read_text())
    assert health[0]["parse_failures"] == 1


def evaluator():
    spec = importlib.util.spec_from_file_location("study_evaluate", STUDY / "evaluate.py")
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def scoring_fixture(tmp_path):
    doc = {
        "document_id": "d",
        "text": "ZX-9321 named drug antibody CD19 autoimmune development",
        "publication_date": "2025-01-01",
        "source_family": "conference_acr",
        "parser_status": "OK",
        "index_status": "INDEXED",
        "source_url": "https://acrabstracts.org/abstract/test",
    }
    (tmp_path / "corpus").mkdir()
    (tmp_path / "corpus/manifest.jsonl").write_text(json.dumps(doc) + "\n")
    (tmp_path / "nominations.json").write_text(
        json.dumps([{"name": "ZX-9321", "document_id": "d", "url": doc["source_url"]}])
    )
    (tmp_path / "fetches.json").write_text(
        json.dumps([{"url": doc["source_url"], "status": "OK", "sha256": "raw"}])
    )
    (tmp_path / "selection.json").write_text(
        json.dumps([{"url": doc["source_url"], "selected": True, "query_id": "Q1"}])
    )
    (tmp_path / "NOMINATIONS_SEALED.json").write_text(
        json.dumps(
            {
                "seeded_names": [],
                "files": {
                    str(p.relative_to(tmp_path)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in tmp_path.rglob("*")
                    if p.is_file()
                },
            }
        )
    )
    ref = {
        "baseline_cutoff": "2026-10-15",
        "entries": [
            {
                "ref_id": "test",
                "name": "ZX-9321",
                "aliases": [],
                "label": "RELEVANT_INVESTIGATIONAL",
                "fully_verified": True,
                "baseline_found": False,
            }
        ],
    }
    span = {
        "start": 0,
        "end": len(doc["text"]),
        "sha256": hashlib.sha256(doc["text"].encode()).hexdigest(),
    }
    assessment = {
        "name": "ZX-9321",
        "document_id": "d",
        "classification": "NAMED_INVESTIGATIONAL",
        "evidence_spans": {key: span for key in evaluator().REQUIRED},
    }
    return ref, assessment


def test_scoring_rejects_comparators_missing_format_and_prior_recovery(tmp_path):
    m = evaluator()
    ref, a = scoring_fixture(tmp_path)
    assert m.score(tmp_path, ref, [a])["primary_successes"] == ["ZX-9321"]
    del a["evidence_spans"]["antibody_format"]
    assert m.score(tmp_path, ref, [a])["endpoint"] == "FAIL"
    a["evidence_spans"]["antibody_format"] = a["evidence_spans"]["identity"]
    ref["entries"][0]["label"] = "APPROVED_COMPARATOR"
    assert m.score(tmp_path, ref, [a])["endpoint"] == "FAIL"
    ref["entries"][0]["label"] = "RELEVANT_INVESTIGATIONAL"
    ref["entries"][0]["baseline_found"] = True
    assert m.score(tmp_path, ref, [a])["endpoint"] == "FAIL"


def test_scoring_rejects_changed_corpus_and_unobserved_names(tmp_path):
    m = evaluator()
    ref, a = scoring_fixture(tmp_path)
    a["name"] = "NOT-NOMINATED"
    with pytest.raises(ValueError, match="not nominated"):
        m.score(tmp_path, ref, [a])
    (tmp_path / "nominations.json").write_text("[]")
    with pytest.raises(ValueError, match="sealed input changed"):
        m.score(tmp_path, ref, [])
