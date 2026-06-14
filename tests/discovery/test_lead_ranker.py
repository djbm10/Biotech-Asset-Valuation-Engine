"""Tests for lead-asset ranking + tiering."""
from __future__ import annotations

from bve.discovery.program_cluster import CandidateProgram
from bve.discovery.lead_ranker import rank_leads, score_program
from bve.discovery.sponsor_trials import TrialRecord


def _prog(drug, phase, *, n=1, enroll=None, lead=False, status="RECRUITING", title=""):
    trials = tuple(
        TrialRecord(nct_id=f"NCT{i}", phase=phase, status=status, title=title,
                    enrollment=enroll, sponsor_is_lead=lead, drug_names=(drug,))
        for i in range(n)
    )
    return CandidateProgram(
        drug=drug, drug_key=drug.lower(), trials=trials, max_phase=phase,
        n_trials=n, enrollment_max=enroll, sponsor_is_lead=lead,
    )


class TestScoreProgram:
    def test_phase3_beats_phase1(self):
        s3, _ = score_program(_prog("A", "phase_3"))
        s1, _ = score_program(_prog("B", "phase_1"))
        assert s3 > s1

    def test_registrational_enrollment_bonus(self):
        big, _ = score_program(_prog("A", "phase_3", enroll=500))
        small, _ = score_program(_prog("A", "phase_3", enroll=50))
        assert big > small

    def test_sponsor_is_lead_bonus(self):
        led, _ = score_program(_prog("A", "phase_2", lead=True))
        not_led, _ = score_program(_prog("A", "phase_2", lead=False))
        assert led > not_led

    def test_corroboration_bonus(self):
        many, _ = score_program(_prog("A", "phase_2", n=3))
        one, _ = score_program(_prog("A", "phase_2", n=1))
        assert many > one

    def test_recency_bonus(self):
        active, _ = score_program(_prog("A", "phase_2", status="RECRUITING"))
        done, _ = score_program(_prog("A", "phase_2", status="COMPLETED"))
        assert active > done

    def test_components_present(self):
        _, comp = score_program(_prog("A", "phase_3"))
        assert set(comp) == {"phase", "registrational", "sponsor_is_lead", "recency", "corroboration"}


class TestRankLeads:
    def test_none_when_empty(self):
        assert rank_leads([]) is None

    def test_single_program_is_high_tier(self):
        lead = rank_leads([_prog("Solo", "phase_2")])
        assert lead is not None
        assert lead.tier == "high"
        assert lead.confidence == 1.0

    def test_picks_highest_phase(self):
        lead = rank_leads([_prog("Early", "phase_1"), _prog("Late", "phase_3")])
        assert lead.program.drug == "Late"

    def test_clear_winner_high_tier(self):
        lead = rank_leads([_prog("Late", "phase_3", lead=True, enroll=500), _prog("Early", "phase_1")])
        assert lead.tier == "high"
        assert lead.margin >= 0.20

    def test_two_close_late_stage_not_high(self):
        # Two near-identical Phase 3 programs → small margin → not auto-high.
        lead = rank_leads([_prog("A", "phase_3"), _prog("B", "phase_3")])
        assert lead.tier in ("medium", "low")
        assert lead.margin < 0.20

    def test_margin_is_top_minus_runner_up(self):
        progs = [_prog("A", "phase_3", lead=True, enroll=500), _prog("B", "phase_2")]
        lead = rank_leads(progs)
        top, _ = score_program(progs[0])
        run, _ = score_program(progs[1])
        assert abs(lead.margin - round(top - run, 4)) < 1e-6
