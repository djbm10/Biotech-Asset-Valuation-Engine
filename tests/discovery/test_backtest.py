"""Tests for the backtest harness: per-seed eval, aggregation, sweep, failure modes."""
from __future__ import annotations

from tests.discovery.conftest import make_protocol

from bve.discovery.backtest import (
    FM_AMBIGUOUS,
    FM_NO_TRIALS,
    FM_SPONSOR_MISS,
    FM_WRONG_LEAD,
    build_report,
    evaluate_seed,
    run_backtest,
)
from bve.discovery.sponsor_trials import parse_protocol
from bve.pipeline.universe_registry import UniverseRegistryEntry


def _seed(ticker, company, drug, indication, stage, modality):
    return UniverseRegistryEntry(
        ticker=ticker, company_name=company, asset_id=f"a-{ticker.lower()}",
        drug_name=drug, indication=indication, therapeutic_area="oncology",
        stage=stage, modality=modality,
    )


def _fetch_from(mapping):
    """Build a fetch_fn returning parsed TrialRecords for a company name."""
    def fetch(company_name):
        protos = mapping.get(company_name, [])
        return [parse_protocol(p, company_name) for p in protos]
    return fetch


class TestEvaluateSeed:
    def test_correct_lead(self):
        seed = _seed("ACME", "Acme Therapeutics", "DrugX", "Breast Cancer", "phase_3", "small_molecule")
        fetch = _fetch_from({"Acme Therapeutics": [
            make_protocol(nct_id="NCT01", drug="DrugX", phases=["PHASE3"], enrollment=400,
                          conditions=["Breast Cancer"], lead_sponsor="Acme Therapeutics"),
        ]})
        r = evaluate_seed(seed, fetch)
        assert r.lead_correct is True
        assert r.failure_mode is None
        assert r.stage_match is True
        assert r.indication_match is True

    def test_no_trials(self):
        seed = _seed("ACME", "Acme Therapeutics", "DrugX", "Cancer", "phase_2", "small_molecule")
        r = evaluate_seed(seed, _fetch_from({}))
        assert r.n_programs == 0
        assert r.failure_mode == FM_NO_TRIALS

    def test_sponsor_resolution_miss(self):
        # Trials exist but none have a drug (e.g. observational) → program-less.
        seed = _seed("ACME", "Acme Therapeutics", "DrugX", "Cancer", "phase_2", "small_molecule")
        fetch = _fetch_from({"Acme Therapeutics": [
            make_protocol(nct_id="NCT01", drug=None, phases=["PHASE2"]),
        ]})
        r = evaluate_seed(seed, fetch)
        assert r.n_programs == 0
        assert r.failure_mode == FM_SPONSOR_MISS

    def test_wrong_lead_picked(self):
        # Clear (high-margin) winner that is NOT the truth drug.
        seed = _seed("ACME", "Acme Therapeutics", "TrueDrug", "Cancer", "phase_3", "small_molecule")
        fetch = _fetch_from({"Acme Therapeutics": [
            make_protocol(nct_id="NCT01", drug="WrongDrug", phases=["PHASE3"], enrollment=500,
                          lead_sponsor="Acme Therapeutics"),
            make_protocol(nct_id="NCT02", drug="TrueDrug", phases=["PHASE1"]),
        ]})
        r = evaluate_seed(seed, fetch)
        assert r.lead_correct is False
        assert r.failure_mode == FM_WRONG_LEAD

    def test_ambiguous_low_margin(self):
        # Two near-identical Phase 2 programs, truth is the one NOT picked.
        seed = _seed("ACME", "Acme Therapeutics", "DrugB", "Cancer", "phase_2", "small_molecule")
        fetch = _fetch_from({"Acme Therapeutics": [
            make_protocol(nct_id="NCT01", drug="DrugA", phases=["PHASE2"]),
            make_protocol(nct_id="NCT02", drug="DrugB", phases=["PHASE2"]),
        ]})
        r = evaluate_seed(seed, fetch)
        if not r.lead_correct:
            assert r.failure_mode == FM_AMBIGUOUS

    def test_nda_bla_stage_understated(self):
        seed = _seed("ACME", "Acme Therapeutics", "DrugX", "Cancer", "nda_bla", "small_molecule")
        fetch = _fetch_from({"Acme Therapeutics": [
            make_protocol(nct_id="NCT01", drug="DrugX", phases=["PHASE3"], enrollment=400,
                          lead_sponsor="Acme Therapeutics"),
        ]})
        r = evaluate_seed(seed, fetch)
        assert r.lead_correct is True       # drug still matches
        assert r.stage_match is False
        assert r.stage_understated is True


class TestBuildReport:
    def _mixed_results(self):
        seeds = [
            _seed("A", "Alpha Co", "DrugA", "Cancer", "phase_3", "small_molecule"),
            _seed("B", "Beta Co", "DrugB", "Cancer", "phase_2", "small_molecule"),
            _seed("C", "Gamma Co", "DrugC", "Cancer", "phase_2", "small_molecule"),
        ]
        fetch = _fetch_from({
            "Alpha Co": [make_protocol(nct_id="N1", drug="DrugA", phases=["PHASE3"],
                                       enrollment=400, lead_sponsor="Alpha Co")],
            "Beta Co": [make_protocol(nct_id="N2", drug="DrugB", phases=["PHASE2"],
                                      lead_sponsor="Beta Co")],
            # Gamma: no trials → no program.
        })
        return [evaluate_seed(s, fetch) for s in seeds]

    def test_coverage_and_accuracy(self):
        report = build_report(self._mixed_results())
        assert report.n_seeds == 3
        assert report.n_with_program == 2
        assert abs(report.coverage - 2 / 3) < 1e-6
        assert report.lead_drug_accuracy == 1.0  # both found are correct

    def test_failure_modes_counted(self):
        report = build_report(self._mixed_results())
        assert report.failure_modes.get(FM_NO_TRIALS) == 1

    def test_threshold_sweep_shape(self):
        report = build_report(self._mixed_results())
        assert len(report.threshold_sweep) == 5
        for row in report.threshold_sweep:
            assert set(row) == {"margin", "n_high", "precision"}

    def test_auto_tier_precision(self):
        report = build_report(self._mixed_results())
        # Both found programs are single-program (high tier) and correct → 100%.
        assert report.auto_tier_precision == 1.0
        assert report.auto_tier_n == 2

    def test_to_text_renders(self):
        text = build_report(self._mixed_results()).to_text()
        assert "AUTO-TIER PRECISION" in text
        assert "Failure modes" in text

    def test_to_dict_round_trips(self):
        d = build_report(self._mixed_results()).to_dict()
        assert d["n_seeds"] == 3
        assert "results" in d


class TestRunBacktest:
    def test_end_to_end_with_injected_fetch(self):
        seeds = [_seed("A", "Alpha Co", "DrugA", "Cancer", "phase_3", "small_molecule")]
        fetch = _fetch_from({"Alpha Co": [
            make_protocol(nct_id="N1", drug="DrugA", phases=["PHASE3"], enrollment=400,
                          lead_sponsor="Alpha Co"),
        ]})
        report = run_backtest(seeds, fetch_fn=fetch)
        assert report.n_seeds == 1
        assert report.lead_drug_accuracy == 1.0
