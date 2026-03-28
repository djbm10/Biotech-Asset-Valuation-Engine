"""
Sprint 9 Phase 6 — Provenance & Auditability (Tasks 9.21 + 9.22).

Task 9.21:
- ValuationOutput.assumptions_yaml_hash is populated and 12 chars
- ValuationOutput.config_hash is populated when config_path supplied
- ValuationOutput.wacc_vintage matches assumptions YAML
- ValuationOutput.analyst_overrides reflects non-default discount_rate / tax_rate
- Re-running with same inputs produces the same hash (deterministic)
- Changing the YAML would produce a different hash (structural check)

Task 9.22:
- audit_log has lineage columns: assumption_field, assumption_old/new_value,
  evidence_signal_id, review_decision_id
- Accepting a review decision with override_value populates lineage fields
- query_audit_log filters by assumption_field and signal_id
- Non-accepted decisions leave lineage columns NULL
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from bve.entities.asset import Asset, DevelopmentStage, Modality, TherapeuticArea
from bve.entities.company import Company
from bve.entities.trial import ClinicalTrial, EndpointType, TrialPhase
from bve.models.market_model import MarketModel
from bve.valuation.valuation_engine import ValuationEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine(discount_rate: float = 0.12, tax_rate: float = 0.21) -> ValuationEngine:
    asset = Asset(
        id="prov-test",
        name="PROV-TEST",
        indication="Oncology",
        therapeutic_area=TherapeuticArea.ONCOLOGY,
        stage=DevelopmentStage.PHASE_2,
        modality=Modality.SMALL_MOLECULE,
        discount_rate=discount_rate,
        effective_tax_rate=tax_rate,
    )
    company = Company(
        id="co-test",
        name="Test Co",
        ticker="TEST",
        cash_millions=100.0,
        shares_outstanding_millions=50.0,
        burn_rate_millions_per_quarter=10.0,
    )
    trials = [
        ClinicalTrial(
            id="t1",
            asset_id="prov-test",
            phase=TrialPhase.PHASE_2,
            success_probability=0.40,
            duration_years=3,
            cost_millions=80.0,
            cost_source="override",
            primary_endpoint_type=EndpointType.HARD_CLINICAL,
        ),
        ClinicalTrial(
            id="t2",
            asset_id="prov-test",
            phase=TrialPhase.PHASE_3,
            success_probability=0.65,
            duration_years=4,
            cost_millions=250.0,
            cost_source="override",
            primary_endpoint_type=EndpointType.HARD_CLINICAL,
        ),
    ]
    market = MarketModel(
        asset_id="prov-test",
        total_addressable_market_millions=1_500.0,
        peak_penetration=0.08,
        years_to_peak=5,
        patent_life_years=12,
        use_s_curve=True,
    )
    from bve.models.monte_carlo import MonteCarloParams
    return ValuationEngine(
        asset=asset,
        company=company,
        trials=trials,
        market_model=market,
        mc_params=MonteCarloParams(n_simulations=200, random_seed=42),
    )


# ---------------------------------------------------------------------------
# Task 9.21 — ValuationOutput provenance
# ---------------------------------------------------------------------------

class TestProvenanceFields:
    def test_assumptions_yaml_hash_present(self):
        out = _make_engine().run()
        assert out.assumptions_yaml_hash is not None
        assert isinstance(out.assumptions_yaml_hash, str)

    def test_assumptions_yaml_hash_is_12_chars(self):
        out = _make_engine().run()
        assert len(out.assumptions_yaml_hash) == 12

    def test_assumptions_yaml_hash_is_hex(self):
        out = _make_engine().run()
        int(out.assumptions_yaml_hash, 16)  # raises ValueError if not hex

    def test_assumptions_yaml_hash_deterministic(self):
        h1 = _make_engine().run().assumptions_yaml_hash
        h2 = _make_engine().run().assumptions_yaml_hash
        assert h1 == h2

    def test_wacc_vintage_present(self):
        out = _make_engine().run()
        assert out.wacc_vintage is not None
        assert isinstance(out.wacc_vintage, str)

    def test_wacc_vintage_matches_yaml_format(self):
        out = _make_engine().run()
        # Should be "YYYY-QN" style
        v = out.wacc_vintage
        assert "-Q" in v or len(v) >= 4, f"Unexpected wacc_vintage format: {v}"

    def test_config_hash_none_when_no_config_path(self):
        out = _make_engine().run()
        assert out.config_hash is None

    def test_config_hash_populated_when_config_path_supplied(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            f.write(b"asset:\n  id: prov-test\n")
            config_path = f.name
        engine = _make_engine()
        engine.config_path = config_path
        out = engine.run()
        assert out.config_hash is not None
        assert len(out.config_hash) == 12

    def test_config_hash_deterministic_same_file(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            f.write(b"asset:\n  id: prov-test\n")
            config_path = f.name
        h1 = _make_engine()
        h1.config_path = config_path
        h2 = _make_engine()
        h2.config_path = config_path
        assert h1.run().config_hash == h2.run().config_hash

    def test_no_overrides_when_defaults_used(self):
        out = _make_engine(discount_rate=0.12, tax_rate=0.21).run()
        # discount_rate 0.12 IS the default; no overrides expected
        dr_overrides = [o for o in out.analyst_overrides if "discount_rate" in o]
        assert len(dr_overrides) == 0

    def test_discount_rate_override_detected(self):
        out = _make_engine(discount_rate=0.14).run()
        dr_overrides = [o for o in out.analyst_overrides if "discount_rate" in o]
        assert len(dr_overrides) == 1
        assert "0.14" in dr_overrides[0]
        assert "default" in dr_overrides[0].lower()

    def test_tax_rate_override_detected(self):
        out = _make_engine(tax_rate=0.15).run()
        tax_overrides = [o for o in out.analyst_overrides if "tax_rate" in o]
        assert len(tax_overrides) == 1
        assert "0.15" in tax_overrides[0]

    def test_analyst_overrides_is_list(self):
        out = _make_engine().run()
        assert isinstance(out.analyst_overrides, list)

    def test_provenance_fields_serializable(self):
        """Provenance fields must round-trip through model_dump."""
        out = _make_engine().run()
        d = out.model_dump()
        assert "assumptions_yaml_hash" in d
        assert "config_hash" in d
        assert "wacc_vintage" in d
        assert "analyst_overrides" in d


# ---------------------------------------------------------------------------
# Task 9.22 — Audit log signal lineage
# ---------------------------------------------------------------------------

class TestAuditLogLineage:
    def _make_store(self):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        return KnowledgeStore(":memory:")

    def _make_decision(self, decision_type: str = "accepted", override=42.0):
        from datetime import datetime, timezone
        from bve.intelligence.knowledge_layer import ReviewDecision
        return ReviewDecision(
            id="dec-001",
            proposal_id="prop-001",
            run_id="run-001",
            decision=decision_type,
            reviewer_id="analyst-1",
            reviewed_at=datetime.now(timezone.utc),
            override_value=override if decision_type == "accepted" else None,
            rationale="Test rationale",
        )

    def _make_source_trace(self):
        from bve.intelligence.knowledge_layer import SourceTrace
        return SourceTrace(source_type="test", source_ref="test-ref")

    def test_audit_log_has_lineage_columns(self):
        store = self._make_store()
        # Insert a decision so a row exists
        from bve.intelligence.knowledge_layer import ReviewDecision
        from datetime import datetime, timezone

        decision = self._make_decision()
        trace = self._make_source_trace()
        store.add_review_decision(decision, company_id="co-1", asset_id="a-1", source_trace=trace)

        rows = store.query_audit_log()
        assert len(rows) == 1
        row = rows[0]
        # Lineage columns must be present (may be None for non-accepted or no proposal)
        assert "assumption_field" in row
        assert "assumption_old_value" in row
        assert "assumption_new_value" in row
        assert "evidence_signal_id" in row
        assert "review_decision_id" in row

    def test_accepted_decision_with_override_populates_lineage(self):
        store = self._make_store()
        decision = self._make_decision("accepted", override=0.45)
        trace = self._make_source_trace()
        store.add_review_decision(decision, company_id="co-1", asset_id="a-1", source_trace=trace)

        rows = store.query_audit_log()
        row = rows[0]
        assert row["assumption_field"] == "override_value"
        assert row["assumption_new_value"] == "0.45"
        assert row["review_decision_id"] == "dec-001"

    def test_rejected_decision_leaves_lineage_null(self):
        store = self._make_store()
        decision = self._make_decision("rejected", override=None)
        trace = self._make_source_trace()
        store.add_review_decision(decision, company_id="co-1", asset_id="a-1", source_trace=trace)

        rows = store.query_audit_log()
        row = rows[0]
        assert row["assumption_field"] is None
        assert row["assumption_new_value"] is None
        assert row["review_decision_id"] is None

    def test_query_filter_by_assumption_field(self):
        store = self._make_store()
        decision = self._make_decision("accepted", override=0.38)
        trace = self._make_source_trace()
        store.add_review_decision(decision, company_id="co-1", asset_id="a-1", source_trace=trace)

        filtered = store.query_audit_log(assumption_field="override_value")
        assert len(filtered) == 1

        empty = store.query_audit_log(assumption_field="nonexistent_field")
        assert len(empty) == 0

    def test_query_filter_by_signal_id(self):
        store = self._make_store()
        # Inject lineage manually via _append_audit_log to test signal_id filter
        store._append_audit_log(
            event_type="review_decision",
            entity_type="proposal",
            entity_id="prop-001",
            actor_id="analyst-1",
            action="accepted",
            payload_json="{}",
            assumption_field="phase_2_pos",
            assumption_old_value="0.32",
            assumption_new_value="0.38",
            evidence_signal_id="sig-abc",
            review_decision_id="dec-xyz",
        )
        store._conn.commit()

        filtered = store.query_audit_log(signal_id="sig-abc")
        assert len(filtered) == 1
        assert filtered[0]["assumption_field"] == "phase_2_pos"
        assert filtered[0]["assumption_old_value"] == "0.32"
        assert filtered[0]["assumption_new_value"] == "0.38"

        empty = store.query_audit_log(signal_id="sig-unknown")
        assert len(empty) == 0

    def test_lineage_append_direct_with_all_fields(self):
        store = self._make_store()
        store._append_audit_log(
            event_type="review_decision",
            entity_type="proposal",
            entity_id="prop-999",
            actor_id="system",
            action="accepted",
            payload_json='{"test": true}',
            assumption_field="phase_3_pos",
            assumption_old_value="0.60",
            assumption_new_value="0.65",
            evidence_signal_id="sig-001",
            review_decision_id="dec-001",
        )
        store._conn.commit()

        rows = store.query_audit_log(entity_id="prop-999")
        assert len(rows) == 1
        r = rows[0]
        assert r["assumption_field"] == "phase_3_pos"
        assert r["assumption_old_value"] == "0.60"
        assert r["assumption_new_value"] == "0.65"
        assert r["evidence_signal_id"] == "sig-001"
        assert r["review_decision_id"] == "dec-001"
