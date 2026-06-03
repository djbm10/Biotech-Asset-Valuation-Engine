"""Persistent SQLite store for Phase 2 gap-fill state objects.

Stores market snapshots, implied expectations, consensus estimates, variant theses,
catalyst payoff trees, financing forecasts, decision records, outcome records, and
parameter versions. All date/datetime values stored as ISO strings; JSON columns
serialized with json.dumps/loads.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from bve.analysis.catalyst_payoff import CatalystPayoffTree
from bve.analysis.implied_expectations import (
    ConsensusEstimate,
    ImpliedExpectationsRecord,
    MarketSnapshot,
)
from bve.analysis.variant_view import VariantThesis
from bve.models.runway_forecast import RunwayForecast


# ---------------------------------------------------------------------------
# New Pydantic models defined here
# ---------------------------------------------------------------------------


class DecisionRecord(BaseModel):
    decision_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: str
    ticker: str
    decision_date: datetime
    action: str  # add / hold / reduce / avoid / watchlist
    target_position_pct: float
    composite_score: float
    market_gap_pct: Optional[float] = None
    thesis_confidence: Optional[float] = None
    catalyst_expected_return_pct: Optional[float] = None
    financing_risk_score: Optional[float] = None
    science_score: Optional[float] = None
    competition_risk_score: Optional[float] = None
    rationale: str
    parameter_version_id: Optional[str] = None


class OutcomeRecord(BaseModel):
    outcome_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    decision_id: str
    asset_id: str
    ticker: str
    decision_date: date
    outcome_date: date
    return_realized_pct: float
    catalyst_triggered: bool = False
    catalyst_description: Optional[str] = None
    thesis_confirmed: Optional[bool] = None
    attribution: str = "unclassified"  # confirmed_thesis / pos_error / timing_error / thesis_error / market_drift


class ParameterVersion(BaseModel):
    version_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    module: str
    parameters: dict[str, float]
    description: str
    is_active: bool = True
    promoted_from_backtest: bool = False


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class GapFillStore:
    """SQLite-backed store for all Phase 2 gap-fill state objects."""

    def __init__(self, db_path: str | Path = "outputs/intelligence/gap_fill.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> GapFillStore:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS market_snapshots (
                id TEXT PRIMARY KEY,
                asset_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                snapshot_date TEXT NOT NULL,
                market_cap_millions REAL,
                ev_millions REAL,
                share_price REAL,
                shares_outstanding_millions REAL,
                cash_millions REAL,
                debt_millions REAL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS implied_expectations (
                id TEXT PRIMARY KEY,
                asset_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                snapshot_date TEXT NOT NULL,
                implied_pos REAL,
                implied_peak_sales_millions REAL,
                implied_dilution_pct REAL,
                implied_timeline_years REAL,
                model_pos REAL,
                model_peak_sales_millions REAL,
                model_rnpv_millions REAL,
                current_ev_millions REAL,
                upside_pct REAL,
                downside_pct REAL,
                valuation_gap_millions REAL,
                methodology TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS consensus_estimates (
                id TEXT PRIMARY KEY,
                asset_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                estimate_date TEXT NOT NULL,
                source TEXT,
                model_pos REAL,
                model_peak_sales_millions REAL,
                analyst_count INTEGER,
                consensus_rnpv_millions REAL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS variant_theses (
                id TEXT PRIMARY KEY,
                asset_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                what_market_believes TEXT,
                what_model_thinks TEXT,
                why_gap_exists TEXT,
                catalysts_to_resolve TEXT,
                confidence_score REAL,
                overall_conviction TEXT,
                deltas_json TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS catalyst_trees (
                id TEXT PRIMARY KEY,
                asset_id TEXT NOT NULL,
                catalyst_id TEXT NOT NULL,
                catalyst_label TEXT NOT NULL,
                catalyst_date TEXT NOT NULL,
                catalyst_type TEXT,
                expected_return_pct REAL,
                downside_severity_pct REAL,
                skew_ratio REAL,
                setup_score REAL,
                pre_event_recommendation TEXT,
                post_event_action_map_json TEXT,
                scenarios_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS financing_forecasts (
                id TEXT PRIMARY KEY,
                company_id TEXT NOT NULL,
                forecast_date TEXT NOT NULL,
                cash_millions REAL,
                debt_millions REAL,
                net_cash_millions REAL,
                runway_months_bull REAL,
                runway_months_base REAL,
                runway_months_bear REAL,
                next_catalyst_date TEXT,
                capital_needed_to_next_catalyst_millions REAL,
                capital_needed_to_approval_millions REAL,
                cash_adequate_for_next_catalyst INTEGER,
                burn_scenarios_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS decision_records (
                decision_id TEXT PRIMARY KEY,
                asset_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                decision_date TEXT NOT NULL,
                action TEXT NOT NULL,
                target_position_pct REAL NOT NULL,
                composite_score REAL NOT NULL,
                market_gap_pct REAL,
                thesis_confidence REAL,
                catalyst_expected_return_pct REAL,
                financing_risk_score REAL,
                science_score REAL,
                competition_risk_score REAL,
                rationale TEXT,
                parameter_version_id TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS outcome_records (
                outcome_id TEXT PRIMARY KEY,
                decision_id TEXT NOT NULL,
                asset_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                decision_date TEXT NOT NULL,
                outcome_date TEXT NOT NULL,
                return_realized_pct REAL NOT NULL,
                catalyst_triggered INTEGER NOT NULL DEFAULT 0,
                catalyst_description TEXT,
                thesis_confirmed INTEGER,
                attribution TEXT NOT NULL DEFAULT 'unclassified',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS parameter_versions (
                version_id TEXT PRIMARY KEY,
                module TEXT NOT NULL,
                description TEXT,
                parameters_json TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                promoted_from_backtest INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # market_snapshots
    # ------------------------------------------------------------------

    def upsert_market_snapshot(self, snap: MarketSnapshot) -> None:
        row_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO market_snapshots(
                id, asset_id, ticker, snapshot_date,
                market_cap_millions, ev_millions, share_price,
                shares_outstanding_millions, cash_millions, debt_millions,
                created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_id,
                snap.asset_id,
                snap.ticker,
                snap.snapshot_date.isoformat(),
                snap.market_cap_millions,
                snap.ev_millions,
                snap.share_price,
                snap.shares_outstanding_millions,
                snap.cash_millions,
                snap.debt_millions,
                now,
            ),
        )
        self._conn.commit()

    def get_latest_market_snapshot(self, asset_id: str) -> Optional[MarketSnapshot]:
        row = self._conn.execute(
            """
            SELECT asset_id, ticker, snapshot_date,
                   market_cap_millions, ev_millions, share_price,
                   shares_outstanding_millions, cash_millions, debt_millions
            FROM market_snapshots WHERE asset_id = ?
            ORDER BY snapshot_date DESC, created_at DESC LIMIT 1
            """,
            (asset_id,),
        ).fetchone()
        if row is None:
            return None
        return MarketSnapshot(
            asset_id=row["asset_id"],
            ticker=row["ticker"],
            snapshot_date=date.fromisoformat(row["snapshot_date"]),
            market_cap_millions=row["market_cap_millions"],
            ev_millions=row["ev_millions"],
            share_price=row["share_price"],
            shares_outstanding_millions=row["shares_outstanding_millions"],
            cash_millions=row["cash_millions"],
            debt_millions=row["debt_millions"],
        )

    def get_market_snapshots(self, asset_id: str, limit: int = 90) -> list[MarketSnapshot]:
        rows = self._conn.execute(
            """
            SELECT asset_id, ticker, snapshot_date,
                   market_cap_millions, ev_millions, share_price,
                   shares_outstanding_millions, cash_millions, debt_millions
            FROM market_snapshots WHERE asset_id = ?
            ORDER BY snapshot_date ASC, created_at ASC
            LIMIT ?
            """,
            (asset_id, limit),
        ).fetchall()
        return [
            MarketSnapshot(
                asset_id=r["asset_id"],
                ticker=r["ticker"],
                snapshot_date=date.fromisoformat(r["snapshot_date"]),
                market_cap_millions=r["market_cap_millions"],
                ev_millions=r["ev_millions"],
                share_price=r["share_price"],
                shares_outstanding_millions=r["shares_outstanding_millions"],
                cash_millions=r["cash_millions"],
                debt_millions=r["debt_millions"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # implied_expectations
    # ------------------------------------------------------------------

    def upsert_implied_expectation(self, rec: ImpliedExpectationsRecord) -> None:
        row_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO implied_expectations(
                id, asset_id, ticker, snapshot_date,
                implied_pos, implied_peak_sales_millions, implied_dilution_pct,
                implied_timeline_years, model_pos, model_peak_sales_millions,
                model_rnpv_millions, current_ev_millions, upside_pct,
                downside_pct, valuation_gap_millions, methodology, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_id,
                rec.asset_id,
                rec.ticker,
                rec.snapshot_date.isoformat(),
                rec.implied_pos,
                rec.implied_peak_sales_millions,
                rec.implied_dilution_pct,
                rec.implied_timeline_years,
                rec.model_pos,
                rec.model_peak_sales_millions,
                rec.model_rnpv_millions,
                rec.current_ev_millions,
                rec.upside_pct,
                rec.downside_pct,
                rec.valuation_gap_millions,
                rec.methodology,
                now,
            ),
        )
        self._conn.commit()

    def get_latest_implied_expectation(self, asset_id: str) -> Optional[ImpliedExpectationsRecord]:
        row = self._conn.execute(
            """
            SELECT asset_id, ticker, snapshot_date,
                   implied_pos, implied_peak_sales_millions, implied_dilution_pct,
                   implied_timeline_years, model_pos, model_peak_sales_millions,
                   model_rnpv_millions, current_ev_millions, upside_pct,
                   downside_pct, valuation_gap_millions, methodology
            FROM implied_expectations WHERE asset_id = ?
            ORDER BY snapshot_date DESC, created_at DESC LIMIT 1
            """,
            (asset_id,),
        ).fetchone()
        if row is None:
            return None
        return ImpliedExpectationsRecord(
            asset_id=row["asset_id"],
            ticker=row["ticker"],
            snapshot_date=date.fromisoformat(row["snapshot_date"]),
            implied_pos=row["implied_pos"],
            implied_peak_sales_millions=row["implied_peak_sales_millions"],
            implied_dilution_pct=row["implied_dilution_pct"],
            implied_timeline_years=row["implied_timeline_years"],
            model_pos=row["model_pos"],
            model_peak_sales_millions=row["model_peak_sales_millions"],
            model_rnpv_millions=row["model_rnpv_millions"],
            current_ev_millions=row["current_ev_millions"],
            upside_pct=row["upside_pct"],
            downside_pct=row["downside_pct"],
            valuation_gap_millions=row["valuation_gap_millions"],
            methodology=row["methodology"],
        )

    def get_implied_expectations(
        self, asset_id: str, limit: int = 90
    ) -> list[ImpliedExpectationsRecord]:
        rows = self._conn.execute(
            """
            SELECT asset_id, ticker, snapshot_date,
                   implied_pos, implied_peak_sales_millions, implied_dilution_pct,
                   implied_timeline_years, model_pos, model_peak_sales_millions,
                   model_rnpv_millions, current_ev_millions, upside_pct,
                   downside_pct, valuation_gap_millions, methodology
            FROM implied_expectations WHERE asset_id = ?
            ORDER BY snapshot_date ASC, created_at ASC
            LIMIT ?
            """,
            (asset_id, limit),
        ).fetchall()
        return [
            ImpliedExpectationsRecord(
                asset_id=r["asset_id"],
                ticker=r["ticker"],
                snapshot_date=date.fromisoformat(r["snapshot_date"]),
                implied_pos=r["implied_pos"],
                implied_peak_sales_millions=r["implied_peak_sales_millions"],
                implied_dilution_pct=r["implied_dilution_pct"],
                implied_timeline_years=r["implied_timeline_years"],
                model_pos=r["model_pos"],
                model_peak_sales_millions=r["model_peak_sales_millions"],
                model_rnpv_millions=r["model_rnpv_millions"],
                current_ev_millions=r["current_ev_millions"],
                upside_pct=r["upside_pct"],
                downside_pct=r["downside_pct"],
                valuation_gap_millions=r["valuation_gap_millions"],
                methodology=r["methodology"],
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # consensus_estimates
    # ------------------------------------------------------------------

    def upsert_consensus_estimate(self, est: ConsensusEstimate) -> None:
        row_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO consensus_estimates(
                id, asset_id, ticker, estimate_date, source,
                model_pos, model_peak_sales_millions, analyst_count,
                consensus_rnpv_millions, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_id,
                est.asset_id,
                est.ticker,
                est.estimate_date.isoformat(),
                est.source,
                est.model_pos,
                est.model_peak_sales_millions,
                est.analyst_count,
                est.consensus_rnpv_millions,
                now,
            ),
        )
        self._conn.commit()

    def get_latest_consensus_estimate(self, asset_id: str) -> Optional[ConsensusEstimate]:
        row = self._conn.execute(
            """
            SELECT asset_id, ticker, estimate_date, source,
                   model_pos, model_peak_sales_millions, analyst_count,
                   consensus_rnpv_millions
            FROM consensus_estimates WHERE asset_id = ?
            ORDER BY estimate_date DESC, created_at DESC LIMIT 1
            """,
            (asset_id,),
        ).fetchone()
        if row is None:
            return None
        return ConsensusEstimate(
            asset_id=row["asset_id"],
            ticker=row["ticker"],
            estimate_date=date.fromisoformat(row["estimate_date"]),
            source=row["source"],
            model_pos=row["model_pos"],
            model_peak_sales_millions=row["model_peak_sales_millions"],
            analyst_count=row["analyst_count"],
            consensus_rnpv_millions=row["consensus_rnpv_millions"],
        )

    # ------------------------------------------------------------------
    # variant_theses
    # ------------------------------------------------------------------

    def upsert_variant_thesis(self, thesis: VariantThesis) -> None:
        row_id = str(uuid.uuid4())
        self._conn.execute(
            """
            INSERT OR REPLACE INTO variant_theses(
                id, asset_id, ticker, created_at, updated_at,
                what_market_believes, what_model_thinks, why_gap_exists,
                catalysts_to_resolve, confidence_score, overall_conviction,
                deltas_json, is_active
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                row_id,
                thesis.asset_id,
                thesis.ticker,
                thesis.created_at.isoformat(),
                thesis.updated_at.isoformat(),
                thesis.what_market_believes,
                thesis.what_model_thinks,
                thesis.why_gap_exists,
                json.dumps(thesis.catalysts_to_resolve),
                thesis.confidence_score,
                thesis.overall_conviction,
                json.dumps([d.model_dump() for d in thesis.deltas]),
            ),
        )
        self._conn.commit()

    def get_active_variant_thesis(self, asset_id: str) -> Optional[VariantThesis]:
        row = self._conn.execute(
            """
            SELECT asset_id, ticker, created_at, updated_at,
                   what_market_believes, what_model_thinks, why_gap_exists,
                   catalysts_to_resolve, confidence_score, overall_conviction,
                   deltas_json
            FROM variant_theses
            WHERE asset_id = ? AND is_active = 1
            ORDER BY updated_at DESC LIMIT 1
            """,
            (asset_id,),
        ).fetchone()
        if row is None:
            return None
        from bve.analysis.variant_view import VariantDelta

        deltas = [VariantDelta(**d) for d in json.loads(row["deltas_json"])]
        return VariantThesis(
            asset_id=row["asset_id"],
            ticker=row["ticker"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            what_market_believes=row["what_market_believes"],
            what_model_thinks=row["what_model_thinks"],
            why_gap_exists=row["why_gap_exists"],
            catalysts_to_resolve=json.loads(row["catalysts_to_resolve"]),
            confidence_score=row["confidence_score"],
            overall_conviction=row["overall_conviction"],
            deltas=deltas,
        )

    def get_variant_theses(self, asset_id: str) -> list[VariantThesis]:
        rows = self._conn.execute(
            """
            SELECT asset_id, ticker, created_at, updated_at,
                   what_market_believes, what_model_thinks, why_gap_exists,
                   catalysts_to_resolve, confidence_score, overall_conviction,
                   deltas_json
            FROM variant_theses WHERE asset_id = ?
            ORDER BY updated_at ASC
            """,
            (asset_id,),
        ).fetchall()
        from bve.analysis.variant_view import VariantDelta

        result = []
        for row in rows:
            deltas = [VariantDelta(**d) for d in json.loads(row["deltas_json"])]
            result.append(
                VariantThesis(
                    asset_id=row["asset_id"],
                    ticker=row["ticker"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                    updated_at=datetime.fromisoformat(row["updated_at"]),
                    what_market_believes=row["what_market_believes"],
                    what_model_thinks=row["what_model_thinks"],
                    why_gap_exists=row["why_gap_exists"],
                    catalysts_to_resolve=json.loads(row["catalysts_to_resolve"]),
                    confidence_score=row["confidence_score"],
                    overall_conviction=row["overall_conviction"],
                    deltas=deltas,
                )
            )
        return result

    # ------------------------------------------------------------------
    # catalyst_trees
    # ------------------------------------------------------------------

    def upsert_catalyst_tree(self, tree: CatalystPayoffTree) -> None:
        row_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO catalyst_trees(
                id, asset_id, catalyst_id, catalyst_label,
                catalyst_date, catalyst_type,
                expected_return_pct, downside_severity_pct, skew_ratio,
                setup_score, pre_event_recommendation,
                post_event_action_map_json, scenarios_json, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_id,
                tree.asset_id,
                tree.catalyst_id,
                tree.catalyst_label,
                tree.catalyst_date.isoformat(),
                tree.catalyst_type,
                tree.expected_return_pct,
                tree.downside_severity_pct,
                tree.skew_ratio,
                tree.setup_score,
                tree.pre_event_recommendation,
                json.dumps(tree.post_event_action_map),
                json.dumps([s.model_dump() for s in tree.scenarios]),
                now,
            ),
        )
        self._conn.commit()

    def get_catalyst_trees(self, asset_id: str) -> list[CatalystPayoffTree]:
        rows = self._conn.execute(
            """
            SELECT asset_id, catalyst_id, catalyst_label, catalyst_date,
                   catalyst_type, expected_return_pct, downside_severity_pct,
                   skew_ratio, setup_score, pre_event_recommendation,
                   post_event_action_map_json, scenarios_json
            FROM catalyst_trees WHERE asset_id = ?
            ORDER BY catalyst_date ASC, created_at ASC
            """,
            (asset_id,),
        ).fetchall()
        from bve.analysis.catalyst_payoff import CatalystScenario

        result = []
        for row in rows:
            scenarios = [CatalystScenario(**s) for s in json.loads(row["scenarios_json"])]
            result.append(
                CatalystPayoffTree(
                    catalyst_id=row["catalyst_id"],
                    asset_id=row["asset_id"],
                    catalyst_label=row["catalyst_label"],
                    catalyst_date=date.fromisoformat(row["catalyst_date"]),
                    catalyst_type=row["catalyst_type"],
                    scenarios=scenarios,
                    expected_return_pct=row["expected_return_pct"],
                    downside_severity_pct=row["downside_severity_pct"],
                    skew_ratio=row["skew_ratio"],
                    setup_score=row["setup_score"],
                    pre_event_recommendation=row["pre_event_recommendation"],
                    post_event_action_map=json.loads(row["post_event_action_map_json"]),
                )
            )
        return result

    def get_latest_catalyst_tree(self, asset_id: str) -> Optional[CatalystPayoffTree]:
        row = self._conn.execute(
            """
            SELECT asset_id, catalyst_id, catalyst_label, catalyst_date,
                   catalyst_type, expected_return_pct, downside_severity_pct,
                   skew_ratio, setup_score, pre_event_recommendation,
                   post_event_action_map_json, scenarios_json
            FROM catalyst_trees WHERE asset_id = ?
            ORDER BY catalyst_date DESC, created_at DESC LIMIT 1
            """,
            (asset_id,),
        ).fetchone()
        if row is None:
            return None
        from bve.analysis.catalyst_payoff import CatalystScenario

        scenarios = [CatalystScenario(**s) for s in json.loads(row["scenarios_json"])]
        return CatalystPayoffTree(
            catalyst_id=row["catalyst_id"],
            asset_id=row["asset_id"],
            catalyst_label=row["catalyst_label"],
            catalyst_date=date.fromisoformat(row["catalyst_date"]),
            catalyst_type=row["catalyst_type"],
            scenarios=scenarios,
            expected_return_pct=row["expected_return_pct"],
            downside_severity_pct=row["downside_severity_pct"],
            skew_ratio=row["skew_ratio"],
            setup_score=row["setup_score"],
            pre_event_recommendation=row["pre_event_recommendation"],
            post_event_action_map=json.loads(row["post_event_action_map_json"]),
        )

    # ------------------------------------------------------------------
    # financing_forecasts
    # ------------------------------------------------------------------

    def upsert_financing_forecast(self, forecast: RunwayForecast) -> None:
        row_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO financing_forecasts(
                id, company_id, forecast_date,
                cash_millions, debt_millions, net_cash_millions,
                runway_months_bull, runway_months_base, runway_months_bear,
                next_catalyst_date,
                capital_needed_to_next_catalyst_millions,
                capital_needed_to_approval_millions,
                cash_adequate_for_next_catalyst,
                burn_scenarios_json, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_id,
                forecast.company_id,
                forecast.forecast_date.isoformat(),
                forecast.cash_millions,
                forecast.debt_millions,
                forecast.net_cash_millions,
                forecast.runway_months_bull,
                forecast.runway_months_base,
                forecast.runway_months_bear,
                forecast.next_catalyst_date.isoformat() if forecast.next_catalyst_date else None,
                forecast.capital_needed_to_next_catalyst_millions,
                forecast.capital_needed_to_approval_millions,
                1 if forecast.cash_adequate_for_next_catalyst else 0,
                json.dumps([s.model_dump() for s in forecast.burn_scenarios]),
                now,
            ),
        )
        self._conn.commit()

    def get_latest_financing_forecast(self, company_id: str) -> Optional[RunwayForecast]:
        row = self._conn.execute(
            """
            SELECT company_id, forecast_date,
                   cash_millions, debt_millions, net_cash_millions,
                   runway_months_bull, runway_months_base, runway_months_bear,
                   next_catalyst_date,
                   capital_needed_to_next_catalyst_millions,
                   capital_needed_to_approval_millions,
                   cash_adequate_for_next_catalyst,
                   burn_scenarios_json
            FROM financing_forecasts WHERE company_id = ?
            ORDER BY forecast_date DESC, created_at DESC LIMIT 1
            """,
            (company_id,),
        ).fetchone()
        if row is None:
            return None
        from bve.models.runway_forecast import BurnScenario

        burn_scenarios = [BurnScenario(**s) for s in json.loads(row["burn_scenarios_json"] or "[]")]
        next_cat = (
            date.fromisoformat(row["next_catalyst_date"]) if row["next_catalyst_date"] else None
        )
        return RunwayForecast(
            company_id=row["company_id"],
            forecast_date=date.fromisoformat(row["forecast_date"]),
            cash_millions=row["cash_millions"],
            debt_millions=row["debt_millions"],
            net_cash_millions=row["net_cash_millions"],
            burn_scenarios=burn_scenarios,
            runway_months_bull=row["runway_months_bull"],
            runway_months_base=row["runway_months_base"],
            runway_months_bear=row["runway_months_bear"],
            next_catalyst_date=next_cat,
            capital_needed_to_next_catalyst_millions=row[
                "capital_needed_to_next_catalyst_millions"
            ],
            capital_needed_to_approval_millions=row["capital_needed_to_approval_millions"],
            cash_adequate_for_next_catalyst=bool(row["cash_adequate_for_next_catalyst"]),
        )

    # ------------------------------------------------------------------
    # decision_records
    # ------------------------------------------------------------------

    def write_decision(self, rec: DecisionRecord) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO decision_records(
                decision_id, asset_id, ticker, decision_date,
                action, target_position_pct, composite_score,
                market_gap_pct, thesis_confidence, catalyst_expected_return_pct,
                financing_risk_score, science_score, competition_risk_score,
                rationale, parameter_version_id, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rec.decision_id,
                rec.asset_id,
                rec.ticker,
                rec.decision_date.isoformat(),
                rec.action,
                rec.target_position_pct,
                rec.composite_score,
                rec.market_gap_pct,
                rec.thesis_confidence,
                rec.catalyst_expected_return_pct,
                rec.financing_risk_score,
                rec.science_score,
                rec.competition_risk_score,
                rec.rationale,
                rec.parameter_version_id,
                now,
            ),
        )
        self._conn.commit()

    def get_decisions(self, asset_id: str, limit: int = 100) -> list[DecisionRecord]:
        rows = self._conn.execute(
            """
            SELECT decision_id, asset_id, ticker, decision_date,
                   action, target_position_pct, composite_score,
                   market_gap_pct, thesis_confidence, catalyst_expected_return_pct,
                   financing_risk_score, science_score, competition_risk_score,
                   rationale, parameter_version_id
            FROM decision_records WHERE asset_id = ?
            ORDER BY decision_date ASC, created_at ASC
            LIMIT ?
            """,
            (asset_id, limit),
        ).fetchall()
        return [
            DecisionRecord(
                decision_id=r["decision_id"],
                asset_id=r["asset_id"],
                ticker=r["ticker"],
                decision_date=datetime.fromisoformat(r["decision_date"]),
                action=r["action"],
                target_position_pct=r["target_position_pct"],
                composite_score=r["composite_score"],
                market_gap_pct=r["market_gap_pct"],
                thesis_confidence=r["thesis_confidence"],
                catalyst_expected_return_pct=r["catalyst_expected_return_pct"],
                financing_risk_score=r["financing_risk_score"],
                science_score=r["science_score"],
                competition_risk_score=r["competition_risk_score"],
                rationale=r["rationale"] or "",
                parameter_version_id=r["parameter_version_id"],
            )
            for r in rows
        ]

    def get_decision(self, decision_id: str) -> Optional[DecisionRecord]:
        row = self._conn.execute(
            """
            SELECT decision_id, asset_id, ticker, decision_date,
                   action, target_position_pct, composite_score,
                   market_gap_pct, thesis_confidence, catalyst_expected_return_pct,
                   financing_risk_score, science_score, competition_risk_score,
                   rationale, parameter_version_id
            FROM decision_records WHERE decision_id = ?
            """,
            (decision_id,),
        ).fetchone()
        if row is None:
            return None
        return DecisionRecord(
            decision_id=row["decision_id"],
            asset_id=row["asset_id"],
            ticker=row["ticker"],
            decision_date=datetime.fromisoformat(row["decision_date"]),
            action=row["action"],
            target_position_pct=row["target_position_pct"],
            composite_score=row["composite_score"],
            market_gap_pct=row["market_gap_pct"],
            thesis_confidence=row["thesis_confidence"],
            catalyst_expected_return_pct=row["catalyst_expected_return_pct"],
            financing_risk_score=row["financing_risk_score"],
            science_score=row["science_score"],
            competition_risk_score=row["competition_risk_score"],
            rationale=row["rationale"] or "",
            parameter_version_id=row["parameter_version_id"],
        )

    # ------------------------------------------------------------------
    # outcome_records
    # ------------------------------------------------------------------

    def write_outcome(self, rec: OutcomeRecord) -> None:
        now = datetime.now(timezone.utc).isoformat()
        thesis_int = None if rec.thesis_confirmed is None else (1 if rec.thesis_confirmed else 0)
        self._conn.execute(
            """
            INSERT OR REPLACE INTO outcome_records(
                outcome_id, decision_id, asset_id, ticker,
                decision_date, outcome_date, return_realized_pct,
                catalyst_triggered, catalyst_description,
                thesis_confirmed, attribution, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                rec.outcome_id,
                rec.decision_id,
                rec.asset_id,
                rec.ticker,
                rec.decision_date.isoformat(),
                rec.outcome_date.isoformat(),
                rec.return_realized_pct,
                1 if rec.catalyst_triggered else 0,
                rec.catalyst_description,
                thesis_int,
                rec.attribution,
                now,
            ),
        )
        self._conn.commit()

    def get_outcomes(self, asset_id: str) -> list[OutcomeRecord]:
        rows = self._conn.execute(
            """
            SELECT outcome_id, decision_id, asset_id, ticker,
                   decision_date, outcome_date, return_realized_pct,
                   catalyst_triggered, catalyst_description,
                   thesis_confirmed, attribution
            FROM outcome_records WHERE asset_id = ?
            ORDER BY outcome_date ASC, created_at ASC
            """,
            (asset_id,),
        ).fetchall()
        return [
            OutcomeRecord(
                outcome_id=r["outcome_id"],
                decision_id=r["decision_id"],
                asset_id=r["asset_id"],
                ticker=r["ticker"],
                decision_date=date.fromisoformat(r["decision_date"]),
                outcome_date=date.fromisoformat(r["outcome_date"]),
                return_realized_pct=r["return_realized_pct"],
                catalyst_triggered=bool(r["catalyst_triggered"]),
                catalyst_description=r["catalyst_description"],
                thesis_confirmed=None if r["thesis_confirmed"] is None else bool(r["thesis_confirmed"]),
                attribution=r["attribution"],
            )
            for r in rows
        ]

    def get_outcome_for_decision(self, decision_id: str) -> Optional[OutcomeRecord]:
        row = self._conn.execute(
            """
            SELECT outcome_id, decision_id, asset_id, ticker,
                   decision_date, outcome_date, return_realized_pct,
                   catalyst_triggered, catalyst_description,
                   thesis_confirmed, attribution
            FROM outcome_records WHERE decision_id = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            (decision_id,),
        ).fetchone()
        if row is None:
            return None
        return OutcomeRecord(
            outcome_id=row["outcome_id"],
            decision_id=row["decision_id"],
            asset_id=row["asset_id"],
            ticker=row["ticker"],
            decision_date=date.fromisoformat(row["decision_date"]),
            outcome_date=date.fromisoformat(row["outcome_date"]),
            return_realized_pct=row["return_realized_pct"],
            catalyst_triggered=bool(row["catalyst_triggered"]),
            catalyst_description=row["catalyst_description"],
            thesis_confirmed=None if row["thesis_confirmed"] is None else bool(row["thesis_confirmed"]),
            attribution=row["attribution"],
        )

    # ------------------------------------------------------------------
    # parameter_versions
    # ------------------------------------------------------------------

    def write_parameter_version(self, pv: ParameterVersion) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO parameter_versions(
                version_id, module, description, parameters_json,
                is_active, promoted_from_backtest, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pv.version_id,
                pv.module,
                pv.description,
                json.dumps(pv.parameters),
                1 if pv.is_active else 0,
                1 if pv.promoted_from_backtest else 0,
                pv.created_at.isoformat(),
            ),
        )
        self._conn.commit()

    def get_active_parameter_version(self, module: str) -> Optional[ParameterVersion]:
        row = self._conn.execute(
            """
            SELECT version_id, module, description, parameters_json,
                   is_active, promoted_from_backtest, created_at
            FROM parameter_versions
            WHERE module = ? AND is_active = 1
            ORDER BY created_at DESC LIMIT 1
            """,
            (module,),
        ).fetchone()
        if row is None:
            return None
        return ParameterVersion(
            version_id=row["version_id"],
            module=row["module"],
            parameters=json.loads(row["parameters_json"]),
            description=row["description"] or "",
            is_active=bool(row["is_active"]),
            promoted_from_backtest=bool(row["promoted_from_backtest"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def list_parameter_versions(self, module: str) -> list[ParameterVersion]:
        rows = self._conn.execute(
            """
            SELECT version_id, module, description, parameters_json,
                   is_active, promoted_from_backtest, created_at
            FROM parameter_versions WHERE module = ?
            ORDER BY created_at ASC
            """,
            (module,),
        ).fetchall()
        return [
            ParameterVersion(
                version_id=r["version_id"],
                module=r["module"],
                parameters=json.loads(r["parameters_json"]),
                description=r["description"] or "",
                is_active=bool(r["is_active"]),
                promoted_from_backtest=bool(r["promoted_from_backtest"]),
                created_at=datetime.fromisoformat(r["created_at"]),
            )
            for r in rows
        ]

    def deactivate_parameter_version(self, version_id: str) -> None:
        self._conn.execute(
            "UPDATE parameter_versions SET is_active = 0 WHERE version_id = ?",
            (version_id,),
        )
        self._conn.commit()
