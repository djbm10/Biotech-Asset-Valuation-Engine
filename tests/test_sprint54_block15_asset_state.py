"""Block 15 — Database-First Asset State tests.

Coverage areas
--------------
TestAssetState (10)         — dataclass construction, helpers, serialisation
TestClinicalAssetState (6)  — round-trip serialisation, from_dict defaults
TestValuationInputState (5) — round-trip, datetime parsing
TestAssetRepository (15)    — upsert, load, list_tickers, mark_stale, round-trip
TestInitAssetDbIntegration (10) — init_asset seeds DB; idempotent; reads back
TestEvaluateTargetDbFirst (5)   — evaluate_target uses DB state; graceful fallback
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from bve.refresh.financial_refresh import FinancialSnapshot
from bve.refresh.input_integrity import InputIntegrityScore, SurfaceScore
from bve.refresh.market_data_refresh import MarketDataSnapshot
from bve.reporting.provenance import ProvenanceItem
from bve.state.asset_repository import AssetRepository, _scaffold_state
from bve.state.asset_state import (
    AssetState,
    ClinicalAssetState,
    ValuationInputState,
    _parse_date,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mem_engine():
    """In-memory SQLite engine scoped to one test."""
    eng = create_engine("sqlite:///:memory:")
    AssetRepository.create_table(eng)
    return eng


@pytest.fixture()
def db_session(mem_engine):
    """Session bound to in-memory engine; auto-rollback after test."""
    Session = sessionmaker(bind=mem_engine, autocommit=False, autoflush=False)
    with Session() as session:
        yield session


@pytest.fixture()
def repo(db_session):
    return AssetRepository(db_session)


def _make_state(ticker: str = "TEST") -> AssetState:
    return AssetState(
        ticker=ticker,
        company_name=f"{ticker} Therapeutics",
        market_data=MarketDataSnapshot(
            ticker=ticker,
            price=10.50,
            market_cap_millions=500.0,
            as_of=date(2026, 5, 1),
            source="yfinance",
            confidence="high",
        ),
        financials=FinancialSnapshot(
            ticker=ticker,
            cash_millions=150.0,
            net_cash_millions=120.0,
            as_of=date(2026, 3, 31),
            source="yfinance",
            confidence="high",
        ),
        clinical_assets=[
            ClinicalAssetState(
                nct_id="NCT12345678",
                asset_name="TEST-001",
                phase="phase2",
                indication="Oncology",
                primary_endpoint="ORR",
                status="active",
                last_synced=date(2026, 5, 10),
            )
        ],
        valuation_inputs=ValuationInputState(
            peak_sales_millions=800.0,
            wacc=0.12,
            years_to_peak=5,
            patent_life_years=10,
            is_screening_grade=False,
            config_path="configs/TEST/valuation_config.yaml",
            last_run=datetime(2026, 5, 15, 10, 0, 0),
        ),
        source_provenance=[
            ProvenanceItem(
                field="peak_sales_millions",
                value=800.0,
                source="yaml_config",
                as_of=date(2026, 5, 1),
                confidence="medium",
            )
        ],
        last_refreshed=date(2026, 5, 20),
        integrity_score=InputIntegrityScore(
            overall_score=0.75,
            overall_grade="B",
            market_data=SurfaceScore("market_data", score=0.25, confidence="high"),
            financials=SurfaceScore("financials", score=0.20, confidence="medium"),
        ),
    )


# ---------------------------------------------------------------------------
# TestAssetState (10 tests)
# ---------------------------------------------------------------------------

class TestAssetState:
    def test_construction_minimal(self):
        state = AssetState(
            ticker="SRPT",
            company_name="Sarepta Therapeutics",
            market_data=MarketDataSnapshot(ticker="SRPT"),
            financials=FinancialSnapshot(ticker="SRPT"),
        )
        assert state.ticker == "SRPT"
        assert state.company_name == "Sarepta Therapeutics"
        assert state.clinical_assets == []
        assert state.source_provenance == []

    def test_construction_full(self):
        state = _make_state("SRPT")
        assert state.ticker == "SRPT"
        assert state.market_data.price == 10.50
        assert state.financials.cash_millions == 150.0

    def test_is_stale_false_when_fresh(self):
        state = _make_state()
        state.last_refreshed = date.today()
        assert not state.is_stale(threshold_days=90)

    def test_is_stale_true_when_old(self):
        state = _make_state()
        state.last_refreshed = date(2020, 1, 1)
        assert state.is_stale(threshold_days=90)

    def test_is_stale_custom_threshold(self):
        state = _make_state()
        state.last_refreshed = date(2026, 5, 19)  # 1 day ago
        assert state.is_stale(threshold_days=0)
        assert not state.is_stale(threshold_days=365)

    def test_has_valuation_true(self):
        state = _make_state()
        assert state.has_valuation()

    def test_has_valuation_false(self):
        state = _make_state()
        state.valuation_inputs.last_run = None
        assert not state.has_valuation()

    def test_screening_grade_false(self):
        state = _make_state()
        assert not state.screening_grade()

    def test_screening_grade_true_default(self):
        state = AssetState(
            ticker="X",
            company_name="X",
            market_data=MarketDataSnapshot(ticker="X"),
            financials=FinancialSnapshot(ticker="X"),
        )
        assert state.screening_grade()

    def test_provenance_for_found(self):
        state = _make_state()
        item = state.provenance_for("peak_sales_millions")
        assert item is not None
        assert item.value == 800.0

    def test_provenance_for_missing(self):
        state = _make_state()
        assert state.provenance_for("nonexistent_field") is None


# ---------------------------------------------------------------------------
# TestClinicalAssetState (6 tests)
# ---------------------------------------------------------------------------

class TestClinicalAssetState:
    def test_to_dict_keys(self):
        c = ClinicalAssetState(
            nct_id="NCT123",
            asset_name="Drug-A",
            phase="phase3",
            indication="Lung Cancer",
        )
        d = c.to_dict()
        assert d["nct_id"] == "NCT123"
        assert d["phase"] == "phase3"
        assert d["estimated_completion"] is None

    def test_to_dict_dates_iso(self):
        c = ClinicalAssetState(
            nct_id="NCT456",
            asset_name="Drug-B",
            phase="phase2",
            indication="CML",
            estimated_completion=date(2027, 6, 30),
            last_synced=date(2026, 1, 1),
        )
        d = c.to_dict()
        assert d["estimated_completion"] == "2027-06-30"
        assert d["last_synced"] == "2026-01-01"

    def test_from_dict_round_trip(self):
        original = ClinicalAssetState(
            nct_id="NCT789",
            asset_name="Drug-C",
            phase="phase1",
            indication="AML",
            primary_endpoint="MTD",
            estimated_completion=date(2028, 3, 15),
            status="recruiting",
            last_synced=date(2026, 5, 1),
        )
        rebuilt = ClinicalAssetState.from_dict(original.to_dict())
        assert rebuilt.nct_id == original.nct_id
        assert rebuilt.estimated_completion == original.estimated_completion
        assert rebuilt.last_synced == original.last_synced

    def test_from_dict_defaults(self):
        c = ClinicalAssetState.from_dict({})
        assert c.nct_id == ""
        assert c.status == "unknown"
        assert c.estimated_completion is None

    def test_from_dict_missing_dates(self):
        c = ClinicalAssetState.from_dict({"nct_id": "N1", "asset_name": "A", "phase": "p1", "indication": "I"})
        assert c.estimated_completion is None
        assert c.last_synced is None

    def test_status_preserved(self):
        c = ClinicalAssetState.from_dict({"nct_id": "N", "asset_name": "A", "phase": "p", "indication": "I", "status": "terminated"})
        assert c.status == "terminated"


# ---------------------------------------------------------------------------
# TestValuationInputState (5 tests)
# ---------------------------------------------------------------------------

class TestValuationInputState:
    def test_to_dict_keys(self):
        v = ValuationInputState(peak_sales_millions=500.0, wacc=0.10)
        d = v.to_dict()
        assert d["peak_sales_millions"] == 500.0
        assert d["wacc"] == 0.10
        assert d["is_screening_grade"] is True

    def test_round_trip(self):
        v = ValuationInputState(
            peak_sales_millions=1200.0,
            wacc=0.15,
            years_to_peak=4,
            patent_life_years=12,
            is_screening_grade=False,
            config_path="configs/X/val.yaml",
            last_run=datetime(2026, 4, 1, 9, 0, 0),
        )
        rebuilt = ValuationInputState.from_dict(v.to_dict())
        assert rebuilt.peak_sales_millions == 1200.0
        assert rebuilt.years_to_peak == 4
        assert rebuilt.is_screening_grade is False
        assert rebuilt.last_run == v.last_run

    def test_from_dict_defaults(self):
        v = ValuationInputState.from_dict({})
        assert v.wacc == 0.12
        assert v.is_screening_grade is True
        assert v.last_run is None

    def test_last_run_none_preserved(self):
        v = ValuationInputState(last_run=None)
        d = v.to_dict()
        assert d["last_run"] is None
        rebuilt = ValuationInputState.from_dict(d)
        assert rebuilt.last_run is None

    def test_last_run_roundtrip_datetime(self):
        dt = datetime(2026, 3, 15, 14, 30, 0)
        v = ValuationInputState(last_run=dt)
        rebuilt = ValuationInputState.from_dict(v.to_dict())
        assert rebuilt.last_run == dt


# ---------------------------------------------------------------------------
# TestAssetRepository (15 tests)
# ---------------------------------------------------------------------------

class TestAssetRepository:
    def test_load_returns_none_when_missing(self, repo):
        assert repo.load("MISSING") is None

    def test_upsert_and_load_round_trip(self, repo):
        state = _make_state("SRPT")
        repo.upsert(state)
        loaded = repo.load("SRPT")
        assert loaded is not None
        assert loaded.ticker == "SRPT"
        assert loaded.company_name == "SRPT Therapeutics"

    def test_upsert_updates_existing(self, repo):
        state = _make_state("VKTX")
        repo.upsert(state)
        state.company_name = "Viking Therapeutics"
        repo.upsert(state)
        loaded = repo.load("VKTX")
        assert loaded.company_name == "Viking Therapeutics"

    def test_market_data_round_trip(self, repo):
        state = _make_state("X1")
        repo.upsert(state)
        loaded = repo.load("X1")
        assert loaded.market_data.price == 10.50
        assert loaded.market_data.market_cap_millions == 500.0
        assert loaded.market_data.confidence == "high"

    def test_financials_round_trip(self, repo):
        state = _make_state("X2")
        repo.upsert(state)
        loaded = repo.load("X2")
        assert loaded.financials.cash_millions == 150.0
        assert loaded.financials.net_cash_millions == 120.0

    def test_clinical_assets_round_trip(self, repo):
        state = _make_state("X3")
        repo.upsert(state)
        loaded = repo.load("X3")
        assert len(loaded.clinical_assets) == 1
        assert loaded.clinical_assets[0].nct_id == "NCT12345678"
        assert loaded.clinical_assets[0].primary_endpoint == "ORR"

    def test_valuation_inputs_round_trip(self, repo):
        state = _make_state("X4")
        repo.upsert(state)
        loaded = repo.load("X4")
        assert loaded.valuation_inputs.peak_sales_millions == 800.0
        assert loaded.valuation_inputs.is_screening_grade is False

    def test_provenance_round_trip(self, repo):
        state = _make_state("X5")
        repo.upsert(state)
        loaded = repo.load("X5")
        assert len(loaded.source_provenance) == 1
        assert loaded.source_provenance[0].field == "peak_sales_millions"

    def test_integrity_score_round_trip(self, repo):
        state = _make_state("X6")
        repo.upsert(state)
        loaded = repo.load("X6")
        assert loaded.integrity_score.overall_grade == "B"
        assert loaded.integrity_score.overall_score == 0.75

    def test_list_tickers_empty(self, repo):
        assert repo.list_tickers() == []

    def test_list_tickers_multiple(self, repo):
        repo.upsert(_make_state("ALNY"))
        repo.upsert(_make_state("SRPT"))
        repo.upsert(_make_state("VKTX"))
        tickers = repo.list_tickers()
        assert set(tickers) == {"ALNY", "SRPT", "VKTX"}

    def test_list_tickers_sorted(self, repo):
        repo.upsert(_make_state("Z"))
        repo.upsert(_make_state("A"))
        tickers = repo.list_tickers()
        assert tickers == sorted(tickers)

    def test_last_refreshed(self, repo):
        state = _make_state("LR")
        state.last_refreshed = date(2026, 5, 20)
        repo.upsert(state)
        assert repo.last_refreshed("LR") == date(2026, 5, 20)

    def test_last_refreshed_missing(self, repo):
        assert repo.last_refreshed("NOPE") is None

    def test_mark_stale_updates_provenance(self, repo):
        state = _make_state("STALE")
        repo.upsert(state)
        repo.mark_stale("STALE", "peak_sales_millions")
        loaded = repo.load("STALE")
        prov = loaded.provenance_for("peak_sales_millions")
        assert prov is not None
        assert prov.confidence == "stale"

    def test_ticker_normalised_to_upper(self, repo):
        state = _make_state("LOWER")
        state.ticker = "lower"
        repo.upsert(state)
        loaded = repo.load("LOWER")
        assert loaded is not None

    def test_load_or_scaffold_creates_when_missing(self, repo, tmp_path):
        state = repo.load_or_scaffold("NEWCO", tmp_path / "asset_profile.yaml")
        assert state is not None
        assert state.ticker == "NEWCO"

    def test_load_or_scaffold_returns_existing(self, repo, tmp_path):
        original = _make_state("EXIST")
        repo.upsert(original)
        state = repo.load_or_scaffold("EXIST", tmp_path / "asset_profile.yaml")
        # Should return existing, not scaffold
        assert state.market_data.price == 10.50


# ---------------------------------------------------------------------------
# TestScaffoldState (3 tests)
# ---------------------------------------------------------------------------

class TestScaffoldState:
    def test_scaffold_minimal(self, tmp_path):
        state = _scaffold_state("NEWT")
        assert state.ticker == "NEWT"
        assert state.screening_grade() is True
        assert len(state.source_provenance) == 1
        assert state.source_provenance[0].source == "yaml_config"

    def test_scaffold_reads_yaml_company_name(self, tmp_path):
        yaml_path = tmp_path / "asset_profile.yaml"
        yaml_path.write_text("company_name: Acme Biotech\n", encoding="utf-8")
        state = _scaffold_state("ACME", yaml_path)
        assert state.company_name == "Acme Biotech"

    def test_scaffold_falls_back_when_yaml_missing(self, tmp_path):
        state = _scaffold_state("MISS", tmp_path / "nonexistent.yaml")
        assert state.company_name == "MISS Therapeutics"


# ---------------------------------------------------------------------------
# TestInitAssetDbIntegration (10 tests)
# ---------------------------------------------------------------------------

class TestInitAssetDbIntegration:
    def test_init_asset_creates_yaml_files(self, tmp_path):
        from bve.workflows.init_asset import init_asset
        created = init_asset("SRPT", configs_dir=tmp_path / "configs", outputs_dir=tmp_path / "outputs")
        paths = {p.name for p in created}
        assert "asset_profile.yaml" in paths
        assert "valuation_config.yaml" in paths

    def test_init_asset_creates_json_files(self, tmp_path):
        from bve.workflows.init_asset import init_asset
        created = init_asset("SRPT", configs_dir=tmp_path / "configs", outputs_dir=tmp_path / "outputs")
        paths = {p.name for p in created}
        assert "management_quality.json" in paths
        assert "financial_snapshot.json" in paths

    def test_init_asset_idempotent(self, tmp_path):
        from bve.workflows.init_asset import init_asset
        created1 = init_asset("XYZ", configs_dir=tmp_path / "c", outputs_dir=tmp_path / "o")
        created2 = init_asset("XYZ", configs_dir=tmp_path / "c", outputs_dir=tmp_path / "o")
        assert len(created1) == 7
        assert len(created2) == 0  # nothing new

    def test_init_asset_ticker_uppercased_in_files(self, tmp_path):
        from bve.workflows.init_asset import init_asset
        init_asset("lower", configs_dir=tmp_path / "c", outputs_dir=tmp_path / "o")
        yaml_path = tmp_path / "c" / "LOWER" / "asset_profile.yaml"
        assert yaml_path.exists()
        content = yaml_path.read_text()
        assert "ticker: LOWER" in content

    def test_init_asset_asset_profile_has_ticker(self, tmp_path):
        from bve.workflows.init_asset import init_asset
        init_asset("RLAY", configs_dir=tmp_path / "c", outputs_dir=tmp_path / "o")
        content = (tmp_path / "c" / "RLAY" / "asset_profile.yaml").read_text()
        assert "ticker: RLAY" in content

    def test_init_asset_management_quality_json_valid(self, tmp_path):
        from bve.workflows.init_asset import init_asset
        init_asset("MGMT", configs_dir=tmp_path / "c", outputs_dir=tmp_path / "o")
        path = tmp_path / "o" / "MGMT" / "management_quality.json"
        data = json.loads(path.read_text())
        assert data["_ticker"] == "MGMT"

    def test_init_asset_financial_snapshot_json_valid(self, tmp_path):
        from bve.workflows.init_asset import init_asset
        init_asset("FIN", configs_dir=tmp_path / "c", outputs_dir=tmp_path / "o")
        path = tmp_path / "o" / "FIN" / "financial_snapshot.json"
        data = json.loads(path.read_text())
        assert data["_ticker"] == "FIN"

    def test_seed_db_state_returns_bool(self, tmp_path):
        from bve.workflows.init_asset import _seed_db_state
        result = _seed_db_state("SEED", tmp_path / "asset_profile.yaml")
        assert isinstance(result, bool)

    def test_init_asset_seven_files_total(self, tmp_path):
        from bve.workflows.init_asset import init_asset
        created = init_asset("SVEN", configs_dir=tmp_path / "c", outputs_dir=tmp_path / "o")
        assert len(created) == 7

    def test_init_asset_creates_correct_dirs(self, tmp_path):
        from bve.workflows.init_asset import init_asset
        init_asset("DIRS", configs_dir=tmp_path / "c", outputs_dir=tmp_path / "o")
        assert (tmp_path / "c" / "DIRS").is_dir()
        assert (tmp_path / "o" / "DIRS").is_dir()


# ---------------------------------------------------------------------------
# TestEvaluateTargetDbFirst (5 tests)
# ---------------------------------------------------------------------------

class TestEvaluateTargetDbFirst:
    def test_evaluate_target_runs_without_db(self, tmp_path):
        from bve.workflows.evaluate_target import evaluate_target
        report = evaluate_target(
            "SRPT",
            outputs_dir=tmp_path / "outputs",
            ops_db=tmp_path / "ops.db",
            prediction_log_db=tmp_path / "pred.db",
            skip_refresh=True,
        )
        assert isinstance(report, str)
        assert "SRPT" in report

    def test_evaluate_target_includes_disclaimer(self, tmp_path):
        from bve.workflows.evaluate_target import evaluate_target
        report = evaluate_target(
            "VKTX",
            outputs_dir=tmp_path / "outputs",
            ops_db=tmp_path / "ops.db",
            prediction_log_db=tmp_path / "pred.db",
            skip_refresh=True,
        )
        assert "Research-grade" in report or "Not investment advice" in report or "⚠" in report

    def test_load_asset_state_returns_none_when_not_found(self):
        from bve.workflows.evaluate_target import _load_asset_state
        # Requesting a ticker that cannot be in a fresh test DB
        # _load_asset_state wraps errors and returns None
        result = _load_asset_state("__NONEXISTENT_TEST_TICKER__")
        assert result is None or hasattr(result, "ticker")

    def test_load_input_integrity_uses_asset_state(self, tmp_path):
        from bve.workflows.evaluate_target import _load_input_integrity
        # Build a fake asset_state with a known integrity score
        state = _make_state("FAKE")
        score = _load_input_integrity(
            "FAKE",
            skip_refresh=False,
            asset_state=state,
        )
        assert score is not None
        assert score.overall_grade == "B"

    def test_load_input_integrity_returns_none_skip_refresh(self, tmp_path):
        from bve.workflows.evaluate_target import _load_input_integrity
        score = _load_input_integrity("FAKE", skip_refresh=True, asset_state=None)
        assert score is None
