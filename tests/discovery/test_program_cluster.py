"""Tests for trial → program clustering."""
from __future__ import annotations

from tests.discovery.conftest import make_protocol

from bve.discovery.program_cluster import cluster_programs
from bve.discovery.sponsor_trials import parse_protocol


def _recs(*protos):
    return [parse_protocol(p, "Acme Therapeutics") for p in protos]


class TestClusterPrograms:
    def test_single_drug_single_program(self):
        recs = _recs(make_protocol(nct_id="NCT01", drug="DrugX", phases=["PHASE2"]))
        progs = cluster_programs(recs)
        assert len(progs) == 1
        assert progs[0].drug == "DrugX"
        assert progs[0].n_trials == 1

    def test_same_drug_across_phases_one_program_max_phase(self):
        recs = _recs(
            make_protocol(nct_id="NCT01", drug="DrugX", phases=["PHASE1"]),
            make_protocol(nct_id="NCT02", drug="DrugX", phases=["PHASE3"]),
        )
        progs = cluster_programs(recs)
        assert len(progs) == 1
        assert progs[0].n_trials == 2
        assert progs[0].max_phase == "phase_3"

    def test_two_drugs_two_programs(self):
        recs = _recs(
            make_protocol(nct_id="NCT01", drug="DrugX", phases=["PHASE2"]),
            make_protocol(nct_id="NCT02", drug="DrugY", phases=["PHASE1"]),
        )
        progs = cluster_programs(recs)
        assert len(progs) == 2

    def test_sorted_by_phase_desc(self):
        recs = _recs(
            make_protocol(nct_id="NCT01", drug="EarlyDrug", phases=["PHASE1"]),
            make_protocol(nct_id="NCT02", drug="LateDrug", phases=["PHASE3"]),
        )
        progs = cluster_programs(recs)
        assert progs[0].drug == "LateDrug"

    def test_drug_key_ignores_formulation(self):
        recs = _recs(
            make_protocol(nct_id="NCT01", drug="DrugX hydrochloride", phases=["PHASE2"]),
            make_protocol(nct_id="NCT02", drug="DrugX", phases=["PHASE3"]),
        )
        progs = cluster_programs(recs)
        assert len(progs) == 1
        assert progs[0].max_phase == "phase_3"

    def test_trial_without_drug_skipped(self):
        recs = _recs(
            make_protocol(nct_id="NCT01", drug=None, phases=["PHASE2"]),
            make_protocol(nct_id="NCT02", drug="DrugX", phases=["PHASE2"]),
        )
        progs = cluster_programs(recs)
        assert len(progs) == 1
        assert progs[0].drug == "DrugX"

    def test_conditions_unioned(self):
        recs = _recs(
            make_protocol(nct_id="NCT01", drug="DrugX", phases=["PHASE2"], conditions=["AML"]),
            make_protocol(nct_id="NCT02", drug="DrugX", phases=["PHASE3"], conditions=["AML", "MDS"]),
        )
        progs = cluster_programs(recs)
        assert set(progs[0].conditions) == {"AML", "MDS"}

    def test_enrollment_max(self):
        recs = _recs(
            make_protocol(nct_id="NCT01", drug="DrugX", phases=["PHASE2"], enrollment=80),
            make_protocol(nct_id="NCT02", drug="DrugX", phases=["PHASE3"], enrollment=400),
        )
        progs = cluster_programs(recs)
        assert progs[0].enrollment_max == 400

    def test_sponsor_is_lead_any(self):
        recs = [
            parse_protocol(make_protocol(nct_id="NCT01", drug="DrugX", phases=["PHASE2"],
                                         lead_sponsor="Other Co"), "Acme Therapeutics"),
            parse_protocol(make_protocol(nct_id="NCT02", drug="DrugX", phases=["PHASE3"],
                                         lead_sponsor="Acme Therapeutics"), "Acme Therapeutics"),
        ]
        progs = cluster_programs(recs)
        assert progs[0].sponsor_is_lead is True

    def test_empty_input(self):
        assert cluster_programs([]) == []
