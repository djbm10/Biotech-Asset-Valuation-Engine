"""Tests for ops/config_quality.py — corpus config provenance dashboard."""
from __future__ import annotations

from datetime import date

import pytest
import yaml

from bve.ops.config_quality import (
    CURRENT_QUALITY_VERSION,
    QUALITY_SCORE_VERSIONS,
    ConfigQualityRecord,
    commercial_inputs_provenance,
    completeness_score,
    scan_config,
    scan_corpus,
    to_json,
    to_markdown,
)

# --- versioned weights are explicit and sane ---------------------------------


def test_score_weights_sum_to_one():
    for version, weights in QUALITY_SCORE_VERSIONS.items():
        assert abs(sum(weights.values()) - 1.0) < 1e-9, version


def test_current_version_is_registered():
    assert CURRENT_QUALITY_VERSION in QUALITY_SCORE_VERSIONS


# --- commercial_inputs provenance classification -----------------------------


def test_provenance_curated_funnel():
    mm = {"commercial_inputs": {"patient_pool": {"prevalence_thousands": 1, "eligible_rate": 0.3}}}
    assert commercial_inputs_provenance(mm) == "curated_funnel"


def test_provenance_derived():
    mm = {"commercial_inputs": {"patient_pool": {"addressable_k": 8.0}}}
    assert commercial_inputs_provenance(mm) == "derived"


def test_provenance_none():
    assert commercial_inputs_provenance({}) == "none"
    assert commercial_inputs_provenance({"commercial_inputs": None}) == "none"


# --- completeness scoring ----------------------------------------------------


def test_completeness_full_when_nothing_defaulted_and_curated():
    weights = QUALITY_SCORE_VERSIONS["v1.0"]
    assert completeness_score([], "curated_funnel", weights) == pytest.approx(1.0)


def test_completeness_zero_when_all_defaulted_and_no_ci():
    weights = QUALITY_SCORE_VERSIONS["v1.0"]
    all_fields = [f for f in weights if f != "commercial_inputs"]
    assert completeness_score(all_fields, "none", weights) == pytest.approx(0.0)


def test_derived_ci_gets_half_credit_vs_curated():
    weights = QUALITY_SCORE_VERSIONS["v1.0"]
    curated = completeness_score([], "curated_funnel", weights)
    derived = completeness_score([], "derived", weights)
    none = completeness_score([], "none", weights)
    ci_w = weights["commercial_inputs"]
    assert curated - derived == pytest.approx(ci_w * 0.5)
    assert derived - none == pytest.approx(ci_w * 0.5)


# --- single-config scan ------------------------------------------------------


def _write_cfg(tmp_path, name, cfg):
    d = tmp_path / "auto_generated"
    d.mkdir(exist_ok=True)
    p = d / f"{name}.yaml"
    p.write_text(yaml.safe_dump(cfg, sort_keys=False), encoding="utf-8")
    return p


def _curated_cfg():
    return {
        "company": {"ticker": "edit"},
        "market_model": {
            "net_price_per_patient_usd": 1_800_000.0,
            "commercial_inputs": {
                "patient_pool": {"prevalence_thousands": 1, "eligible_rate": 0.35}
            },
        },
        "_meta": {
            "generator_version": "profile-0.1",
            "generated_at": "2026-06-14",
            "evidence_level": "coarse",
            "defaulted_fields": ["cogs_rate", "years_to_peak"],
            "provisional": True,
        },
    }


def test_scan_curated_config(tmp_path):
    p = _write_cfg(tmp_path, "edit", _curated_cfg())
    rec = scan_config(p, as_of=date(2026, 6, 24))
    assert isinstance(rec, ConfigQualityRecord)
    assert rec.ticker == "EDIT"
    assert rec.vintage == "auto_generated"
    assert rec.commercial_inputs_provenance == "curated_funnel"
    assert rec.evidence_level == "coarse"
    assert rec.metadata_present is True
    assert rec.n_defaulted == 2
    assert rec.defaulted_fields == ["cogs_rate", "years_to_peak"]
    assert rec.completeness_score is not None and rec.completeness_score > 0.9
    assert rec.staleness_days == 10
    assert rec.score_version == CURRENT_QUALITY_VERSION
    assert rec.score_weights == QUALITY_SCORE_VERSIONS[CURRENT_QUALITY_VERSION]


def test_scan_missing_metadata_yields_none_completeness(tmp_path):
    cfg = {"company": {"ticker": "xxx"}, "market_model": {}, "_meta": {"evidence_level": "coarse"}}
    p = _write_cfg(tmp_path, "xxx", cfg)
    rec = scan_config(p)
    assert rec.metadata_present is False
    assert rec.completeness_score is None  # never overstate precision


def test_derived_config_scores_below_curated(tmp_path):
    curated = scan_config(_write_cfg(tmp_path, "edit", _curated_cfg()))
    derived_cfg = _curated_cfg()
    derived_cfg["company"]["ticker"] = "agio"
    derived_cfg["market_model"]["commercial_inputs"] = {
        "patient_pool": {"addressable_k": 8.0}
    }
    derived = scan_config(_write_cfg(tmp_path, "agio", derived_cfg))
    assert derived.completeness_score < curated.completeness_score


def test_unknown_score_version_raises(tmp_path):
    p = _write_cfg(tmp_path, "edit", _curated_cfg())
    with pytest.raises(ValueError, match="Unknown quality score version"):
        scan_config(p, score_version="v9.9")


# --- corpus scan + rendering -------------------------------------------------


def test_scan_corpus_sorted_worst_first(tmp_path):
    _write_cfg(tmp_path, "good", _curated_cfg())
    bad = _curated_cfg()
    bad["company"]["ticker"] = "bad"
    bad["market_model"].pop("commercial_inputs")
    bad["_meta"]["defaulted_fields"] = list(
        QUALITY_SCORE_VERSIONS["v1.0"].keys()
    )
    _write_cfg(tmp_path, "bad", bad)

    records = scan_corpus([tmp_path / "auto_generated"])
    assert len(records) == 2
    assert records[0].ticker == "BAD"  # worst first
    assert records[0].completeness_score < records[1].completeness_score


def test_scan_corpus_skips_missing_root(tmp_path):
    assert scan_corpus([tmp_path / "does_not_exist"]) == []


def test_to_json_roundtrips(tmp_path):
    records = scan_corpus([_write_cfg(tmp_path, "edit", _curated_cfg()).parent])
    payload = to_json(records)
    assert isinstance(payload, list)
    assert payload[0]["ticker"] == "EDIT"
    assert "completeness_score" in payload[0]


def test_to_markdown_has_table_and_summary(tmp_path):
    _write_cfg(tmp_path, "edit", _curated_cfg())
    md = to_markdown(scan_corpus([tmp_path / "auto_generated"]))
    assert "# Config Quality Dashboard" in md
    assert "| Ticker |" in md
    assert "EDIT" in md
    assert "score version" in md.lower()


def test_to_markdown_empty():
    assert "No configs found" in to_markdown([])
