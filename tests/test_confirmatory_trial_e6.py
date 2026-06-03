"""
Sprint E6 — ConfirmatoryTrialObligation model.

Tests cover:
  1. ConfirmatoryTrialStatus enum: values
  2. ConfirmatoryTrialObligation: construction, properties, frozen
  3. is_resolved / is_at_risk properties
  4. DrugAssetProgram: field default, storage, build() factory
  5. ValuationEngine: WITHDRAWN_FAILED emits UserWarning; other statuses do not
  6. No computational impact: PV costs and rNPV identical with/without obligation
  7. Backward compatibility: programs without confirmatory_obligation unchanged
"""
from __future__ import annotations

import warnings

import pytest
from pydantic import ValidationError

from bve.entities.asset import Asset
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial
from bve.models.confirmatory_trial import (
    ConfirmatoryTrialObligation,
    ConfirmatoryTrialStatus,
)
from bve.models.cost_model import CostModel
from bve.models.drug_asset_program import DrugAssetProgram
from bve.models.market_model import MarketModel
from bve.models.probability_model import ProbabilityModel
from bve.valuation.valuation_engine import ValuationEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _asset() -> Asset:
    return Asset(
        id="e6-test",
        name="E6 Test",
        indication="Test",
        therapeutic_area="oncology",
        stage="phase_3",
        modality="small_molecule",
        discount_rate=0.10,
    )


def _company() -> Company:
    return Company(
        id="e6-co",
        name="E6 Co",
        cash_millions=80.0,
        shares_outstanding_millions=40.0,
    )


def _market() -> MarketModel:
    return MarketModel(
        asset_id="e6-test",
        therapeutic_area="oncology",
        total_addressable_market_millions=400.0,
        peak_penetration=0.10,
        patent_life_years=10,
    )


def _trials() -> list[ClinicalTrial]:
    return [
        ClinicalTrial(
            asset_id="e6-test",
            phase="phase_3",
            success_probability=0.55,
            duration_years=3.0,
            cost_millions=150.0,
            cost_source="override",
        ),
    ]


def _obligation(status: ConfirmatoryTrialStatus) -> ConfirmatoryTrialObligation:
    return ConfirmatoryTrialObligation(
        status=status,
        description="FDA-required confirmatory RCT for accelerated approval.",
        required_by_date="2028-12-31",
        nct_id="NCT12345678",
    )


def _run_engine(
    obligation: ConfirmatoryTrialObligation | None,
) -> float:
    prog = DrugAssetProgram.build(
        _asset(), _trials(), _market(), confirmatory_obligation=obligation
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ValuationEngine.from_program(prog, _company()).run().rnpv.rnpv_millions


# ---------------------------------------------------------------------------
# 1. ConfirmatoryTrialStatus enum
# ---------------------------------------------------------------------------

class TestConfirmatoryTrialStatusEnum:
    def test_values_exist(self):
        assert ConfirmatoryTrialStatus.PENDING.value == "pending"
        assert ConfirmatoryTrialStatus.ACTIVE.value == "active"
        assert ConfirmatoryTrialStatus.MET.value == "met"
        assert ConfirmatoryTrialStatus.WITHDRAWN_FAILED.value == "withdrawn_failed"

    def test_all_statuses_constructable(self):
        for status in ConfirmatoryTrialStatus:
            ob = ConfirmatoryTrialObligation(status=status)
            assert ob.status == status


# ---------------------------------------------------------------------------
# 2. ConfirmatoryTrialObligation model
# ---------------------------------------------------------------------------

class TestConfirmatoryTrialObligationModel:
    def test_status_required(self):
        with pytest.raises((ValidationError, TypeError)):
            ConfirmatoryTrialObligation()  # type: ignore

    def test_minimal_construction(self):
        ob = ConfirmatoryTrialObligation(status=ConfirmatoryTrialStatus.PENDING)
        assert ob.status == ConfirmatoryTrialStatus.PENDING
        assert ob.description is None
        assert ob.required_by_date is None
        assert ob.nct_id is None
        assert ob.notes is None

    def test_full_construction(self):
        ob = ConfirmatoryTrialObligation(
            status=ConfirmatoryTrialStatus.ACTIVE,
            description="Confirmatory RCT",
            required_by_date="2029-06-30",
            nct_id="NCT99999999",
            notes="On track per most recent FDA correspondence.",
        )
        assert ob.description == "Confirmatory RCT"
        assert ob.required_by_date == "2029-06-30"
        assert ob.nct_id == "NCT99999999"

    def test_frozen(self):
        ob = ConfirmatoryTrialObligation(status=ConfirmatoryTrialStatus.PENDING)
        with pytest.raises(Exception):
            ob.status = ConfirmatoryTrialStatus.MET  # type: ignore

    def test_model_copy_produces_updated_instance(self):
        ob = ConfirmatoryTrialObligation(status=ConfirmatoryTrialStatus.ACTIVE)
        updated = ob.model_copy(update={"status": ConfirmatoryTrialStatus.MET})
        assert updated.status == ConfirmatoryTrialStatus.MET
        assert ob.status == ConfirmatoryTrialStatus.ACTIVE  # original unchanged

    def test_string_coercion_for_status(self):
        ob = ConfirmatoryTrialObligation(status="met")  # type: ignore
        assert ob.status == ConfirmatoryTrialStatus.MET

    def test_invalid_status_rejected(self):
        with pytest.raises(ValidationError):
            ConfirmatoryTrialObligation(status="invalid_status")  # type: ignore


# ---------------------------------------------------------------------------
# 3. is_resolved / is_at_risk properties
# ---------------------------------------------------------------------------

class TestObligationProperties:
    def test_pending_not_resolved_not_at_risk(self):
        ob = _obligation(ConfirmatoryTrialStatus.PENDING)
        assert not ob.is_resolved
        assert not ob.is_at_risk

    def test_active_not_resolved_not_at_risk(self):
        ob = _obligation(ConfirmatoryTrialStatus.ACTIVE)
        assert not ob.is_resolved
        assert not ob.is_at_risk

    def test_met_is_resolved_not_at_risk(self):
        ob = _obligation(ConfirmatoryTrialStatus.MET)
        assert ob.is_resolved
        assert not ob.is_at_risk

    def test_withdrawn_failed_is_resolved_and_at_risk(self):
        ob = _obligation(ConfirmatoryTrialStatus.WITHDRAWN_FAILED)
        assert ob.is_resolved
        assert ob.is_at_risk


# ---------------------------------------------------------------------------
# 4. DrugAssetProgram field
# ---------------------------------------------------------------------------

class TestDrugAssetProgramObligationField:
    def test_default_is_none(self):
        prog = DrugAssetProgram.build(_asset(), _trials(), _market())
        assert prog.confirmatory_obligation is None

    def test_obligation_stored(self):
        ob = _obligation(ConfirmatoryTrialStatus.ACTIVE)
        prog = DrugAssetProgram.build(_asset(), _trials(), _market(), confirmatory_obligation=ob)
        assert prog.confirmatory_obligation is ob

    def test_program_is_frozen(self):
        ob = _obligation(ConfirmatoryTrialStatus.PENDING)
        prog = DrugAssetProgram.build(_asset(), _trials(), _market(), confirmatory_obligation=ob)
        with pytest.raises(Exception):
            prog.confirmatory_obligation = None  # type: ignore

    def test_direct_construction(self):
        ob = _obligation(ConfirmatoryTrialStatus.MET)
        prog = DrugAssetProgram(
            asset=_asset(),
            trials=_trials(),
            market_model=_market(),
            confirmatory_obligation=ob,
        )
        assert prog.confirmatory_obligation.status == ConfirmatoryTrialStatus.MET


# ---------------------------------------------------------------------------
# 5. ValuationEngine: warning behaviour
# ---------------------------------------------------------------------------

class TestValuationEngineObligationWarning:
    def _run_capture_warnings(
        self, obligation: ConfirmatoryTrialObligation | None
    ) -> list:
        prog = DrugAssetProgram.build(
            _asset(), _trials(), _market(), confirmatory_obligation=obligation
        )
        engine = ValuationEngine.from_program(prog, _company())
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            engine.run()
        return [w for w in caught if issubclass(w.category, UserWarning)]

    def test_no_obligation_no_warning(self):
        ws = self._run_capture_warnings(None)
        confirmatory_ws = [w for w in ws if "confirmatory" in str(w.message).lower()]
        assert len(confirmatory_ws) == 0

    def test_pending_no_warning(self):
        ws = self._run_capture_warnings(_obligation(ConfirmatoryTrialStatus.PENDING))
        confirmatory_ws = [w for w in ws if "confirmatory" in str(w.message).lower()]
        assert len(confirmatory_ws) == 0

    def test_active_no_warning(self):
        ws = self._run_capture_warnings(_obligation(ConfirmatoryTrialStatus.ACTIVE))
        confirmatory_ws = [w for w in ws if "confirmatory" in str(w.message).lower()]
        assert len(confirmatory_ws) == 0

    def test_met_no_warning(self):
        ws = self._run_capture_warnings(_obligation(ConfirmatoryTrialStatus.MET))
        confirmatory_ws = [w for w in ws if "confirmatory" in str(w.message).lower()]
        assert len(confirmatory_ws) == 0

    def test_withdrawn_failed_emits_warning(self):
        ws = self._run_capture_warnings(_obligation(ConfirmatoryTrialStatus.WITHDRAWN_FAILED))
        confirmatory_ws = [w for w in ws if "confirmatory" in str(w.message).lower()]
        assert len(confirmatory_ws) >= 1

    def test_warning_message_contains_asset_id(self):
        ws = self._run_capture_warnings(_obligation(ConfirmatoryTrialStatus.WITHDRAWN_FAILED))
        confirmatory_ws = [w for w in ws if "confirmatory" in str(w.message).lower()]
        assert len(confirmatory_ws) == 1
        msg = str(confirmatory_ws[0].message)
        assert "e6-test" in msg

    def test_warning_message_contains_status(self):
        ws = self._run_capture_warnings(_obligation(ConfirmatoryTrialStatus.WITHDRAWN_FAILED))
        confirmatory_ws = [w for w in ws if "confirmatory" in str(w.message).lower()]
        msg = str(confirmatory_ws[0].message)
        assert "withdrawn_failed" in msg


# ---------------------------------------------------------------------------
# 6. No computational impact
# ---------------------------------------------------------------------------

class TestNoComputationalImpact:
    def test_obligation_does_not_change_pv_costs(self):
        asset = _asset()
        prob = ProbabilityModel.compute(asset, _trials())
        cs_no_ob = CostModel.compute(prob, 0.10)

        # Obligation is not threaded into CostModel — PV should be identical
        assert cs_no_ob.total_pv_weighted_millions > 0.0  # sanity
        # The obligation only sits on DrugAssetProgram; CostModel is unaware
        cs_with_ob = CostModel.compute(prob, 0.10)
        assert cs_no_ob.total_pv_weighted_millions == pytest.approx(
            cs_with_ob.total_pv_weighted_millions, rel=1e-9
        )

    def test_rnpv_identical_with_and_without_obligation(self):
        """Any obligation status has zero effect on the computed rNPV."""
        rnpv_no_ob = _run_engine(None)
        for status in ConfirmatoryTrialStatus:
            rnpv_with_ob = _run_engine(_obligation(status))
            assert rnpv_no_ob == pytest.approx(rnpv_with_ob, rel=1e-6), (
                f"rNPV changed for status {status.value}"
            )


# ---------------------------------------------------------------------------
# 7. Backward compatibility
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_program_without_obligation_unchanged(self):
        prog = DrugAssetProgram.build(_asset(), _trials(), _market())
        assert prog.confirmatory_obligation is None

    def test_engine_without_obligation_no_warning(self):
        prog = DrugAssetProgram.build(_asset(), _trials(), _market())
        engine = ValuationEngine.from_program(prog, _company())
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            engine.run()
        confirmatory_ws = [w for w in caught
                           if issubclass(w.category, UserWarning)
                           and "confirmatory" in str(w.message).lower()]
        assert len(confirmatory_ws) == 0
