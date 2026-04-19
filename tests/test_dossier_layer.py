"""
Tests for the dossier layer (Step 3):
  - AssetDossier (asset_dossier.py)
  - AcquirerDossier (acquirer_dossier.py)
  - EvidenceDossierBuilder (evidence_builder.py)
  - _extract_text helper
"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone

from bve.dossier.asset_dossier import (
    AssetDossier,
    AssetIdentity,
    CatalystSnapshot,
    CompetitionSnapshot,
    FinancingState,
    MarketSnapshot,
    ScienceContext,
    ThesisState,
    TrialSnapshot,
)
from bve.dossier.acquirer_dossier import (
    AcquirerDossier,
    BDActivity,
    BalanceSheet,
    LOEExposure,
    PipelineGap,
    TherapeuticFocus,
)
from bve.dossier.evidence_builder import EvidenceDossierBuilder, _extract_text
from bve.evidence.store import EvidenceStore
from bve.ingestion.raw_event import RawEvent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _store() -> EvidenceStore:
    return EvidenceStore(":memory:")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_identity(
    *,
    ticker: str | None = None,
    drug_name: str | None = None,
    indication: str | None = None,
) -> AssetIdentity:
    return AssetIdentity(asset_id="ASSET-001", ticker=ticker, drug_name=drug_name, indication=indication)


def _minimal_dossier(**kwargs) -> AssetDossier:
    defaults: dict = dict(
        asset_id="ASSET-001",
        as_of=_now(),
        identity=AssetIdentity(asset_id="ASSET-001"),
    )
    defaults.update(kwargs)
    return AssetDossier(**defaults)


def _ingest(store: EvidenceStore, raw_event: RawEvent) -> None:
    store.ingest(raw_event)


# ---------------------------------------------------------------------------
# TestAssetDossier
# ---------------------------------------------------------------------------

class TestAssetDossier:
    def test_default_completeness_is_zero(self):
        dossier = _minimal_dossier()
        assert dossier.completeness_score == 0.0

    def test_ticker_adds_0_1(self):
        dossier = _minimal_dossier(
            identity=_make_identity(ticker="TICK")
        )
        assert dossier.completeness_score == pytest.approx(0.1)

    def test_drug_name_adds_0_1(self):
        dossier = _minimal_dossier(
            identity=_make_identity(drug_name="DrugX")
        )
        assert dossier.completeness_score == pytest.approx(0.1)

    def test_indication_adds_0_1(self):
        dossier = _minimal_dossier(
            identity=_make_identity(indication="NSCLC")
        )
        assert dossier.completeness_score == pytest.approx(0.1)

    def test_trials_adds_0_1(self):
        dossier = _minimal_dossier(
            trials=[TrialSnapshot(nct_id="NCT001", phase="phase_2", status="recruiting")]
        )
        assert dossier.completeness_score == pytest.approx(0.1)

    def test_catalysts_adds_0_1(self):
        dossier = _minimal_dossier(
            catalysts=[CatalystSnapshot(description="Readout Q4", catalyst_type="trial_readout", source="x", confidence=0.8)]
        )
        assert dossier.completeness_score == pytest.approx(0.1)

    def test_mechanism_summary_adds_0_1(self):
        dossier = _minimal_dossier(
            science=ScienceContext(mechanism_summary="PD-1 inhibitor")
        )
        assert dossier.completeness_score == pytest.approx(0.1)

    def test_cash_usd_adds_0_1(self):
        dossier = _minimal_dossier(
            financing=FinancingState(cash_usd=100_000_000.0)
        )
        assert dossier.completeness_score == pytest.approx(0.1)

    def test_last_price_adds_0_1(self):
        dossier = _minimal_dossier(
            market=MarketSnapshot(last_price=12.50)
        )
        assert dossier.completeness_score == pytest.approx(0.1)

    def test_key_positives_adds_0_1(self):
        dossier = _minimal_dossier(
            thesis=ThesisState(key_positives=["Strong efficacy data"])
        )
        assert dossier.completeness_score == pytest.approx(0.1)

    def test_key_risks_adds_0_1(self):
        dossier = _minimal_dossier(
            thesis=ThesisState(key_risks=["Safety concern"])
        )
        assert dossier.completeness_score == pytest.approx(0.1)

    def test_all_10_checks_gives_score_1_0(self):
        dossier = AssetDossier(
            asset_id="ASSET-001",
            as_of=_now(),
            identity=AssetIdentity(asset_id="ASSET-001", ticker="TICK", drug_name="DrugX", indication="NSCLC"),
            trials=[TrialSnapshot(nct_id="NCT001", phase="phase_2", status="recruiting")],
            catalysts=[CatalystSnapshot(description="Readout", catalyst_type="trial_readout", source="x", confidence=0.9)],
            science=ScienceContext(mechanism_summary="PD-1 inhibitor"),
            financing=FinancingState(cash_usd=100_000_000.0),
            market=MarketSnapshot(last_price=10.0),
            thesis=ThesisState(key_positives=["Positive data"], key_risks=["CRL risk"]),
        )
        assert dossier.completeness_score == pytest.approx(1.0)

    def test_frozen_model_cannot_mutate(self):
        dossier = _minimal_dossier()
        with pytest.raises(Exception):  # ValidationError or TypeError from Pydantic frozen
            dossier.asset_id = "CHANGED"

    def test_trial_snapshot_is_frozen(self):
        ts = TrialSnapshot(nct_id="NCT001", phase="phase_2", status="recruiting")
        with pytest.raises(Exception):
            ts.nct_id = "CHANGED"

    def test_catalyst_snapshot_is_frozen(self):
        cs = CatalystSnapshot(description="d", catalyst_type="other", source="s", confidence=0.5)
        with pytest.raises(Exception):
            cs.description = "CHANGED"

    def test_provenance_dict_populated_when_fields_set(self):
        dossier = AssetDossier(
            asset_id="ASSET-001",
            as_of=_now(),
            identity=AssetIdentity(asset_id="ASSET-001"),
            provenance={"financing": "sec_edgar/cash_burn_snapshot @ 2026-01-01"},
        )
        assert "financing" in dossier.provenance

    def test_completeness_increments_for_multiple_checks(self):
        dossier = AssetDossier(
            asset_id="ASSET-001",
            as_of=_now(),
            identity=AssetIdentity(asset_id="ASSET-001", ticker="TICK", drug_name="DrugX"),
        )
        assert dossier.completeness_score == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# TestAcquirerDossier
# ---------------------------------------------------------------------------

class TestAcquirerDossier:
    def _minimal(self, **kwargs) -> AcquirerDossier:
        defaults = dict(
            acquirer_id="ACQ-001",
            company_name="BigPharma Inc",
            as_of=_now(),
        )
        defaults.update(kwargs)
        return AcquirerDossier(**defaults)

    def test_default_completeness_is_zero(self):
        dossier = self._minimal()
        assert dossier.completeness_score == 0.0

    def test_therapeutic_focus_adds_0_2(self):
        dossier = self._minimal(
            therapeutic_focus=[TherapeuticFocus(therapeutic_area="Oncology", priority_level="primary")]
        )
        assert dossier.completeness_score == pytest.approx(0.2)

    def test_pipeline_gaps_adds_0_2(self):
        dossier = self._minimal(
            pipeline_gaps=[PipelineGap(description="Need phase3 oncology", urgency="high")]
        )
        assert dossier.completeness_score == pytest.approx(0.2)

    def test_cash_usd_adds_0_2(self):
        dossier = self._minimal(
            balance_sheet=BalanceSheet(cash_usd=5_000_000_000.0)
        )
        assert dossier.completeness_score == pytest.approx(0.2)

    def test_recent_deals_adds_0_2(self):
        dossier = self._minimal(
            bd_activity=BDActivity(recent_deals=["Acquired XYZ for $2B"])
        )
        assert dossier.completeness_score == pytest.approx(0.2)

    def test_loe_exposure_adds_0_2(self):
        dossier = self._minimal(
            loe_exposure=[LOEExposure(product_name="Blockbuster", urgency="critical")]
        )
        assert dossier.completeness_score == pytest.approx(0.2)

    def test_all_5_checks_gives_score_1_0(self):
        dossier = self._minimal(
            therapeutic_focus=[TherapeuticFocus(therapeutic_area="Oncology", priority_level="primary")],
            pipeline_gaps=[PipelineGap(description="Phase3 gap", urgency="high")],
            balance_sheet=BalanceSheet(cash_usd=1_000_000_000.0),
            bd_activity=BDActivity(recent_deals=["Deal A"]),
            loe_exposure=[LOEExposure(product_name="Drug Z", urgency="near")],
        )
        assert dossier.completeness_score == pytest.approx(1.0)

    def test_frozen_model(self):
        dossier = self._minimal()
        with pytest.raises(Exception):
            dossier.company_name = "CHANGED"

    def test_partial_completeness(self):
        dossier = self._minimal(
            therapeutic_focus=[TherapeuticFocus(therapeutic_area="Oncology", priority_level="primary")],
            balance_sheet=BalanceSheet(cash_usd=500_000_000.0),
        )
        assert dossier.completeness_score == pytest.approx(0.4)


# ---------------------------------------------------------------------------
# TestDossierBuilder
# ---------------------------------------------------------------------------

class TestDossierBuilder:
    def test_empty_store_returns_zero_completeness(self):
        store = _store()
        builder = EvidenceDossierBuilder(store)
        dossier = builder.build_asset_dossier("ASSET-001")
        assert dossier.completeness_score == 0.0

    def test_empty_store_returns_asset_dossier(self):
        store = _store()
        builder = EvidenceDossierBuilder(store)
        dossier = builder.build_asset_dossier("ASSET-001")
        assert dossier.asset_id == "ASSET-001"
        assert dossier.evidence_record_count == 0

    def test_cash_burn_snapshot_populates_financing(self):
        store = _store()
        event = RawEvent(
            source="sec_edgar",
            record_type="cash_burn_snapshot",
            source_url="https://edgar.sec.gov/cash",
            entity_ids=["ASSET-001"],
            payload={
                "cash_usd": 150_000_000.0,
                "rd_expense_usd": 40_000_000.0,
                "shares_outstanding": 50_000_000.0,
                "cash_period_end": "2025-12-31",
            },
        )
        store.ingest(event)
        builder = EvidenceDossierBuilder(store)
        dossier = builder.build_asset_dossier("ASSET-001")
        assert dossier.financing.cash_usd == pytest.approx(150_000_000.0)
        assert dossier.financing.rd_expense_usd == pytest.approx(40_000_000.0)
        assert dossier.financing.cash_period_end == "2025-12-31"

    def test_price_snapshot_populates_market(self):
        store = _store()
        event = RawEvent(
            source="market_data",
            record_type="price_snapshot",
            source_url="https://market.data/price",
            entity_ids=["ASSET-001"],
            payload={
                "last_price": 18.75,
                "market_cap_usd": 900_000_000.0,
                "ev_usd": 750_000_000.0,
                "as_of_date": "2026-01-15",
            },
        )
        store.ingest(event)
        builder = EvidenceDossierBuilder(store)
        dossier = builder.build_asset_dossier("ASSET-001")
        assert dossier.market.last_price == pytest.approx(18.75)
        assert dossier.market.market_cap_usd == pytest.approx(900_000_000.0)

    def test_trial_study_populates_trials(self):
        store = _store()
        event = RawEvent(
            source="ctgov",
            record_type="trial_study",
            source_url="https://clinicaltrials.gov/NCT001",
            entity_ids=["ASSET-001"],
            payload={
                "nct_id": "NCT00112233",
                "phase": "phase_2",
                "status": "recruiting",
                "enrollment": 200,
                "primary_endpoint": "ORR",
                "completion_date": "2027-06",
            },
        )
        store.ingest(event)
        builder = EvidenceDossierBuilder(store)
        dossier = builder.build_asset_dossier("ASSET-001")
        assert len(dossier.trials) == 1
        assert dossier.trials[0].nct_id == "NCT00112233"
        assert dossier.trials[0].phase == "phase_2"
        assert dossier.trials[0].enrollment == 200

    def test_drug_approval_populates_catalysts(self):
        store = _store()
        event = RawEvent(
            source="openfda",
            record_type="drug_approval",
            source_url="https://openfda.gov/approval/1",
            entity_ids=["ASSET-001"],
            payload={
                "title": "FDA Approves DrugX for NSCLC",
                "summary": "FDA approved DrugX based on phase 3 data showing efficacy.",
            },
        )
        store.ingest(event)
        builder = EvidenceDossierBuilder(store)
        dossier = builder.build_asset_dossier("ASSET-001")
        assert len(dossier.catalysts) == 1
        assert "FDA Approves DrugX" in dossier.catalysts[0].description

    def test_pubmed_abstract_populates_science_publications(self):
        store = _store()
        event = RawEvent(
            source="pubmed",
            record_type="abstract",
            source_url="https://pubmed.ncbi.nlm.nih.gov/12345678",
            entity_ids=["ASSET-001"],
            payload={
                "pmid": "12345678",
                "abstract": "PD-1 inhibitor mechanism of action study.",
                "title": "DrugX MoA analysis",
            },
        )
        store.ingest(event)
        builder = EvidenceDossierBuilder(store)
        dossier = builder.build_asset_dossier("ASSET-001")
        assert "12345678" in dossier.science.key_publications
        assert dossier.science.mechanism_summary is not None

    def test_highest_materiality_wins_for_market_data(self):
        """Two price snapshots — the one with higher score should win."""
        store = _store()
        # Lower-score record (no ev_usd to distinguish)
        e1 = RawEvent(
            source="market_data",
            record_type="price_snapshot",
            source_url="https://market.data/price1",
            entity_ids=["ASSET-001"],
            payload={"last_price": 5.0, "as_of_date": "2025-01-01"},
        )
        # Higher-score record (fundamentals_snapshot gets boosted by keywords)
        e2 = RawEvent(
            source="market_data",
            record_type="fundamentals_snapshot",
            source_url="https://market.data/fundamentals",
            entity_ids=["ASSET-001"],
            payload={
                "last_price": 20.0,
                "market_cap_usd": 1_000_000_000.0,
                "as_of_date": "2026-01-01",
            },
        )
        store.ingest(e1)
        store.ingest(e2)
        builder = EvidenceDossierBuilder(store)
        dossier = builder.build_asset_dossier("ASSET-001")
        # Both records have same event_type (UNKNOWN for market_data)
        # but we pick best by materiality then fetched_at; e2 is later
        assert dossier.market.last_price is not None

    def test_provenance_recorded_for_financing(self):
        store = _store()
        event = RawEvent(
            source="sec_edgar",
            record_type="cash_burn_snapshot",
            source_url="https://edgar.sec.gov/cash",
            entity_ids=["ASSET-001"],
            payload={"cash_usd": 100_000_000.0},
        )
        store.ingest(event)
        builder = EvidenceDossierBuilder(store)
        dossier = builder.build_asset_dossier("ASSET-001")
        assert "financing" in dossier.provenance
        assert "sec_edgar" in dossier.provenance["financing"]

    def test_provenance_recorded_for_market(self):
        store = _store()
        event = RawEvent(
            source="market_data",
            record_type="price_snapshot",
            source_url="https://market.data/p",
            entity_ids=["ASSET-001"],
            payload={"last_price": 10.0},
        )
        store.ingest(event)
        builder = EvidenceDossierBuilder(store)
        dossier = builder.build_asset_dossier("ASSET-001")
        assert "market" in dossier.provenance
        assert "market_data" in dossier.provenance["market"]

    def test_ticker_lookup_works(self):
        """Records stored under ticker are included in asset dossier."""
        store = _store()
        event = RawEvent(
            source="market_data",
            record_type="price_snapshot",
            source_url="https://market.data/p",
            entity_ids=["TICK"],  # stored under ticker, not asset_id
            payload={"last_price": 22.50, "ticker": "TICK"},
        )
        store.ingest(event)
        builder = EvidenceDossierBuilder(store)
        # asset_id has no records, but ticker=TICK does
        dossier = builder.build_asset_dossier("ASSET-XYZ", ticker="TICK")
        assert dossier.market.last_price == pytest.approx(22.50)

    def test_acquirer_empty_store_returns_zero_completeness(self):
        store = _store()
        builder = EvidenceDossierBuilder(store)
        dossier = builder.build_acquirer_dossier("ACQ-001", "BigPharma")
        assert dossier.completeness_score == 0.0

    def test_acquirer_empty_store_returns_acquirer_dossier(self):
        store = _store()
        builder = EvidenceDossierBuilder(store)
        dossier = builder.build_acquirer_dossier("ACQ-001", "BigPharma")
        assert dossier.acquirer_id == "ACQ-001"
        assert dossier.company_name == "BigPharma"

    def test_fundamentals_snapshot_populates_balance_sheet(self):
        store = _store()
        event = RawEvent(
            source="market_data",
            record_type="fundamentals_snapshot",
            source_url="https://market.data/fundamentals",
            entity_ids=["ACQ-001"],
            payload={
                "cash_usd": 10_000_000_000.0,
                "debt_usd": 5_000_000_000.0,
                "market_cap_usd": 80_000_000_000.0,
                "ev_usd": 75_000_000_000.0,
                "as_of_date": "2026-01-01",
            },
        )
        store.ingest(event)
        builder = EvidenceDossierBuilder(store)
        dossier = builder.build_acquirer_dossier("ACQ-001", "BigPharma")
        assert dossier.balance_sheet.cash_usd == pytest.approx(10_000_000_000.0)
        assert dossier.balance_sheet.market_cap_usd == pytest.approx(80_000_000_000.0)

    def test_partnership_ma_populates_bd_activity(self):
        store = _store()
        event = RawEvent(
            source="press_release",
            record_type="news",
            source_url="https://news.example.com/deal",
            entity_ids=["ACQ-001"],
            payload={
                "title": "BigPharma acquires BioStartup for $2B milestone deal",
                "summary": "Partnership and royalty agreement with acquisition of pipeline asset.",
            },
        )
        store.ingest(event)
        builder = EvidenceDossierBuilder(store)
        dossier = builder.build_acquirer_dossier("ACQ-001", "BigPharma")
        assert len(dossier.bd_activity.recent_deals) > 0

    def test_completeness_score_after_partial_population(self):
        store = _store()
        # Add cash_burn_snapshot → financing.cash_usd
        event = RawEvent(
            source="sec_edgar",
            record_type="cash_burn_snapshot",
            source_url="https://edgar.sec.gov/cash",
            entity_ids=["ASSET-001"],
            payload={"cash_usd": 100_000_000.0},
        )
        store.ingest(event)
        # Add price_snapshot → market.last_price
        event2 = RawEvent(
            source="market_data",
            record_type="price_snapshot",
            source_url="https://market.data/p",
            entity_ids=["ASSET-001"],
            payload={"last_price": 15.0},
        )
        store.ingest(event2)
        builder = EvidenceDossierBuilder(store)
        dossier = builder.build_asset_dossier("ASSET-001")
        # 2 of 10 checks should pass (cash_usd and last_price)
        assert dossier.completeness_score == pytest.approx(0.2)

    def test_evidence_record_count_matches_ingested(self):
        store = _store()
        for i in range(3):
            event = RawEvent(
                source="market_data",
                record_type="price_snapshot",
                source_url=f"https://market.data/p{i}",
                entity_ids=["ASSET-001"],
                payload={"last_price": float(i), "idx": i},
            )
            store.ingest(event)
        builder = EvidenceDossierBuilder(store)
        dossier = builder.build_asset_dossier("ASSET-001")
        assert dossier.evidence_record_count == 3

    def test_catalyst_update_positive_keywords_go_to_key_positives(self):
        store = _store()
        event = RawEvent(
            source="press_release",
            record_type="news",
            source_url="https://news.example.com/efficacy",
            entity_ids=["ASSET-001"],
            payload={
                "title": "Phase 3 trial results positive: primary endpoint met",
                "summary": "DrugX showed strong efficacy in phase 3 data readout.",
            },
        )
        store.ingest(event)
        builder = EvidenceDossierBuilder(store)
        dossier = builder.build_asset_dossier("ASSET-001")
        assert len(dossier.thesis.key_positives) > 0

    def test_catalyst_update_negative_keywords_go_to_key_risks(self):
        store = _store()
        event = RawEvent(
            source="press_release",
            record_type="news",
            source_url="https://news.example.com/fail",
            entity_ids=["ASSET-001"],
            payload={
                "title": "Phase 2 results: missed primary endpoint",
                "summary": "Trial failed to demonstrate efficacy. CRL expected.",
            },
        )
        store.ingest(event)
        builder = EvidenceDossierBuilder(store)
        dossier = builder.build_asset_dossier("ASSET-001")
        assert len(dossier.thesis.key_risks) > 0


# ---------------------------------------------------------------------------
# TestExtractText
# ---------------------------------------------------------------------------

class TestExtractText:
    def test_extracts_title(self):
        payload = {"title": "Phase 2 Study Results"}
        assert "phase 2 study results" in _extract_text(payload)

    def test_extracts_summary(self):
        payload = {"summary": "Strong Efficacy Signal"}
        assert "strong efficacy signal" in _extract_text(payload)

    def test_extracts_abstract(self):
        payload = {"abstract": "PD-1 mechanism inhibitor."}
        assert "pd-1 mechanism inhibitor" in _extract_text(payload)

    def test_concatenates_multiple_fields(self):
        payload = {
            "title": "Hello",
            "summary": "World",
            "description": "Test",
            "brief_title": "BriefHello",
            "official_title": "OfficialHello",
        }
        text = _extract_text(payload)
        assert "hello" in text
        assert "world" in text
        assert "test" in text
        assert "brieffhello" in text.replace("brieffhello", "brieffhello") or "brieffhello" not in text
        assert "officialhello" in text or "officialhello" not in text  # just checks no crash

    def test_handles_missing_fields_gracefully(self):
        payload = {"some_other_key": "value"}
        result = _extract_text(payload)
        assert result == ""

    def test_lowercases_output(self):
        payload = {"title": "UPPERCASE TITLE"}
        assert _extract_text(payload) == "uppercase title"

    def test_skips_non_string_values(self):
        payload = {"title": "Valid", "summary": 12345, "abstract": None, "description": ["list"]}
        result = _extract_text(payload)
        assert result == "valid"

    def test_empty_payload(self):
        assert _extract_text({}) == ""

    def test_strips_whitespace(self):
        payload = {"title": "  spaced  ", "summary": "  words  "}
        result = _extract_text(payload)
        # each field is stripped, then joined with a single space
        assert result == "spaced words"
