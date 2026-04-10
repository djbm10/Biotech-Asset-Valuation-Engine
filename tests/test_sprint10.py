"""
Sprint 10 tests — Market-Implied PoS at Universe Scale.

Covers:
  - universe_params.yaml: schema validity, all 27 tickers present, required fields
  - ops/universe_configs.py: build_program(), load_params(), _build_trials()
  - analysis/implied_pos_batch.py: ScreenRow math, run_screen() offline mode

No yfinance calls: market data patched to fixed values in all tests.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
import yaml

if TYPE_CHECKING:
    from bve.analysis.implied_pos_batch import ScreenRow

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PARAMS_PATH = Path(__file__).resolve().parents[1] / "research" / "universe_params.yaml"
UNIVERSE_TICKERS = [
    "VKTX", "ALNY", "SRPT", "KYMR", "ARVN", "RVMD", "NTLA", "BEAM", "IMVT",
    "MDGL", "CRSP", "BMRN", "VRTX", "REGN", "LLY", "RXRX", "MRNA", "FULC",
    "FATE", "OCUL", "SRRK", "IOVA", "NVAX", "PRTA", "EDIT", "AMRN", "ZYME",
]

_FAKE_FUNDAMENTALS = {
    "ticker": "VKTX",
    "name": "Viking Therapeutics",
    "market_cap_millions": 2100.0,
    "cash_millions": 450.0,
    "total_debt_millions": 0.0,
    "shares_outstanding_millions": 175.0,
    "current_price": 12.0,
    "52w_high": 18.0,
    "52w_low": 8.0,
    "beta": 1.2,
    "sector": "Healthcare",
    "industry": "Biotechnology",
}


@pytest.fixture
def raw_params() -> dict:
    with open(PARAMS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def universe_dict(raw_params) -> dict[str, dict]:
    return raw_params["universe"]


# ---------------------------------------------------------------------------
# universe_params.yaml — schema and completeness
# ---------------------------------------------------------------------------

class TestUniverseParamsYaml:

    def test_file_exists(self):
        assert PARAMS_PATH.exists(), f"Missing: {PARAMS_PATH}"

    def test_all_27_tickers_present(self, universe_dict):
        missing = [t for t in UNIVERSE_TICKERS if t not in universe_dict]
        assert missing == [], f"Missing tickers: {missing}"

    def test_no_extra_tickers(self, universe_dict):
        extra = [t for t in universe_dict if t not in UNIVERSE_TICKERS]
        assert extra == [], f"Unexpected tickers: {extra}"

    def test_required_fields_all_tickers(self, universe_dict):
        required = ["program_label", "ta", "phase", "peak_sales_millions",
                    "years_to_approval", "patent_life_years", "single_asset"]
        for ticker, entry in universe_dict.items():
            for field in required:
                assert field in entry, f"{ticker}: missing required field '{field}'"

    def test_ta_values_valid(self, universe_dict):
        valid = {"oncology", "rare_disease", "cns", "cardiovascular",
                 "immunology", "infectious_disease", "ophthalmology", "other"}
        for ticker, entry in universe_dict.items():
            ta = entry.get("ta")
            assert ta in valid, f"{ticker}: invalid ta='{ta}'"

    def test_phase_values_valid(self, universe_dict):
        valid = {"phase_1", "phase_2", "phase_3", "nda_bla", "approved"}
        for ticker, entry in universe_dict.items():
            phase = entry.get("phase")
            assert phase in valid, f"{ticker}: invalid phase='{phase}'"

    def test_peak_sales_positive(self, universe_dict):
        for ticker, entry in universe_dict.items():
            ps = entry.get("peak_sales_millions")
            assert isinstance(ps, (int, float)) and ps > 0, \
                f"{ticker}: peak_sales_millions must be > 0, got {ps}"

    def test_years_to_approval_non_negative(self, universe_dict):
        for ticker, entry in universe_dict.items():
            yrs = entry.get("years_to_approval")
            assert isinstance(yrs, (int, float)) and yrs >= 0, \
                f"{ticker}: years_to_approval must be >= 0, got {yrs}"

    def test_patent_life_reasonable(self, universe_dict):
        for ticker, entry in universe_dict.items():
            pl = entry.get("patent_life_years")
            assert isinstance(pl, (int, float)) and 1 <= pl <= 20, \
                f"{ticker}: patent_life_years={pl} outside [1, 20]"

    def test_single_asset_is_bool(self, universe_dict):
        for ticker, entry in universe_dict.items():
            sa = entry.get("single_asset")
            assert isinstance(sa, bool), f"{ticker}: single_asset must be bool"

    def test_approved_assets_zero_years_to_approval(self, universe_dict):
        for ticker, entry in universe_dict.items():
            if entry.get("phase") == "approved":
                yrs = entry.get("years_to_approval", -1)
                assert yrs == 0.0, f"{ticker}: approved phase should have years_to_approval=0"

    def test_modality_values_valid_when_present(self, universe_dict):
        valid = {"small_molecule", "biologic", "gene_therapy",
                 "cell_therapy", "adc", "rna_therapy", "other"}
        for ticker, entry in universe_dict.items():
            mod = entry.get("modality")
            if mod is not None:
                assert mod in valid, f"{ticker}: invalid modality='{mod}'"


# ---------------------------------------------------------------------------
# ops/universe_configs.py — build_program
# ---------------------------------------------------------------------------

class TestUniverseConfigs:

    def test_load_params_returns_all_tickers(self):
        from bve.ops.universe_configs import load_params
        params = load_params()
        for t in UNIVERSE_TICKERS:
            assert t in params

    def test_build_program_phase3_has_phase3_and_nda_trials(self):
        from bve.ops.universe_configs import build_program, load_params
        params = load_params()
        prog, co = build_program("VKTX", params["VKTX"])
        phases = [t.phase.value for t in prog.trials]
        assert "phase_3" in phases
        assert "nda_bla" in phases

    def test_build_program_phase2_has_3_trials(self):
        from bve.ops.universe_configs import build_program, load_params
        params = load_params()
        prog, co = build_program("KYMR", params["KYMR"])
        phases = [t.phase.value for t in prog.trials]
        assert phases == ["phase_2", "phase_3", "nda_bla"]

    def test_build_program_approved_has_no_trials(self):
        from bve.ops.universe_configs import build_program, load_params
        params = load_params()
        prog, co = build_program("MDGL", params["MDGL"])
        assert prog.trials == []

    def test_build_program_market_model_peak_sales(self):
        from bve.ops.universe_configs import build_program, load_params
        params = load_params()
        prog, co = build_program("VKTX", params["VKTX"])
        assert prog.market_model.total_addressable_market_millions == 4500.0

    def test_build_program_asset_id_matches_market_model(self):
        from bve.ops.universe_configs import build_program, load_params
        params = load_params()
        prog, co = build_program("ARVN", params["ARVN"])
        assert prog.asset.id == prog.market_model.asset_id

    def test_build_program_commercial_plan_suppressed(self):
        from bve.ops.universe_configs import build_program, load_params
        params = load_params()
        prog, co = build_program("NTLA", params["NTLA"])
        assert prog.commercial_plan.loe_source == "suppressed"

    def test_build_program_placeholder_company_when_none(self):
        from bve.ops.universe_configs import build_program, load_params
        params = load_params()
        _, co = build_program("EDIT", params["EDIT"], company=None)
        assert co.shares_outstanding_millions > 0
        assert co.ticker == "EDIT"

    def test_build_program_with_injected_company(self):
        from bve.entities.company import Company
        from bve.ops.universe_configs import build_program, load_params
        params = load_params()
        custom_co = Company(
            id="co-vktx",
            name="Viking Test",
            ticker="VKTX",
            cash_millions=500.0,
            shares_outstanding_millions=200.0,
            current_price=15.0,
        )
        _, co = build_program("VKTX", params["VKTX"], company=custom_co)
        assert co.current_price == 15.0
        assert co.cash_millions == 500.0

    def test_fetch_company_snapshot_uses_yfinance(self):
        from bve.ops.universe_configs import fetch_company_snapshot
        fake = dict(_FAKE_FUNDAMENTALS)
        # get_fundamentals is imported lazily inside fetch_company_snapshot;
        # patch at the source module so all callers see the mock.
        with patch("bve.ingestion.market_data.get_fundamentals", return_value=fake):
            co = fetch_company_snapshot("VKTX")
        assert co.ticker == "VKTX"
        assert co.current_price == 12.0
        assert co.cash_millions == 450.0
        assert co.shares_outstanding_millions == 175.0

    def test_fetch_company_snapshot_handles_yfinance_failure(self):
        from bve.ops.universe_configs import fetch_company_snapshot
        # Patch the module-level function that gets imported inside fetch_company_snapshot
        with patch("bve.ingestion.market_data.get_fundamentals",
                   side_effect=Exception("network error")):
            co = fetch_company_snapshot("VKTX")
        assert co.ticker == "VKTX"
        assert co.current_price is None
        assert co.cash_millions == 0.0

    def test_load_universe_programs_offline_builds_all(self):
        from bve.ops.universe_configs import load_universe_programs
        programs = load_universe_programs(fetch_live=False)
        assert len(programs) == 27
        for ticker in UNIVERSE_TICKERS:
            assert ticker in programs

    def test_pos_decreases_with_earlier_phase(self):
        """Phase 1 asset should have lower model_pos than Phase 3 asset (same TA)."""
        from bve.ops.universe_configs import build_program, load_params
        params = load_params()
        # NTLA is phase_1, ALNY is phase_3 — both cardiovascular/rare_disease
        prog_ph1, _ = build_program("NTLA", params["NTLA"])
        prog_ph3, _ = build_program("ALNY", params["ALNY"])
        # Compute cumulative pos manually
        pos_ph1 = 1.0
        for t in prog_ph1.trials:
            pos_ph1 *= t.success_probability
        pos_ph3 = 1.0
        for t in prog_ph3.trials:
            pos_ph3 *= t.success_probability
        assert pos_ph1 < pos_ph3


# ---------------------------------------------------------------------------
# analysis/implied_pos_batch.py — ScreenRow math + run_screen offline
# ---------------------------------------------------------------------------

class TestImpliedPosBatch:

    def test_run_screen_offline_returns_27_rows(self):
        from bve.analysis.implied_pos_batch import run_screen
        from bve.ops.weekly_runner import UNIVERSE
        rows = run_screen(UNIVERSE, fetch_live=False)
        assert len(rows) == 27

    def test_run_screen_offline_spread_is_none_when_no_price(self):
        from bve.analysis.implied_pos_batch import run_screen
        from bve.ops.weekly_runner import UNIVERSE
        rows = run_screen(UNIVERSE, fetch_live=False)
        for row in rows:
            assert row.spread_pp is None, \
                f"{row.ticker}: expected None spread (no price), got {row.spread_pp}"

    def test_run_screen_offline_model_pos_in_range(self):
        from bve.analysis.implied_pos_batch import run_screen
        from bve.ops.weekly_runner import UNIVERSE
        rows = run_screen(UNIVERSE, fetch_live=False)
        for row in rows:
            assert 0.0 <= row.model_pos <= 1.0, \
                f"{row.ticker}: model_pos={row.model_pos} out of range"

    def test_run_screen_offline_rnpv_positive_for_late_stage(self):
        from bve.analysis.implied_pos_batch import run_screen
        from bve.ops.weekly_runner import UNIVERSE
        rows = run_screen(UNIVERSE, fetch_live=False)
        # NDA/BLA assets (one review step away from approval) should have positive rNPV.
        # Phase 3 with small rare-disease markets (e.g. FULC/FSHD ~$800M peak) can be
        # negative when probability-weighted Phase 3 + NDA costs exceed the expected NPV.
        nda_stage = [r for r in rows if r.stage == "nda_bla"]
        for row in nda_stage:
            assert row.rnpv_millions > 0, \
                f"{row.ticker}: NDA/BLA asset should have positive rNPV, got {row.rnpv_millions}"

    def test_run_screen_single_asset_only_filter(self):
        from bve.analysis.implied_pos_batch import run_screen
        from bve.ops.weekly_runner import UNIVERSE
        rows = run_screen(UNIVERSE, fetch_live=False, single_asset_only=True)
        for row in rows:
            assert row.single_asset is True
            assert row.approximation_warning is None

    def test_run_screen_multi_program_names_have_warning(self):
        from bve.analysis.implied_pos_batch import run_screen
        from bve.ops.weekly_runner import UNIVERSE
        rows = run_screen(UNIVERSE, fetch_live=False)
        multi = [r for r in rows if not r.single_asset]
        # Known multi-program names
        multi_tickers = {r.ticker for r in multi}
        for expected in ["VRTX", "REGN", "LLY", "ALNY"]:
            assert expected in multi_tickers, \
                f"Expected {expected} to be flagged as multi-program"
        for row in multi:
            assert row.approximation_warning is not None

    def test_spread_formula_with_mocked_price(self):
        """When price is injected, spread = (model_pos - implied_pos) × 100."""
        from bve.analysis.implied_pos_batch import run_screen
        from bve.ops.weekly_runner import UNIVERSE

        fake = dict(_FAKE_FUNDAMENTALS)
        fake.update({"ticker": "VKTX", "current_price": 12.0,
                     "shares_outstanding_millions": 175.0,
                     "cash_millions": 450.0, "total_debt_millions": 0.0})

        with patch("bve.ingestion.market_data.get_fundamentals", return_value=fake):
            rows = run_screen(
                [e for e in UNIVERSE if e["ticker"] == "VKTX"],
                fetch_live=True,
            )

        # run_screen iterates all 27 params entries; universe list provides catalyst
        # metadata only. Find VKTX within the full result.
        assert len(rows) == 27
        row = next(r for r in rows if r.ticker == "VKTX")
        assert row.ticker == "VKTX"
        assert row.ev_millions is not None
        # ev = market_cap - net_cash = 12 × 175 - (450 - 0) = 2100 - 450 = 1650
        expected_ev = round(12.0 * 175.0 - 450.0, 1)
        assert abs(row.ev_millions - expected_ev) < 1.0, \
            f"EV={row.ev_millions}, expected ~{expected_ev}"

        if row.implied_pos is not None and row.spread_pp is not None:
            # Verify spread formula: spread_pp = (model_pos - implied_pos) × 100
            computed = round((row.model_pos - row.implied_pos) * 100, 1)
            assert abs(row.spread_pp - computed) < 0.5, \
                f"spread_pp={row.spread_pp} != {computed}"

    def test_run_screen_sort_by_spread(self):
        from bve.analysis.implied_pos_batch import run_screen
        from bve.ops.weekly_runner import UNIVERSE
        rows = run_screen(UNIVERSE, fetch_live=False, sort_by="spread")
        # Without prices all spreads are None — rows should all be returned
        assert len(rows) == 27

    def test_run_screen_sort_by_rnpv(self):
        from bve.analysis.implied_pos_batch import run_screen
        from bve.ops.weekly_runner import UNIVERSE
        rows = run_screen(UNIVERSE, fetch_live=False, sort_by="rnpv")
        rnpvs = [r.rnpv_millions for r in rows]
        for a, b in zip(rnpvs, rnpvs[1:]):
            assert a >= b, f"rNPV not descending: {a} < {b}"

    def test_screen_row_is_undervalued_property(self):
        from bve.analysis.implied_pos_batch import ScreenRow
        row = ScreenRow(
            ticker="TEST", program_label="Test", stage="phase_2", ta="oncology",
            model_pos=0.60, implied_pos=0.40, spread_pp=20.0,
            rnpv_millions=1000.0, ev_millions=800.0, acquisition_discount_pct=25.0,
            next_catalyst="Ph2 readout", catalyst_date=None, days_to_catalyst=None,
            single_asset=True, approximation_warning=None,
        )
        assert row.is_undervalued is True

    def test_screen_row_is_overvalued(self):
        from bve.analysis.implied_pos_batch import ScreenRow
        row = ScreenRow(
            ticker="TEST", program_label="Test", stage="phase_2", ta="oncology",
            model_pos=0.40, implied_pos=0.65, spread_pp=-25.0,
            rnpv_millions=800.0, ev_millions=1200.0, acquisition_discount_pct=-33.3,
            next_catalyst="Ph2 readout", catalyst_date=None, days_to_catalyst=None,
            single_asset=True, approximation_warning=None,
        )
        assert row.is_undervalued is False

    def test_screen_row_is_undervalued_none_when_no_implied(self):
        from bve.analysis.implied_pos_batch import ScreenRow
        row = ScreenRow(
            ticker="TEST", program_label="Test", stage="phase_2", ta="oncology",
            model_pos=0.50, implied_pos=None, spread_pp=None,
            rnpv_millions=500.0, ev_millions=None, acquisition_discount_pct=None,
            next_catalyst="readout", catalyst_date=None, days_to_catalyst=None,
            single_asset=True, approximation_warning=None,
        )
        assert row.is_undervalued is None

    def test_acquisition_discount_formula(self):
        """ACQ_DISC = (rNPV - EV) / |EV| × 100."""
        from bve.analysis.implied_pos_batch import run_screen
        from bve.ops.weekly_runner import UNIVERSE

        fake = dict(_FAKE_FUNDAMENTALS)
        fake.update({"ticker": "VKTX", "current_price": 12.0,
                     "shares_outstanding_millions": 175.0,
                     "cash_millions": 450.0, "total_debt_millions": 0.0})

        with patch("bve.ingestion.market_data.get_fundamentals", return_value=fake):
            rows = run_screen(
                [e for e in UNIVERSE if e["ticker"] == "VKTX"],
                fetch_live=True,
            )
        row = rows[0]
        if row.ev_millions and row.acquisition_discount_pct is not None:
            expected = round((row.rnpv_millions - row.ev_millions) / abs(row.ev_millions) * 100, 1)
            assert abs(row.acquisition_discount_pct - expected) < 0.5

    def test_all_tickers_have_program_label(self):
        from bve.analysis.implied_pos_batch import run_screen
        from bve.ops.weekly_runner import UNIVERSE
        rows = run_screen(UNIVERSE, fetch_live=False)
        for row in rows:
            assert row.program_label, f"{row.ticker}: missing program_label"

    def test_phase1_model_pos_lower_than_phase3(self):
        from bve.analysis.implied_pos_batch import run_screen
        from bve.ops.weekly_runner import UNIVERSE
        rows = run_screen(UNIVERSE, fetch_live=False)
        pos_by_ticker = {r.ticker: r.model_pos for r in rows}
        # NTLA (phase_1) vs ARVN (phase_3) — same oncology/rare base rates context
        assert pos_by_ticker["NTLA"] < pos_by_ticker["ARVN"], \
            "Phase 1 asset should have lower model_pos than Phase 3"


# ---------------------------------------------------------------------------
# Task 10.4 — screen_snapshots KnowledgeStore persistence
# ---------------------------------------------------------------------------

class TestScreenSnapshots:

    def _make_row(
        self,
        ticker: str = "VKTX",
        spread: float = 15.0,
        asset_id: str = "",
    ) -> "ScreenRow":
        from bve.analysis.implied_pos_batch import ScreenRow
        return ScreenRow(
            ticker=ticker,
            program_label=f"{ticker} program",
            stage="phase_2",
            ta="oncology",
            model_pos=0.60,
            implied_pos=0.45,
            spread_pp=spread,
            rnpv_millions=1200.0,
            ev_millions=900.0,
            acquisition_discount_pct=33.3,
            next_catalyst="Ph2 readout Q3 2026",
            catalyst_date=None,
            days_to_catalyst=None,
            single_asset=True,
            approximation_warning=None,
            data_date=date(2026, 3, 28),
            asset_id=asset_id,
        )

    def test_write_and_read_back(self, tmp_path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        store = KnowledgeStore(tmp_path / "test.db")
        rows = [self._make_row("VKTX", 15.0), self._make_row("KYMR", 8.5)]
        n = store.write_screen_snapshots(rows)
        assert n == 2

        result = store.get_screen_snapshots()
        assert len(result) == 2
        tickers = {r["ticker"] for r in result}
        assert tickers == {"VKTX", "KYMR"}
        store.close()

    def test_upsert_replaces_same_ticker_date(self, tmp_path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        store = KnowledgeStore(tmp_path / "test.db")
        row = self._make_row("VKTX", 15.0)
        store.write_screen_snapshots([row])
        # Write again same ticker same date — should replace, not duplicate
        row2 = self._make_row("VKTX", 20.0)
        store.write_screen_snapshots([row2])
        result = store.get_screen_snapshots()
        vktx = [r for r in result if r["ticker"] == "VKTX"]
        assert len(vktx) == 1
        assert vktx[0]["spread_pp"] == 20.0
        store.close()

    def test_write_supports_multiple_assets_same_ticker_same_date(self, tmp_path):
        from bve.intelligence.knowledge_layer import KnowledgeStore

        store = KnowledgeStore(tmp_path / "test.db")
        rows = [
            self._make_row("VKTX", 15.0, asset_id="a-vktx-lead"),
            self._make_row("VKTX", 8.0, asset_id="a-vktx-follow"),
        ]
        store.write_screen_snapshots(rows)

        result = store.get_screen_snapshots(ticker="VKTX")
        assert len(result) == 2
        assert {row["asset_id"] for row in result} == {"a-vktx-lead", "a-vktx-follow"}
        store.close()

    def test_get_screen_snapshot_for_asset_on_or_before(self, tmp_path):
        from bve.intelligence.knowledge_layer import KnowledgeStore

        store = KnowledgeStore(tmp_path / "test.db")
        store.write_screen_snapshots(
            [self._make_row("VKTX", 15.0, asset_id="a-vktx-lead")],
            snapshot_date=date(2026, 3, 21),
        )
        store.write_screen_snapshots(
            [self._make_row("VKTX", 9.0, asset_id="a-vktx-follow")],
            snapshot_date=date(2026, 3, 28),
        )

        result = store.get_screen_snapshot_for_asset_on_or_before(
            asset_id="a-vktx-lead",
            as_of=date(2026, 3, 28),
        )
        assert result is not None
        assert result["asset_id"] == "a-vktx-lead"
        assert result["snapshot_date"] == "2026-03-21"
        store.close()

    def test_filter_by_snapshot_date(self, tmp_path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        store = KnowledgeStore(tmp_path / "test.db")
        row = self._make_row("VKTX", 15.0)
        store.write_screen_snapshots([row], snapshot_date=date(2026, 3, 28))
        # Different date produces no results
        result = store.get_screen_snapshots(snapshot_date=date(2026, 3, 1))
        assert result == []
        # Correct date returns the row
        result2 = store.get_screen_snapshots(snapshot_date=date(2026, 3, 28))
        assert len(result2) == 1
        store.close()

    def test_get_screen_snapshots_default_returns_latest(self, tmp_path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        store = KnowledgeStore(tmp_path / "test.db")
        r1 = self._make_row("VKTX", 15.0)
        r2 = self._make_row("KYMR", 8.0)
        store.write_screen_snapshots([r1], snapshot_date=date(2026, 3, 27))
        store.write_screen_snapshots([r2], snapshot_date=date(2026, 3, 28))
        result = store.get_screen_snapshots()  # no date arg → latest
        # Should only return 2026-03-28 rows
        assert len(result) == 1
        assert result[0]["ticker"] == "KYMR"
        store.close()

    def test_filter_by_ticker(self, tmp_path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        store = KnowledgeStore(tmp_path / "test.db")
        rows = [self._make_row("VKTX", 15.0), self._make_row("KYMR", 8.0)]
        store.write_screen_snapshots(rows)
        result = store.get_screen_snapshots(ticker="VKTX")
        assert len(result) == 1
        assert result[0]["ticker"] == "VKTX"
        store.close()

    def test_list_snapshot_dates(self, tmp_path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        store = KnowledgeStore(tmp_path / "test.db")
        store.write_screen_snapshots([self._make_row()], snapshot_date=date(2026, 3, 21))
        store.write_screen_snapshots([self._make_row()], snapshot_date=date(2026, 3, 28))
        dates = store.list_screen_snapshot_dates()
        assert dates[0] == date(2026, 3, 28)   # most recent first
        assert dates[1] == date(2026, 3, 21)
        store.close()

    def test_latest_snapshot_date_on_or_before(self, tmp_path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        store = KnowledgeStore(tmp_path / "test.db")
        store.write_screen_snapshots([self._make_row()], snapshot_date=date(2026, 3, 21))
        store.write_screen_snapshots([self._make_row("KYMR", 8.0)], snapshot_date=date(2026, 3, 28))
        assert store.latest_screen_snapshot_date_on_or_before(date(2026, 3, 27)) == date(2026, 3, 21)
        resolved, rows = store.get_screen_snapshots_on_or_before(date(2026, 3, 27))
        assert resolved == date(2026, 3, 21)
        assert len(rows) == 1
        assert rows[0]["ticker"] == "VKTX"
        store.close()

    def test_empty_db_returns_empty_list(self, tmp_path):
        from bve.intelligence.knowledge_layer import KnowledgeStore
        store = KnowledgeStore(tmp_path / "test.db")
        assert store.get_screen_snapshots() == []
        assert store.list_screen_snapshot_dates() == []
        store.close()

    def test_run_screen_offline_and_persist(self, tmp_path):
        """End-to-end: run_screen offline → persist → read back 27 rows."""
        from bve.analysis.implied_pos_batch import run_screen
        from bve.intelligence.knowledge_layer import KnowledgeStore
        from bve.ops.weekly_runner import UNIVERSE
        store = KnowledgeStore(tmp_path / "test.db")
        rows = run_screen(UNIVERSE, fetch_live=False)
        n = store.write_screen_snapshots(rows)
        assert n == 27
        result = store.get_screen_snapshots()
        assert len(result) == 27
        store.close()
