"""Tests for sponsor-trial fetch + protocol parsing."""
from __future__ import annotations

from tests.discovery.conftest import make_protocol

from bve.discovery.sponsor_trials import (
    TrialRecord,
    fetch_sponsor_trials,
    parse_protocol,
)


class TestParseProtocol:
    def test_basic_fields(self):
        proto = make_protocol(
            nct_id="NCT01", drug="DrugX", phases=["PHASE2"], enrollment=120,
            conditions=["Breast Cancer"], title="Pivotal study of DrugX",
            primary_completion="2026-09", lead_sponsor="Acme Therapeutics",
        )
        rec = parse_protocol(proto, "Acme Therapeutics")
        assert rec is not None
        assert rec.nct_id == "NCT01"
        assert rec.drug_names == ("DrugX",)
        assert rec.phase == "phase_2"
        assert rec.enrollment == 120
        assert rec.conditions == ("Breast Cancer",)
        assert rec.primary_completion_date == "2026-09"

    def test_no_nct_returns_none(self):
        assert parse_protocol(make_protocol(nct_id="", drug="X", phases=["PHASE1"])) is None

    def test_missing_phase_kept_as_none(self):
        rec = parse_protocol(make_protocol(nct_id="NCT02", drug="X", phases=None))
        assert rec is not None and rec.phase is None

    def test_phase_list_takes_max(self):
        rec = parse_protocol(make_protocol(nct_id="NCT03", drug="X", phases=["PHASE1", "PHASE2"]))
        assert rec.phase == "phase_2"

    def test_phase4_maps_to_phase3(self):
        rec = parse_protocol(make_protocol(nct_id="NCT04", drug="X", phases=["PHASE4"]))
        assert rec.phase == "phase_3"

    def test_placebo_dropped_from_drugs(self):
        proto = make_protocol(
            nct_id="NCT05", drug="DrugX", phases=["PHASE3"],
            extra_interventions=[("DRUG", "Placebo")],
        )
        rec = parse_protocol(proto)
        assert rec.drug_names == ("DrugX",)

    def test_non_asset_intervention_dropped(self):
        proto = make_protocol(
            nct_id="NCT06", drug="DrugX", phases=["PHASE2"],
            extra_interventions=[("PROCEDURE", "Surgery"), ("DEVICE", "Pump")],
        )
        rec = parse_protocol(proto)
        assert rec.drug_names == ("DrugX",)

    def test_biological_intervention_kept(self):
        proto = make_protocol(nct_id="NCT07", drug="mAb-1", drug_type="BIOLOGICAL", phases=["PHASE1"])
        rec = parse_protocol(proto)
        assert rec.drug_names == ("mAb-1",)

    def test_sponsor_is_lead_exact(self):
        proto = make_protocol(nct_id="NCT08", drug="X", phases=["PHASE2"],
                              lead_sponsor="Beam Therapeutics, Inc.")
        rec = parse_protocol(proto, "Beam Therapeutics")
        assert rec.sponsor_is_lead is True

    def test_sponsor_not_lead_when_different(self):
        proto = make_protocol(nct_id="NCT09", drug="X", phases=["PHASE2"],
                              lead_sponsor="National Cancer Institute")
        rec = parse_protocol(proto, "Beam Therapeutics")
        assert rec.sponsor_is_lead is False

    def test_sponsor_is_lead_false_without_company(self):
        proto = make_protocol(nct_id="NCT10", drug="X", phases=["PHASE2"])
        rec = parse_protocol(proto)
        assert rec.sponsor_is_lead is False

    def test_enrollment_non_int_safe(self):
        proto = make_protocol(nct_id="NCT11", drug="X", phases=["PHASE2"])
        proto["designModule"]["enrollmentInfo"] = {"count": "not-a-number"}
        rec = parse_protocol(proto)
        assert rec.enrollment is None

    def test_record_is_frozen(self):
        rec = parse_protocol(make_protocol(nct_id="NCT12", drug="X", phases=["PHASE1"]))
        import pytest
        with pytest.raises(Exception):
            rec.nct_id = "other"  # type: ignore[misc]


class TestFetchSponsorTrials:
    def test_injected_fetcher_parses(self):
        protos = [
            make_protocol(nct_id="NCT01", drug="DrugX", phases=["PHASE2"]),
            make_protocol(nct_id="NCT02", drug="DrugY", phases=["PHASE1"]),
        ]
        recs = fetch_sponsor_trials("Acme", fetcher=lambda **kw: protos)
        assert len(recs) == 2
        assert all(isinstance(r, TrialRecord) for r in recs)

    def test_cache_round_trip(self, tmp_path):
        from bve.pipeline.disk_cache import DiskCache

        cache = DiskCache(root=tmp_path / "c")
        protos = [make_protocol(nct_id="NCT01", drug="DrugX", phases=["PHASE2"])]
        calls = {"n": 0}

        def fetcher(**kw):
            calls["n"] += 1
            return protos

        r1 = fetch_sponsor_trials("Acme Bio", fetcher=fetcher, cache=cache)
        r2 = fetch_sponsor_trials("Acme Bio", fetcher=fetcher, cache=cache)
        assert calls["n"] == 1  # second call served from cache
        assert len(r1) == len(r2) == 1

    def test_cache_only_no_network(self, tmp_path):
        from bve.pipeline.disk_cache import DiskCache

        cache = DiskCache(root=tmp_path / "c")

        def fetcher(**kw):
            raise AssertionError("network must not be hit in cache_only mode")

        recs = fetch_sponsor_trials("Nobody", fetcher=fetcher, cache=cache, cache_only=True)
        assert recs == []
