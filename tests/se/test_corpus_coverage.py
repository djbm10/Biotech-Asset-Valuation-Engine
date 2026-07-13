from __future__ import annotations

from datetime import date

from bve.se.acquisition.corpus_store import CorpusStore
from bve.se.acquisition.source_health import SourceHealth, SourceHealthReport
from bve.se.evaluation.corpus_coverage import (
    attribute_required_evidence,
    evaluate_corpus_coverage,
)
from bve.se.schemas.contracts import SourceTier

AS_OF = date(2026, 7, 10)

_REFERENCE = (
    "benchmark_id,target,canonical_asset,aliases,current_or_last_sponsor,development_state,"
    "highest_public_stage,expected_disposition,reference_tier,identity_source,source_locator,"
    "material_limitation,review_status\n"
    "DEV-BCMA-001,BCMA,teclistamab,TECVAYLI|JNJ-64007957,J&J,approved,Approved,INCLUDE,GOLD,DailyMed,"
    "https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=54e0f974-ccee-44ea-9254-40e9883cee1e,x,PRIMARY_VERIFIED\n"
    "DEV-BCMA-005,BCMA,alnuctamab,CC-93269|BMS-986349,BMS,status_uncertain,Phase 1,INCLUDE,SILVER,"
    "Public trial registry,NCT03486067,x,NEEDS_PRIMARY_REFRESH\n"
    "DEV-BCMA-010,BCMA,WVT078,WVT-078,Novartis,historical_terminated,Phase 1,INCLUDE,SILVER,"
    "Public trial registry,NCT04123418,x,NEEDS_PRIMARY_REFRESH\n"
)


def _write_reference(tmp_path):
    path = tmp_path / "reference_universe.csv"
    path.write_text(_REFERENCE)
    return path


def _seed_corpus(tmp_path):
    store = CorpusStore(tmp_path / "corpus")
    # GOLD approved label — matched by INN substring.
    store.add(
        source_family="fda_label", source_url="https://dailymed.nlm.nih.gov/x",
        publisher="FDA", document_type="approved_drug_label", source_tier=SourceTier.REGULATORY,
        raw_payload={"a": 1}, text="TECVAYLI teclistamab-cqyv BCMA CD3 bispecific", as_of_date=AS_OF,
    )
    # SILVER trial — matched by NCT id in source_url.
    store.add(
        source_family="clinicaltrials_gov",
        source_url="https://clinicaltrials.gov/study/NCT03486067",
        publisher="CT.gov", document_type="trial_registry_record", source_tier=SourceTier.REGISTRY,
        raw_payload={"b": 1}, text="a BCMA CD3 study", as_of_date=AS_OF, native_snapshot=True,
    )
    # WVT078 intentionally absent -> remains a coverage gap.
    return tmp_path / "corpus"


def test_coverage_by_inn_and_nct(tmp_path) -> None:
    corpus = _seed_corpus(tmp_path)
    report = evaluate_corpus_coverage(corpus, _write_reference(tmp_path))
    assert report.gold_covered == 1 and report.gold_total == 1
    assert report.silver_covered == 1 and report.silver_total == 2
    by_id = {a.benchmark_id: a for a in report.assets}
    assert by_id["DEV-BCMA-001"].matched_source_family == "fda_label"
    assert by_id["DEV-BCMA-005"].matched_token == "nct03486067"
    assert by_id["DEV-BCMA-010"].covered is False


def test_release_threshold_logic(tmp_path) -> None:
    corpus = _seed_corpus(tmp_path)
    report = evaluate_corpus_coverage(corpus, _write_reference(tmp_path))
    # GOLD 1/1 and SILVER 1/2 -> one silver short is allowed only at >= total-1, here total-1 == 1.
    assert report.meets_release_thresholds() is True
    report.silver_total = 3
    assert report.meets_release_thresholds() is False


def test_attribute_required_evidence(tmp_path) -> None:
    corpus = _seed_corpus(tmp_path)
    coverage = evaluate_corpus_coverage(corpus, _write_reference(tmp_path))
    health = SourceHealthReport(
        sources=[
            SourceHealth(
                source_family="fda_label",
                connector_succeeded=True,
                query_returned_results=True,
                raw_record_count=1,
                documents_parsed=1,
                documents_indexed=1,
            ),
            SourceHealth(
                source_family="pubmed",
                connector_succeeded=True,
                query_returned_results=True,
                raw_record_count=1,
                documents_parsed=1,
                documents_indexed=1,
            ),
        ]
    )
    updated = attribute_required_evidence(coverage, health)
    by_family = {s.source_family: s for s in updated.sources}
    assert by_family["fda_label"].required_evidence_present is True
    assert by_family["pubmed"].required_evidence_present is False
