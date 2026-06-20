"""
Minimal relational knowledge layer for intelligence workflows.

Design goals:
  - structured (non-vector) retrieval first
  - source traceability on every persisted record
  - auditable, reconstructable dossier outputs
  - no direct dependency on valuation-engine modules
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Optional

from pydantic import BaseModel, Field

from bve.intelligence.extraction.raw_document import RawDocument
from bve.intelligence.extraction.result import ExtractionResult
from bve.intelligence.knowledge_graph import EdgeType, KGEdge, KGNode, NodeType
from bve.intelligence.schemas.runs import ReviewDecision
from bve.intelligence.schemas.signals import Event, StructuredSignal
from bve.intelligence.taxonomy import EventType

if TYPE_CHECKING:  # pragma: no cover
    from bve.connectors.market_prices import MarketPriceRecord
    from bve.intelligence.acquisition_screen import AcquisitionDiscountSnapshot
    from bve.intelligence.catalyst_calendar import CatalystEvent
    from bve.intelligence.enrollment_snapshot_extractor import EnrollmentSnapshot
    from bve.intelligence.market_expectations import MarketExpectation
    from bve.ops.data_quality import DataQualityScore


class SourceTrace(BaseModel):
    """Provenance attached to each stored record."""

    source_type: str
    source_ref: str
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: Optional[str] = None


class RawDocumentRecord(BaseModel):
    """Minimal stored raw-document artifact."""

    id: str
    payload_json: dict
    created_at: datetime


class ExtractionResultRecord(BaseModel):
    """Minimal stored extraction-result artifact."""

    id: str
    raw_document_id: str
    payload_json: dict
    created_at: datetime


class StructuredSignalRecord(BaseModel):
    """Minimal stored structured-signal artifact."""

    id: str
    extraction_result_id: str
    payload_json: dict
    created_at: datetime


class EvidenceFactRecord(BaseModel):
    """Persisted evidence fact."""

    fact_id: str
    company_id: str
    asset_id: str
    fact_namespace: str
    fact_key: str
    entity_type: str
    entity_id: str
    source_type: str
    conflict_status: str
    is_active: bool
    payload_json: dict
    created_at: datetime


class StoredValuationDiff(BaseModel):
    """
    Storage-safe valuation diff model used by the knowledge layer.

    This model intentionally avoids importing valuation modules.
    """

    run_id: str
    event_id: str
    asset_id: str
    valuation_before: dict
    valuation_after: dict
    delta_npv: float
    created_at: datetime
    valuation_delta: dict[str, float] = Field(default_factory=dict)
    assumptions_changed: list[dict] = Field(default_factory=list)
    applied_overrides: dict[str, float] = Field(default_factory=dict)
    # Market cap at the time this diff was computed ($M). Enables historical
    # mispricing analysis without requiring a live yfinance lookup at ranking time.
    market_cap_snapshot_millions: Optional[float] = None


class ScoreUpdateRecord(BaseModel):
    """Auditable record of a scanner composite-score movement driven by signals.

    Commit 1 of the live scanner score-update contract: ``prior_score`` is the base
    composite (no signal context) and ``new_score`` is the composite after applying
    the stored-signal context, so ``delta`` and the contributing IDs isolate the
    signal-driven movement (source → fact → score impact lineage).
    """

    id: str
    asset_id: str
    as_of: date
    prior_score: Optional[float]
    new_score: float
    delta: float
    run_id: Optional[str] = None
    decision: str = "auto_apply"  # auto_apply | review (commit 2 gate)
    components: dict[str, float] = Field(default_factory=dict)
    contributing_signal_ids: list[str] = Field(default_factory=list)
    contributing_event_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RunStateRecord(BaseModel):
    """Persistent per-stage runtime status for one asset run."""

    run_id: str
    stage: str
    asset_id: str
    status: Literal["running", "success", "failure", "skipped"]
    started_at: datetime
    finished_at: Optional[datetime] = None
    checkpoint_json: dict[str, Any] = Field(default_factory=dict)
    error_json: dict[str, Any] = Field(default_factory=dict)


class OpportunityAlertRecord(BaseModel):
    """Idempotent opportunity alert artifact."""

    asset_id: str
    event_type: str
    window: str
    run_id: Optional[str] = None
    created_at: datetime
    payload_json: dict[str, Any] = Field(default_factory=dict)


class CompanySOTPSnapshotRecord(BaseModel):
    """Persisted point-in-time company SOTP row."""

    ticker: str
    company_id: str
    company_name: str
    snapshot_date: date
    rank: int = 0
    market_cap_millions: float
    enterprise_value_millions: float
    sotp_equity_value_millions: float
    sotp_per_share: float
    sotp_discount: float
    ranked_sotp_discount: float
    reconciliation_gap_millions: float = 0.0
    reconciliation_gap_pct: float = 0.0
    reconciliation_status: Optional[str] = None
    reconciliation_passes_gate: bool = True
    mcap_trend_3m_pct: Optional[float] = None
    sotp_tier: Optional[str] = None
    sotp_action: Optional[str] = None
    sotp_confidence_tier: Optional[str] = None
    sotp_tier_reason: Optional[str] = None
    modeled_asset_coverage_pct: float
    asset_count_modeled: int
    modeled_asset_ids: list[str] = Field(default_factory=list)
    config_quality_summary: Optional[str] = None
    modeled_asset_confidence_min: float = 0.0
    modeled_asset_confidence_avg: float = 0.0
    action_policy: Optional[str] = None
    action_reason: Optional[str] = None
    market_cap_source: Optional[str] = None
    balance_sheet_source: Optional[str] = None
    balance_sheet_source_ref: Optional[str] = None
    balance_sheet_snapshot_date: Optional[date] = None
    balance_sheet_period_end_date: Optional[date] = None
    balance_sheet_form_type: Optional[str] = None
    balance_sheet_is_point_in_time: bool = False
    balance_sheet_age_days: Optional[int] = None
    balance_sheet_passes_recency_gate: bool = False
    balance_sheet_recency_penalty: float = 1.0
    bucket_count: int = 0
    buckets: list[dict[str, Any]] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EquityPolicySnapshotRecord(BaseModel):
    """Persisted Step 5 equity-policy audit row."""

    ticker: str
    as_of_date: date
    reference_snapshot_date: Optional[date] = None
    company_snapshot_date: Optional[date] = None
    source_mode: str = "heuristic_company_snapshot"
    company_action_policy: Optional[str] = None
    company_action_reason: Optional[str] = None
    company_ranked_discount: Optional[float] = None
    composite_score: Optional[float] = None
    current_price: Optional[float] = None
    base_sotp_per_share: Optional[float] = None
    bear_sotp_per_share: Optional[float] = None
    bull_sotp_per_share: Optional[float] = None
    conviction: Optional[float] = None
    adv_millions: Optional[float] = None
    next_catalyst_days: Optional[int] = None
    catalyst_description: Optional[str] = None
    action: str
    sizing_pct: float = 0.0
    rationale: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DataRetentionResult(BaseModel):
    """Summary of one retention-policy application."""

    applied_at: datetime
    raw_documents_retention_days: int
    raw_documents_deleted: int = 0
    structured_signals_deleted: int = 0


class BacktestSnapshot(BaseModel):
    """Snapshot of a firing alert used for downstream portfolio backtests."""

    snapshot_id: str
    alert_id: str
    asset_id: str
    signal_date: date
    signal_id: Optional[str] = None
    signal_timestamp: Optional[datetime] = None
    composite_score: Optional[float] = None
    extraction_confidence: Optional[float] = None
    delta_npv_millions: Optional[float] = None
    intrinsic_value_millions: Optional[float] = None
    mispricing_score: Optional[float] = None
    catalyst_date: Optional[date] = None
    catalyst_type: Optional[str] = None
    catalyst_score: Optional[float] = None
    rank_at_signal: Optional[int] = None
    model_version: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AssetRegistryEntry(BaseModel):
    """Structured tracked-asset registry row."""

    asset_id: str
    ticker: Optional[str] = None
    company_id: Optional[str] = None
    drug_name: Optional[str] = None
    indication: Optional[str] = None
    therapeutic_area: Optional[str] = None
    modality: Optional[str] = None
    stage: Optional[str] = None
    nct_id: Optional[str] = None
    tam_millions: Optional[float] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str
    last_competitor_discovery_at: Optional[datetime] = None


class MemoRecord(BaseModel):
    """Persisted analyst/system memo."""

    id: str
    company_id: Optional[str] = None
    asset_id: Optional[str] = None
    title: str
    memo_type: str = "analyst_memo"
    content_markdown: str
    created_at: datetime
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    source_signal_ids: list[str] = Field(default_factory=list)
    source_run_ids: list[str] = Field(default_factory=list)
    referenced_event_ids: list[str] = Field(default_factory=list)
    referenced_diff_ids: list[str] = Field(default_factory=list)
    referenced_review_ids: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    source_trace: SourceTrace


class LiteratureReviewRecord(BaseModel):
    """Persisted literature review synthesis output."""

    id: str
    company_id: Optional[str] = None
    asset_id: Optional[str] = None
    generated_at: datetime
    payload_json: dict
    source_trace: SourceTrace


class CompetitiveLandscapeRecord(BaseModel):
    """Persisted competitive landscape synthesis output."""

    id: str
    company_id: Optional[str] = None
    asset_id: Optional[str] = None
    generated_at: datetime
    payload_json: dict
    source_trace: SourceTrace


class ResearchReportRecord(BaseModel):
    """Persisted research report synthesis output."""

    id: str
    company_id: Optional[str] = None
    asset_id: Optional[str] = None
    report_version: Optional[str] = None
    model_version: Optional[str] = None
    generated_at: datetime
    payload_json: dict
    source_trace: SourceTrace


class DossierRecord(BaseModel):
    """Generated dossier for a company/asset."""

    id: str
    company_id: Optional[str] = None
    asset_id: Optional[str] = None
    generated_at: datetime
    recent_events: list[Event] = Field(default_factory=list)
    current_assumptions: dict = Field(default_factory=dict)
    latest_valuation_snapshot: dict = Field(default_factory=dict)
    recent_changes: list[StoredValuationDiff] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    source_trace: SourceTrace


class RecordWithTrace(BaseModel):
    """Stored payload + provenance + reconstructed chain."""

    record_type: str
    record_id: str
    payload: dict
    source_trace: SourceTrace
    provenance_chain: dict[str, Any] = Field(default_factory=dict)


class KnowledgeStore:
    """
    SQLite-backed knowledge storage and retrieval.

    Stores:
      - upstream provenance artifacts (raw documents, extraction results, structured signals)
      - events
      - valuation diffs (+ assumptions and valuation snapshots)
      - run_state stage records
      - opportunity alerts
      - review decisions
      - memos
      - dossiers
      - literature reviews
      - competitive landscapes
      - research reports
    """

    def __init__(self, db_path: str | Path = "outputs/intelligence_phase2/knowledge.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _coerce_datetime(value: Any, *, default: Optional[datetime] = None) -> datetime:
        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str):
            text = value.strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            dt = datetime.fromisoformat(text)
        else:
            dt = default or datetime.now(timezone.utc)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        cols = {row["name"] for row in self._conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def _migrate_screen_snapshots_asset_key(self) -> None:
        row = self._conn.execute(
            """
            SELECT sql
            FROM sqlite_master
            WHERE type = 'table' AND name = 'screen_snapshots'
            """
        ).fetchone()
        if row is None or row[0] is None:
            return
        normalized_sql = str(row[0]).replace(" ", "").replace("\n", "").lower()
        if "unique(ticker,snapshot_date,asset_id)" in normalized_sql:
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_screen_snapshots_asset_date
                    ON screen_snapshots(asset_id, snapshot_date DESC)
                """
            )
            return

        columns = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(screen_snapshots)").fetchall()
        }
        select_expr = {
            "snapshot_id": "snapshot_id",
            "ticker": "ticker",
            "asset_id": "COALESCE(asset_id, '')" if "asset_id" in columns else "''",
            "snapshot_date": "snapshot_date",
            "program_label": "program_label" if "program_label" in columns else "NULL",
            "stage": "stage" if "stage" in columns else "NULL",
            "ta": "ta" if "ta" in columns else "NULL",
            "model_pos": "model_pos" if "model_pos" in columns else "NULL",
            "implied_pos": "implied_pos" if "implied_pos" in columns else "NULL",
            "spread_pp": "spread_pp" if "spread_pp" in columns else "NULL",
            "rnpv_millions": "rnpv_millions" if "rnpv_millions" in columns else "NULL",
            "ev_millions": "ev_millions" if "ev_millions" in columns else "NULL",
            "acquisition_discount_pct": (
                "acquisition_discount_pct" if "acquisition_discount_pct" in columns else "NULL"
            ),
            "next_catalyst": "next_catalyst" if "next_catalyst" in columns else "NULL",
            "catalyst_date": "catalyst_date" if "catalyst_date" in columns else "NULL",
            "days_to_catalyst": "days_to_catalyst" if "days_to_catalyst" in columns else "NULL",
            "single_asset": "single_asset" if "single_asset" in columns else "1",
            "approximation_warning": (
                "approximation_warning" if "approximation_warning" in columns else "NULL"
            ),
            "thesis_strength": "thesis_strength" if "thesis_strength" in columns else "NULL",
            "market_exceeds_model": (
                "market_exceeds_model" if "market_exceeds_model" in columns else "0"
            ),
            "config_quality": "config_quality" if "config_quality" in columns else "NULL",
            "created_at": "created_at" if "created_at" in columns else "CURRENT_TIMESTAMP",
        }
        target_columns = list(select_expr.keys())
        select_sql = ",\n                ".join(select_expr[column] for column in target_columns)
        insert_columns_sql = ", ".join(target_columns)

        self._conn.executescript(
            f"""
            CREATE TABLE IF NOT EXISTS screen_snapshots__migrated (
                snapshot_id       TEXT PRIMARY KEY,
                ticker            TEXT NOT NULL,
                asset_id          TEXT NOT NULL DEFAULT '',
                snapshot_date     TEXT NOT NULL,
                program_label     TEXT,
                stage             TEXT,
                ta                TEXT,
                model_pos         REAL,
                implied_pos       REAL,
                spread_pp         REAL,
                rnpv_millions     REAL,
                ev_millions       REAL,
                acquisition_discount_pct REAL,
                next_catalyst     TEXT,
                catalyst_date     TEXT,
                days_to_catalyst  INTEGER,
                single_asset      INTEGER NOT NULL DEFAULT 1,
                approximation_warning TEXT,
                thesis_strength   REAL,
                market_exceeds_model INTEGER NOT NULL DEFAULT 0,
                config_quality    TEXT,
                created_at        TEXT NOT NULL,
                UNIQUE(ticker, snapshot_date, asset_id)
            );
            INSERT OR REPLACE INTO screen_snapshots__migrated({insert_columns_sql})
            SELECT
                {select_sql}
            FROM screen_snapshots;
            DROP TABLE screen_snapshots;
            ALTER TABLE screen_snapshots__migrated RENAME TO screen_snapshots;
            CREATE INDEX IF NOT EXISTS idx_screen_snapshots_date
                ON screen_snapshots(snapshot_date DESC);
            CREATE INDEX IF NOT EXISTS idx_screen_snapshots_ticker_date
                ON screen_snapshots(ticker, snapshot_date DESC);
            CREATE INDEX IF NOT EXISTS idx_screen_snapshots_asset_date
                ON screen_snapshots(asset_id, snapshot_date DESC);
            """
        )

    def _init_schema(self) -> None:
        # Pre-migration: add columns that the executescript's CREATE INDEX
        # statements reference, before the script runs.  Guard against the
        # table not yet existing (fresh DB — executescript will create it).
        tables = {
            row[0]
            for row in self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "structured_signals" in tables:
            self._ensure_column("structured_signals", "extraction_result_id", "TEXT")
            self._ensure_column("structured_signals", "created_at", "TEXT")
        if "screen_snapshots" in tables:
            self._ensure_column("screen_snapshots", "asset_id", "TEXT NOT NULL DEFAULT ''")

        cur = self._conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS raw_documents (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                source TEXT,
                document_hash TEXT,
                source_url TEXT,
                payload_json TEXT NOT NULL,
                source_trace_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS extraction_results (
                id TEXT PRIMARY KEY,
                raw_document_id TEXT,
                signal_id TEXT,
                event_id TEXT,
                company_id TEXT,
                asset_id TEXT,
                event_type TEXT,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                source_trace_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS processed_document_hashes (
                source TEXT NOT NULL,
                document_hash TEXT NOT NULL,
                raw_document_id TEXT,
                first_processed_at TEXT NOT NULL,
                last_processed_at TEXT NOT NULL,
                PRIMARY KEY(source, document_hash)
            );

            CREATE TABLE IF NOT EXISTS structured_signals (
                id TEXT PRIMARY KEY,
                extraction_result_id TEXT,
                event_id TEXT,
                company_id TEXT,
                asset_id TEXT,
                event_type TEXT,
                signal_date TEXT,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                source_trace_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS evidence_facts (
                fact_id TEXT PRIMARY KEY,
                company_id TEXT NOT NULL,
                asset_id TEXT NOT NULL,
                fact_namespace TEXT NOT NULL,
                fact_key TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                conflict_status TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                source_trace_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                event_key TEXT,
                signal_id TEXT,
                company_id TEXT,
                asset_id TEXT,
                indication_id TEXT,
                event_type TEXT,
                observed_at TEXT,
                ingested_at TEXT,
                source_url TEXT,
                source_type TEXT,
                headline TEXT,
                confidence REAL,
                payload_json TEXT NOT NULL,
                source_trace_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS valuation_diffs (
                run_id TEXT PRIMARY KEY,
                company_id TEXT,
                asset_id TEXT,
                event_id TEXT,
                created_at TEXT,
                delta_npv REAL,
                payload_json TEXT NOT NULL,
                assumptions_snapshot_json TEXT,
                valuation_snapshot_json TEXT,
                source_trace_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS score_updates (
                id TEXT PRIMARY KEY,
                run_id TEXT,
                asset_id TEXT NOT NULL,
                as_of TEXT NOT NULL,
                prior_score REAL,
                new_score REAL NOT NULL,
                delta REAL NOT NULL,
                decision TEXT NOT NULL DEFAULT 'auto_apply',
                components_json TEXT,
                contributing_signal_ids_json TEXT,
                contributing_event_ids_json TEXT,
                source_trace_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS run_state (
                run_id TEXT NOT NULL,
                stage TEXT NOT NULL,
                asset_id TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                checkpoint_json TEXT,
                error_json TEXT,
                PRIMARY KEY(run_id, stage, asset_id)
            );

            CREATE TABLE IF NOT EXISTS data_quality_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                asset_id TEXT NOT NULL,
                check_name TEXT NOT NULL,
                status TEXT NOT NULL,
                severity TEXT NOT NULL,
                reason TEXT NOT NULL,
                value TEXT,
                threshold TEXT,
                overall_score REAL NOT NULL DEFAULT 0.0,
                gated INTEGER NOT NULL DEFAULT 0,
                details_json TEXT NOT NULL DEFAULT '{}',
                checked_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS kg_integrity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_json TEXT NOT NULL,
                passed INTEGER NOT NULL,
                checked_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS opportunity_alerts (
                asset_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                window TEXT NOT NULL,
                run_id TEXT,
                created_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                PRIMARY KEY(asset_id, event_type, window)
            );

            CREATE TABLE IF NOT EXISTS backtest_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                alert_id TEXT NOT NULL,
                asset_id TEXT NOT NULL,
                signal_date TEXT NOT NULL,
                signal_id TEXT,
                signal_timestamp TEXT,
                composite_score REAL,
                extraction_confidence REAL,
                delta_npv_millions REAL,
                intrinsic_value_millions REAL,
                mispricing_score REAL,
                catalyst_date TEXT,
                catalyst_type TEXT,
                catalyst_score REAL,
                rank_at_signal INTEGER,
                model_version TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS asset_registry (
                asset_id TEXT PRIMARY KEY,
                ticker TEXT,
                company_id TEXT,
                drug_name TEXT,
                indication TEXT,
                therapeutic_area TEXT,
                modality TEXT,
                stage TEXT,
                nct_id TEXT,
                tam_millions REAL,
                created_at TEXT NOT NULL,
                source TEXT NOT NULL,
                last_competitor_discovery_at TEXT,
                UNIQUE(ticker, drug_name, indication)
            );

            CREATE TABLE IF NOT EXISTS review_decisions (
                id TEXT PRIMARY KEY,
                proposal_id TEXT,
                run_id TEXT,
                company_id TEXT,
                asset_id TEXT,
                decision TEXT,
                reviewer_id TEXT,
                reviewed_at TEXT,
                override_value REAL,
                rationale TEXT,
                notes TEXT,
                payload_json TEXT NOT NULL,
                source_trace_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS memos (
                id TEXT PRIMARY KEY,
                company_id TEXT,
                asset_id TEXT,
                memo_type TEXT,
                title TEXT,
                created_at TEXT,
                payload_json TEXT NOT NULL,
                source_trace_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS dossiers (
                id TEXT PRIMARY KEY,
                company_id TEXT,
                asset_id TEXT,
                generated_at TEXT,
                payload_json TEXT NOT NULL,
                source_trace_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS literature_reviews (
                id TEXT PRIMARY KEY,
                company_id TEXT,
                asset_id TEXT,
                generated_at TEXT,
                payload_json TEXT NOT NULL,
                source_trace_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS competitive_landscapes (
                id TEXT PRIMARY KEY,
                company_id TEXT,
                asset_id TEXT,
                generated_at TEXT,
                payload_json TEXT NOT NULL,
                source_trace_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS research_reports (
                id TEXT PRIMARY KEY,
                company_id TEXT,
                asset_id TEXT,
                report_version TEXT,
                model_version TEXT,
                generated_at TEXT,
                payload_json TEXT NOT NULL,
                source_trace_json TEXT NOT NULL
            );

            -- Market price history (1A).  adj_close is the canonical price series.
            -- Unique on (ticker, price_date) — idempotent upserts.
            CREATE TABLE IF NOT EXISTS market_prices (
                ticker TEXT NOT NULL,
                price_date TEXT NOT NULL,
                close_usd REAL,
                adj_close_usd REAL,
                volume INTEGER,
                market_cap_millions REAL,
                is_adjusted INTEGER NOT NULL DEFAULT 1,
                source TEXT NOT NULL DEFAULT 'yfinance',
                ingested_at TEXT NOT NULL,
                PRIMARY KEY (ticker, price_date)
            );

            -- Event outcomes (1B).  One row per event; T-windows resolved incrementally.
            -- signal_date + trading-day arithmetic determines resolution schedule.
            CREATE TABLE IF NOT EXISTS event_outcomes (
                outcome_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL UNIQUE,
                asset_id TEXT NOT NULL,
                ticker TEXT,
                signal_date TEXT NOT NULL,
                event_type TEXT,
                model_delta_npv REAL,
                model_delta_pct REAL,
                volume_spike_at_signal INTEGER DEFAULT 0,
                price_before REAL,
                price_t1 REAL,     market_return_t1 REAL,     resolved_t1 INTEGER DEFAULT 0,
                price_t5 REAL,     market_return_t5 REAL,     resolved_t5 INTEGER DEFAULT 0,
                price_t30 REAL,    market_return_t30 REAL,    resolved_t30 INTEGER DEFAULT 0,
                price_t90 REAL,    market_return_t90 REAL,    resolved_t90 INTEGER DEFAULT 0,
                price_t180 REAL,   market_return_t180 REAL,   resolved_t180 INTEGER DEFAULT 0,
                fully_resolved INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            -- Market expectation modeling (1D).  Implied PoS back-solved from market cap.
            CREATE TABLE IF NOT EXISTS market_expectations (
                expectation_id TEXT PRIMARY KEY,
                asset_id TEXT NOT NULL,
                ticker TEXT NOT NULL,
                expectation_date TEXT NOT NULL,
                implied_pos REAL,
                model_pos REAL,
                pos_gap REAL,
                cash_estimate_millions REAL,
                methodology TEXT NOT NULL DEFAULT 'nav_backsolve',
                computed_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS acquisition_discount_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                asset_id TEXT NOT NULL,
                ticker TEXT,
                snapshot_date TEXT NOT NULL,
                formula_version TEXT NOT NULL,
                model_rnpv_millions REAL,
                model_pos REAL,
                market_cap_millions REAL,
                market_cap_as_of TEXT,
                market_cap_source TEXT,
                enterprise_value_millions REAL,
                net_cash_millions REAL,
                ev_methodology TEXT NOT NULL,
                acquisition_discount REAL,
                passes_threshold INTEGER NOT NULL DEFAULT 0,
                exclusion_reason TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(asset_id, snapshot_date, formula_version)
            );

            -- Cross-asset propagation proposals (Wave D).
            -- Generated when a trigger signal (competitor failure, safety event)
            -- implies a valuation assumption change on a peer asset.
            CREATE TABLE IF NOT EXISTS propagation_proposals (
                proposal_id   TEXT PRIMARY KEY,
                source_asset_id   TEXT NOT NULL,
                target_asset_id   TEXT NOT NULL,
                propagation_type  TEXT NOT NULL,
                calibration_confidence REAL NOT NULL DEFAULT 0.0,
                sample_size       INTEGER NOT NULL DEFAULT 0,
                proposal_json     TEXT NOT NULL,
                status            TEXT NOT NULL DEFAULT 'pending',
                created_at        TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_propagation_proposals_target
                ON propagation_proposals(target_asset_id, status, created_at);

            -- Universe implied PoS screen snapshots (Sprint 10 / Task 10.4).
            -- One row per modeled asset per snapshot_date (UPSERT semantics).
            CREATE TABLE IF NOT EXISTS screen_snapshots (
                snapshot_id       TEXT PRIMARY KEY,
                ticker            TEXT NOT NULL,
                asset_id          TEXT NOT NULL DEFAULT '',
                snapshot_date     TEXT NOT NULL,
                program_label     TEXT,
                stage             TEXT,
                ta                TEXT,
                model_pos         REAL,
                implied_pos       REAL,
                spread_pp         REAL,
                rnpv_millions     REAL,
                ev_millions       REAL,
                acquisition_discount_pct REAL,
                next_catalyst     TEXT,
                catalyst_date     TEXT,
                days_to_catalyst  INTEGER,
                single_asset      INTEGER NOT NULL DEFAULT 1,
                approximation_warning TEXT,
                thesis_strength   REAL,
                market_exceeds_model INTEGER NOT NULL DEFAULT 0,
                config_quality    TEXT,
                created_at        TEXT NOT NULL,
                UNIQUE(ticker, snapshot_date, asset_id)
            );
            CREATE INDEX IF NOT EXISTS idx_screen_snapshots_date
                ON screen_snapshots(snapshot_date DESC);
            CREATE INDEX IF NOT EXISTS idx_screen_snapshots_ticker_date
                ON screen_snapshots(ticker, snapshot_date DESC);
            CREATE INDEX IF NOT EXISTS idx_screen_snapshots_asset_date
                ON screen_snapshots(asset_id, snapshot_date DESC);

            CREATE TABLE IF NOT EXISTS company_sotp_snapshots (
                snapshot_id       TEXT PRIMARY KEY,
                ticker            TEXT NOT NULL,
                company_id        TEXT NOT NULL,
                company_name      TEXT NOT NULL,
                snapshot_date     TEXT NOT NULL,
                rank              INTEGER NOT NULL DEFAULT 0,
                market_cap_millions REAL NOT NULL,
                enterprise_value_millions REAL NOT NULL,
                sotp_equity_value_millions REAL NOT NULL,
                sotp_per_share    REAL NOT NULL,
                sotp_discount     REAL NOT NULL,
                ranked_sotp_discount REAL NOT NULL,
                reconciliation_gap_millions REAL NOT NULL DEFAULT 0.0,
                reconciliation_gap_pct REAL NOT NULL DEFAULT 0.0,
                reconciliation_status TEXT,
                reconciliation_passes_gate INTEGER NOT NULL DEFAULT 1,
                mcap_trend_3m_pct REAL,
                sotp_tier TEXT,
                sotp_action TEXT,
                sotp_confidence_tier TEXT,
                sotp_tier_reason TEXT,
                modeled_asset_coverage_pct REAL NOT NULL,
                asset_count_modeled INTEGER NOT NULL DEFAULT 0,
                modeled_asset_ids_json TEXT NOT NULL,
                config_quality_summary TEXT,
                modeled_asset_confidence_min REAL,
                modeled_asset_confidence_avg REAL,
                manual_bucket_share_pct REAL NOT NULL DEFAULT 0.0,
                manual_bucket_confidence_avg REAL,
                n_bucket_sources INTEGER NOT NULL DEFAULT 0,
                action_policy     TEXT,
                action_reason     TEXT,
                market_cap_source TEXT,
                balance_sheet_source TEXT,
                balance_sheet_source_ref TEXT,
                balance_sheet_snapshot_date TEXT,
                balance_sheet_period_end_date TEXT,
                balance_sheet_form_type TEXT,
                balance_sheet_is_point_in_time INTEGER NOT NULL DEFAULT 0,
                balance_sheet_age_days INTEGER,
                balance_sheet_passes_recency_gate INTEGER NOT NULL DEFAULT 0,
                balance_sheet_recency_penalty REAL NOT NULL DEFAULT 1.0,
                bucket_count      INTEGER NOT NULL DEFAULT 0,
                buckets_json      TEXT NOT NULL,
                limitations_json  TEXT NOT NULL,
                notes             TEXT,
                created_at        TEXT NOT NULL,
                UNIQUE(ticker, snapshot_date)
            );
            CREATE INDEX IF NOT EXISTS idx_company_sotp_snapshots_date
                ON company_sotp_snapshots(snapshot_date DESC);
            CREATE INDEX IF NOT EXISTS idx_company_sotp_snapshots_ticker_date
                ON company_sotp_snapshots(ticker, snapshot_date DESC);

            CREATE TABLE IF NOT EXISTS equity_policy_snapshots (
                snapshot_id       TEXT PRIMARY KEY,
                ticker            TEXT NOT NULL,
                as_of_date        TEXT NOT NULL,
                reference_snapshot_date TEXT,
                company_snapshot_date TEXT,
                source_mode       TEXT NOT NULL,
                company_action_policy TEXT,
                company_action_reason TEXT,
                company_ranked_discount REAL,
                composite_score   REAL,
                current_price     REAL,
                base_sotp_per_share REAL,
                bear_sotp_per_share REAL,
                bull_sotp_per_share REAL,
                conviction        REAL,
                adv_millions      REAL,
                next_catalyst_days INTEGER,
                catalyst_description TEXT,
                action            TEXT NOT NULL,
                sizing_pct        REAL NOT NULL DEFAULT 0.0,
                rationale         TEXT NOT NULL,
                created_at        TEXT NOT NULL,
                UNIQUE(ticker, as_of_date)
            );
            CREATE INDEX IF NOT EXISTS idx_equity_policy_snapshots_as_of
                ON equity_policy_snapshots(as_of_date DESC);
            CREATE INDEX IF NOT EXISTS idx_equity_policy_snapshots_ticker_as_of
                ON equity_policy_snapshots(ticker, as_of_date DESC);

            -- Rules-based universe snapshots (Sprint 12B).
            -- Each row captures the filter result for one ticker on one build date.
            CREATE TABLE IF NOT EXISTS universe_snapshots (
                snapshot_id    TEXT PRIMARY KEY,
                ticker         TEXT NOT NULL,
                build_date     TEXT NOT NULL,
                company_name   TEXT,
                market_cap_m   REAL,
                adv_m          REAL,
                has_phase2_plus INTEGER NOT NULL DEFAULT 0,
                active_nct_ids TEXT,           -- JSON array of NCT IDs
                passed         INTEGER NOT NULL DEFAULT 0,
                exclusion_reason TEXT,
                sources        TEXT,            -- JSON array of source names
                created_at     TEXT NOT NULL,
                UNIQUE(ticker, build_date)
            );
            CREATE INDEX IF NOT EXISTS idx_universe_snapshots_date
                ON universe_snapshots(build_date DESC);
            CREATE INDEX IF NOT EXISTS idx_universe_snapshots_passed
                ON universe_snapshots(build_date, passed);

            CREATE TABLE IF NOT EXISTS pos_predictions (
                id              TEXT PRIMARY KEY,
                program_id      TEXT NOT NULL,
                ticker          TEXT NOT NULL,
                ta              TEXT,
                phase           TEXT,
                model_pos       REAL NOT NULL,
                implied_pos     REAL,
                spread_pp       REAL,
                peak_sales_millions REAL,
                rnpv_millions   REAL,
                predicted_at    TEXT NOT NULL,
                trial_end_expected TEXT,
                created_at      TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_pos_predictions_program
                ON pos_predictions(program_id, predicted_at DESC);
            CREATE INDEX IF NOT EXISTS idx_pos_predictions_ticker
                ON pos_predictions(ticker, predicted_at DESC);

            CREATE TABLE IF NOT EXISTS pos_outcomes (
                id              TEXT PRIMARY KEY,
                program_id      TEXT NOT NULL,
                outcome_date    TEXT,
                outcome_type    TEXT CHECK(outcome_type IN (
                    'approval', 'crl', 'failure_efficacy', 'failure_safety',
                    'partial_approval', 'discontinued', 'ongoing'
                )),
                trial_name      TEXT,
                source          TEXT,
                created_at      TEXT NOT NULL,
                UNIQUE(program_id)
            );
            CREATE INDEX IF NOT EXISTS idx_pos_outcomes_program
                ON pos_outcomes(program_id);

            CREATE TABLE IF NOT EXISTS detected_events (
                id              TEXT PRIMARY KEY,
                ticker          TEXT NOT NULL,
                asset_id        TEXT NOT NULL,
                event_type      TEXT NOT NULL,
                headline        TEXT NOT NULL,
                headline_key    TEXT NOT NULL,  -- first 80 chars for dedup
                source_url      TEXT,
                detected_at     TEXT NOT NULL,
                detected_date   TEXT NOT NULL,  -- YYYY-MM-DD for dedup
                requires_recompute INTEGER NOT NULL DEFAULT 0,
                extra_json      TEXT,
                created_at      TEXT NOT NULL,
                UNIQUE(ticker, event_type, headline_key, detected_date)
            );
            CREATE INDEX IF NOT EXISTS idx_detected_events_ticker
                ON detected_events(ticker);
            CREATE INDEX IF NOT EXISTS idx_detected_events_detected_at
                ON detected_events(detected_at DESC);
            CREATE INDEX IF NOT EXISTS idx_detected_events_recompute
                ON detected_events(requires_recompute, detected_at DESC);

            CREATE INDEX IF NOT EXISTS idx_raw_documents_created
                ON raw_documents(created_at);
            CREATE INDEX IF NOT EXISTS idx_raw_documents_hash
                ON raw_documents(document_hash);
            CREATE INDEX IF NOT EXISTS idx_processed_document_hashes_last_processed
                ON processed_document_hashes(last_processed_at);
            CREATE INDEX IF NOT EXISTS idx_extractions_raw_document
                ON extraction_results(raw_document_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_extractions_company_asset
                ON extraction_results(company_id, asset_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_signals_extraction
                ON structured_signals(extraction_result_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_signals_event
                ON structured_signals(event_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_signals_company_asset
                ON structured_signals(company_id, asset_id, signal_date);
            CREATE INDEX IF NOT EXISTS idx_signals_type_date
                ON structured_signals(event_type, signal_date);
            CREATE INDEX IF NOT EXISTS idx_evidence_facts_entity_key
                ON evidence_facts(company_id, asset_id, fact_key, created_at);
            CREATE INDEX IF NOT EXISTS idx_evidence_facts_active
                ON evidence_facts(is_active, fact_key, created_at);

            CREATE INDEX IF NOT EXISTS idx_events_signal
                ON events(signal_id);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_events_event_key_unique
                ON events(event_key);
            CREATE INDEX IF NOT EXISTS idx_events_company_asset_date
                ON events(company_id, asset_id, observed_at);
            CREATE INDEX IF NOT EXISTS idx_events_type_date
                ON events(event_type, observed_at);

            CREATE INDEX IF NOT EXISTS idx_diffs_company_asset_date
                ON valuation_diffs(company_id, asset_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_diffs_event_date
                ON valuation_diffs(event_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_run_state_run_asset
                ON run_state(run_id, asset_id, stage);
            CREATE INDEX IF NOT EXISTS idx_run_state_stage_status
                ON run_state(stage, status, started_at);
            CREATE INDEX IF NOT EXISTS idx_data_quality_asset_checked
                ON data_quality_log(asset_id, checked_at);
            CREATE INDEX IF NOT EXISTS idx_data_quality_checked_at
                ON data_quality_log(checked_at);
            CREATE INDEX IF NOT EXISTS idx_data_quality_run_id
                ON data_quality_log(run_id);
            CREATE INDEX IF NOT EXISTS idx_kg_integrity_checked_at
                ON kg_integrity_log(checked_at);
            CREATE INDEX IF NOT EXISTS idx_opportunity_alerts_created
                ON opportunity_alerts(created_at);
            CREATE INDEX IF NOT EXISTS idx_backtest_snapshots_asset
                ON backtest_snapshots(asset_id, signal_date);
            CREATE INDEX IF NOT EXISTS idx_backtest_snapshots_signal_ts
                ON backtest_snapshots(signal_timestamp);
            CREATE INDEX IF NOT EXISTS idx_asset_registry_ticker
                ON asset_registry(ticker);
            CREATE INDEX IF NOT EXISTS idx_asset_registry_ta
                ON asset_registry(therapeutic_area);

            CREATE INDEX IF NOT EXISTS idx_reviews_company_asset_date
                ON review_decisions(company_id, asset_id, reviewed_at);
            CREATE INDEX IF NOT EXISTS idx_reviews_run
                ON review_decisions(run_id, reviewed_at);

            CREATE INDEX IF NOT EXISTS idx_memos_company_asset_date
                ON memos(company_id, asset_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_dossiers_company_asset_date
                ON dossiers(company_id, asset_id, generated_at);
            CREATE INDEX IF NOT EXISTS idx_lit_reviews_company_asset_date
                ON literature_reviews(company_id, asset_id, generated_at);
            CREATE INDEX IF NOT EXISTS idx_comp_landscapes_company_asset_date
                ON competitive_landscapes(company_id, asset_id, generated_at);
            CREATE INDEX IF NOT EXISTS idx_research_reports_company_asset_date
                ON research_reports(company_id, asset_id, generated_at);
            CREATE INDEX IF NOT EXISTS idx_prices_ticker_date
                ON market_prices(ticker, price_date);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_outcomes_event_unique
                ON event_outcomes(event_id);
            CREATE INDEX IF NOT EXISTS idx_outcomes_asset_date
                ON event_outcomes(asset_id, signal_date);
            CREATE INDEX IF NOT EXISTS idx_outcomes_unresolved
                ON event_outcomes(fully_resolved, signal_date);
            CREATE INDEX IF NOT EXISTS idx_expectations_asset_date
                ON market_expectations(asset_id, expectation_date);
            CREATE INDEX IF NOT EXISTS idx_acquisition_discount_asset_date
                ON acquisition_discount_snapshots(asset_id, snapshot_date DESC);
            CREATE INDEX IF NOT EXISTS idx_acquisition_discount_threshold
                ON acquisition_discount_snapshots(
                    snapshot_date, passes_threshold, acquisition_discount DESC
                );

            -- Knowledge graph (2A).
            CREATE TABLE IF NOT EXISTS kg_nodes (
                node_id TEXT PRIMARY KEY,
                node_type TEXT NOT NULL,
                name TEXT NOT NULL,
                external_id TEXT,
                properties_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS kg_edges (
                edge_id TEXT PRIMARY KEY,
                source_node_id TEXT NOT NULL,
                target_node_id TEXT NOT NULL,
                edge_type TEXT NOT NULL,
                confidence REAL NOT NULL DEFAULT 1.0,
                source_signal_id TEXT,
                properties_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                UNIQUE(source_node_id, target_node_id, edge_type)
            );

            CREATE INDEX IF NOT EXISTS idx_kg_nodes_type
                ON kg_nodes(node_type);
            CREATE INDEX IF NOT EXISTS idx_kg_nodes_external
                ON kg_nodes(external_id);
            CREATE INDEX IF NOT EXISTS idx_kg_edges_source
                ON kg_edges(source_node_id, edge_type);
            CREATE INDEX IF NOT EXISTS idx_kg_edges_target
                ON kg_edges(target_node_id, edge_type);
            CREATE INDEX IF NOT EXISTS idx_kg_edges_type
                ON kg_edges(edge_type);

            -- Competitor programs (2B).
            -- UNIQUE(asset_id, nct_id) prevents duplicates across discovery runs.
            -- nct_id may be NULL for programs without a registered trial.
            CREATE TABLE IF NOT EXISTS competitor_programs (
                program_id TEXT PRIMARY KEY,
                asset_id TEXT NOT NULL,
                company TEXT,
                drug_name TEXT NOT NULL,
                nct_id TEXT,
                phase TEXT,
                status TEXT,
                primary_endpoint_type TEXT,
                indication TEXT NOT NULL,
                discovered_at TEXT NOT NULL,
                UNIQUE(asset_id, nct_id)
            );

            CREATE INDEX IF NOT EXISTS idx_competitor_programs_asset
                ON competitor_programs(asset_id);
            CREATE INDEX IF NOT EXISTS idx_competitor_programs_indication
                ON competitor_programs(indication);

            -- Event impact scores (3A).
            -- UNIQUE(event_type, trial_phase, endpoint_type) — upsert on recompute.
            CREATE TABLE IF NOT EXISTS event_scores (
                score_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                trial_phase TEXT,
                endpoint_type TEXT,
                observation_count INTEGER NOT NULL,
                mean_return_t30 REAL,
                mean_return_t180 REAL,
                active INTEGER NOT NULL DEFAULT 0,
                half_life_days REAL NOT NULL DEFAULT 180.0,
                computed_at TEXT NOT NULL,
                UNIQUE(event_type, trial_phase, endpoint_type)
            );

            CREATE INDEX IF NOT EXISTS idx_event_scores_type
                ON event_scores(event_type);

            -- Forecast records (3B).
            -- One row per signal; unique on signal_id.
            -- Actuals filled by resolve_forecasts() when event_outcomes resolves.
            -- horizon_days: which return window the prediction is evaluated against (default 30).
            -- predicted_at: when the prediction was generated (signal extraction time).
            -- created_at:   when the row was written to the DB (may differ from predicted_at
            --               if ingestion is delayed).
            CREATE TABLE IF NOT EXISTS forecast_records (
                forecast_id TEXT PRIMARY KEY,
                signal_id TEXT NOT NULL UNIQUE,
                event_id TEXT NOT NULL,
                asset_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                signal_date TEXT NOT NULL,
                extraction_confidence REAL NOT NULL DEFAULT 0.0,
                predicted_direction TEXT NOT NULL,
                predicted_delta_pct REAL,
                horizon_days INTEGER NOT NULL DEFAULT 30,
                predicted_at TEXT NOT NULL,
                actual_market_return_t30 REAL,
                actual_market_return_t180 REAL,
                outcome_correct INTEGER,
                resolved INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_forecast_records_event_id
                ON forecast_records(event_id);
            CREATE INDEX IF NOT EXISTS idx_forecast_records_asset_resolved
                ON forecast_records(asset_id, resolved);

            -- Audit log (3C).
            -- Append-only.  Rows are NEVER updated or deleted.
            -- Records every review decision with full payload for reproducibility.
            CREATE TABLE IF NOT EXISTS audit_log (
                audit_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,    -- e.g. "review_decision"
                entity_type TEXT NOT NULL,   -- e.g. "proposal"
                entity_id TEXT NOT NULL,
                actor_id TEXT,               -- reviewer_id or system actor
                action TEXT NOT NULL,        -- e.g. "accepted", "rejected", "deferred"
                payload_json TEXT NOT NULL,  -- full ReviewDecision JSON
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_audit_log_entity
                ON audit_log(entity_type, entity_id);
            CREATE INDEX IF NOT EXISTS idx_audit_log_actor_date
                ON audit_log(actor_id, created_at);

            -- Catalyst events (Wave 1).
            -- One row per catalyst; EV fields updated in place by CatalystEVCalculator.
            CREATE TABLE IF NOT EXISTS catalyst_events (
                id TEXT PRIMARY KEY,
                asset_id TEXT,
                company_id TEXT,
                catalyst_type TEXT NOT NULL,
                expected_date TEXT NOT NULL,
                date_confidence TEXT NOT NULL,
                source TEXT NOT NULL,
                description TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                resolved INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_catalyst_events_asset
                ON catalyst_events(asset_id);
            CREATE INDEX IF NOT EXISTS idx_catalyst_events_date
                ON catalyst_events(expected_date);
            CREATE INDEX IF NOT EXISTS idx_catalyst_events_active_date
                ON catalyst_events(is_active, expected_date);

            -- Enrollment snapshots (Wave 3).
            -- UNIQUE(nct_id, snapshot_date) ensures one row per trial per day.
            CREATE TABLE IF NOT EXISTS enrollment_snapshots (
                id TEXT PRIMARY KEY,
                nct_id TEXT NOT NULL,
                asset_id TEXT NOT NULL,
                snapshot_date TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(nct_id, snapshot_date)
            );

            CREATE INDEX IF NOT EXISTS idx_enrollment_nct_date
                ON enrollment_snapshots(nct_id, snapshot_date);
            CREATE INDEX IF NOT EXISTS idx_enrollment_asset_date
                ON enrollment_snapshots(asset_id, snapshot_date);

            -- Outcome override log (Wave 0.5 — outcome resolution audit).
            -- Append-only.  Rows are NEVER updated or deleted.
            -- Records every manual correction to an event_outcome label so
            -- the learning loop uses human-verified truth, not raw automation.
            CREATE TABLE IF NOT EXISTS outcome_override_log (
                override_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                original_label TEXT,
                corrected_label TEXT NOT NULL,
                reason TEXT,
                operator_id TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_outcome_override_event
                ON outcome_override_log(event_id);

            -- Forward paper tracking log (Task 23).
            -- One row per (date, asset) — represents what we would recommend
            -- without committing real capital.  Append via INSERT OR REPLACE.
            CREATE TABLE IF NOT EXISTS paper_tracking_log (
                entry_id           TEXT PRIMARY KEY,
                snapshot_date      TEXT NOT NULL,
                asset_id           TEXT NOT NULL,
                ticker             TEXT,
                recommendation     TEXT NOT NULL,
                composite_score    REAL,
                mna_likelihood     REAL,
                predicted_acquirer TEXT,
                catalyst           TEXT,
                thesis             TEXT,
                risk_flags         TEXT,
                created_at         TEXT NOT NULL,
                UNIQUE(snapshot_date, asset_id)
            );

            CREATE INDEX IF NOT EXISTS idx_paper_tracking_log_date
                ON paper_tracking_log(snapshot_date);

            CREATE INDEX IF NOT EXISTS idx_paper_tracking_log_asset
                ON paper_tracking_log(asset_id, snapshot_date);
            """
        )

        # Backward-compatible migration path for existing databases.
        self._ensure_column("raw_documents", "source", "TEXT")
        self._ensure_column("raw_documents", "document_hash", "TEXT")
        self._ensure_column("events", "event_key", "TEXT")
        self._ensure_column("events", "signal_id", "TEXT")
        self._ensure_column("valuation_diffs", "created_at", "TEXT")
        self._ensure_column("valuation_diffs", "market_cap_snapshot_millions", "REAL")
        self._ensure_column("data_quality_log", "run_id", "TEXT")
        self._ensure_column("data_quality_log", "check_name", "TEXT")
        self._ensure_column("data_quality_log", "status", "TEXT")
        self._ensure_column("data_quality_log", "severity", "TEXT")
        self._ensure_column("data_quality_log", "reason", "TEXT")
        self._ensure_column("data_quality_log", "value", "TEXT")
        self._ensure_column("data_quality_log", "threshold", "TEXT")
        self._ensure_column("data_quality_log", "details_json", "TEXT")
        self._ensure_column("backtest_snapshots", "signal_id", "TEXT")
        self._ensure_column("backtest_snapshots", "signal_timestamp", "TEXT")
        self._ensure_column("backtest_snapshots", "intrinsic_value_millions", "REAL")
        self._ensure_column("backtest_snapshots", "catalyst_score", "REAL")
        self._ensure_column("research_reports", "report_version", "TEXT")
        self._ensure_column("research_reports", "model_version", "TEXT")
        # Sprint 23 Task 5: forward paper log new fields.
        self._ensure_column("paper_tracking_log", "watchlist_type", "TEXT")
        self._ensure_column("paper_tracking_log", "calibrated_score", "REAL")
        self._ensure_column("paper_tracking_log", "calibrated_score_label", "TEXT")
        self._ensure_column("paper_tracking_log", "transaction_driver_count", "INTEGER")
        self._ensure_column("paper_tracking_log", "gate_reason_codes", "TEXT")
        self._ensure_column("paper_tracking_log", "top5_acquirers", "TEXT")

        # Wave 3C: reviewer annotation columns on review_decisions.
        self._ensure_column("review_decisions", "reviewer_confidence", "REAL")
        self._ensure_column("review_decisions", "analyst_tags_json", "TEXT")
        self._ensure_column("review_decisions", "supporting_quote", "TEXT")

        # Task 9.22: signal → assumption lineage columns on audit_log.
        # These link an accepted review decision to the specific assumption change
        # it triggered, enabling a compliance reviewer to reconstruct "why did X change".
        self._ensure_column("audit_log", "assumption_field", "TEXT")
        self._ensure_column("audit_log", "assumption_old_value", "TEXT")
        self._ensure_column("audit_log", "assumption_new_value", "TEXT")
        self._ensure_column("audit_log", "evidence_signal_id", "TEXT")
        self._ensure_column("audit_log", "review_decision_id", "TEXT")

        # Wave 0.5: outcome truth taxonomy on event_outcomes.
        # outcome_label separates trial truth from market reaction.
        # Values: "trial_success" | "trial_failure" | "ambiguous" |
        #         "market_reaction_only" | "unresolved"
        self._ensure_column("event_outcomes", "outcome_label", "TEXT")
        self._ensure_column("event_outcomes", "outcome_resolution_source", "TEXT")

        # Sprint 25: thesis_strength on screen_snapshots.
        # Populated by weekly_runner via ThesisTracker.snapshot() at screen time.
        self._ensure_column("screen_snapshots", "thesis_strength", "REAL")
        self._ensure_column("screen_snapshots", "asset_id", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column(
            "screen_snapshots",
            "market_exceeds_model",
            "INTEGER NOT NULL DEFAULT 0",
        )
        self._ensure_column("screen_snapshots", "config_quality", "TEXT")
        self._migrate_screen_snapshots_asset_key()
        self._ensure_column("company_sotp_snapshots", "config_quality_summary", "TEXT")
        self._ensure_column("company_sotp_snapshots", "modeled_asset_confidence_min", "REAL")
        self._ensure_column("company_sotp_snapshots", "modeled_asset_confidence_avg", "REAL")
        self._ensure_column("company_sotp_snapshots", "manual_bucket_share_pct", "REAL NOT NULL DEFAULT 0.0")
        self._ensure_column("company_sotp_snapshots", "manual_bucket_confidence_avg", "REAL")
        self._ensure_column("company_sotp_snapshots", "n_bucket_sources", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("company_sotp_snapshots", "action_policy", "TEXT")
        self._ensure_column("company_sotp_snapshots", "action_reason", "TEXT")
        self._ensure_column("company_sotp_snapshots", "market_cap_source", "TEXT")
        self._ensure_column("company_sotp_snapshots", "balance_sheet_source", "TEXT")
        self._ensure_column("company_sotp_snapshots", "balance_sheet_source_ref", "TEXT")
        self._ensure_column("company_sotp_snapshots", "balance_sheet_snapshot_date", "TEXT")
        self._ensure_column("company_sotp_snapshots", "balance_sheet_period_end_date", "TEXT")
        self._ensure_column("company_sotp_snapshots", "balance_sheet_form_type", "TEXT")
        self._ensure_column(
            "company_sotp_snapshots",
            "balance_sheet_is_point_in_time",
            "INTEGER NOT NULL DEFAULT 0",
        )
        self._ensure_column("company_sotp_snapshots", "balance_sheet_age_days", "INTEGER")
        self._ensure_column(
            "company_sotp_snapshots",
            "balance_sheet_passes_recency_gate",
            "INTEGER NOT NULL DEFAULT 0",
        )
        self._ensure_column(
            "company_sotp_snapshots",
            "balance_sheet_recency_penalty",
            "REAL NOT NULL DEFAULT 1.0",
        )
        self._ensure_column("company_sotp_snapshots", "reconciliation_gap_millions", "REAL NOT NULL DEFAULT 0.0")
        self._ensure_column("company_sotp_snapshots", "reconciliation_gap_pct", "REAL NOT NULL DEFAULT 0.0")
        self._ensure_column("company_sotp_snapshots", "reconciliation_status", "TEXT")
        self._ensure_column("company_sotp_snapshots", "reconciliation_passes_gate", "INTEGER NOT NULL DEFAULT 1")
        self._ensure_column("company_sotp_snapshots", "mcap_trend_3m_pct", "REAL")
        self._ensure_column("company_sotp_snapshots", "sotp_tier", "TEXT")
        self._ensure_column("company_sotp_snapshots", "sotp_action", "TEXT")
        self._ensure_column("company_sotp_snapshots", "sotp_confidence_tier", "TEXT")
        self._ensure_column("company_sotp_snapshots", "sotp_tier_reason", "TEXT")
        self._ensure_column("company_sotp_snapshots", "bucket_count", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column("company_sotp_snapshots", "buckets_json", "TEXT")
        self._ensure_column("company_sotp_snapshots", "limitations_json", "TEXT")


        # Wave E-lite: stratification buckets on forecast_records.
        # Required for PoS recalibration by (indication × phase × endpoint_type).
        self._ensure_column("forecast_records", "trial_phase", "TEXT")
        self._ensure_column("forecast_records", "indication", "TEXT")
        self._ensure_column("forecast_records", "endpoint_type", "TEXT")
        self._ensure_column("forecast_records", "outcome_label", "TEXT")

        diff_cols = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(valuation_diffs)").fetchall()
        }
        # Backfill created_at from legacy generated_at if needed.
        if "generated_at" in diff_cols:
            self._conn.execute(
                """
                UPDATE valuation_diffs
                   SET created_at = COALESCE(created_at, generated_at)
                 WHERE created_at IS NULL
                """
            )
        # Backfill deterministic event_key contract for historical rows.
        self._conn.execute(
            """
            UPDATE events
               SET event_key = COALESCE(event_key, id)
             WHERE event_key IS NULL OR event_key = ''
            """
        )
        # Best-effort backfill source from stored payload.
        self._conn.execute(
            """
            UPDATE raw_documents
               SET source = COALESCE(
                   source,
                   json_extract(payload_json, '$.source')
               )
             WHERE source IS NULL OR source = ''
            """
        )
        # Enforce raw-document idempotency key contract: (source, document_hash).
        # Remove historical duplicates first (keep earliest created_at/id) so
        # unique index creation remains backward compatible.
        self._conn.execute(
            """
            DELETE FROM raw_documents
             WHERE id IN (
                SELECT d1.id
                  FROM raw_documents d1
                  JOIN raw_documents d2
                    ON d1.source = d2.source
                   AND d1.document_hash = d2.document_hash
                   AND d1.id <> d2.id
                 WHERE d1.source IS NOT NULL
                   AND d1.source <> ''
                   AND d1.document_hash IS NOT NULL
                   AND d1.document_hash <> ''
                   AND (
                        d1.created_at > d2.created_at
                        OR (d1.created_at = d2.created_at AND d1.id > d2.id)
                   )
            )
            """
        )
        self._conn.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_raw_documents_source_hash_unique
                ON raw_documents(source, document_hash)
            """
        )
        self._conn.execute(
            """
            INSERT OR IGNORE INTO processed_document_hashes(
                source, document_hash, raw_document_id, first_processed_at, last_processed_at
            )
            SELECT
                d.source,
                d.document_hash,
                d.id,
                MIN(er.created_at) AS first_processed_at,
                MAX(er.created_at) AS last_processed_at
            FROM raw_documents d
            JOIN extraction_results er
              ON er.raw_document_id = d.id
            WHERE d.source IS NOT NULL
              AND d.source <> ''
              AND d.document_hash IS NOT NULL
              AND d.document_hash <> ''
            GROUP BY d.source, d.document_hash
            """
        )
        # Backfill defaults for new data_quality_log columns introduced after Sprint 2A.
        self._conn.execute(
            """
            UPDATE data_quality_log
               SET check_name = COALESCE(NULLIF(check_name, ''), 'overall'),
                   status = COALESCE(NULLIF(status, ''), CASE WHEN gated = 1 THEN 'fail' ELSE 'pass' END),
                   severity = COALESCE(NULLIF(severity, ''), CASE WHEN gated = 1 THEN 'warning' ELSE 'info' END),
                   reason = COALESCE(NULLIF(reason, ''), CASE WHEN gated = 1 THEN 'legacy_gated' ELSE 'legacy_pass' END),
                   threshold = COALESCE(threshold, ''),
                   details_json = COALESCE(details_json, '{}')
             WHERE check_name IS NULL
                OR status IS NULL
                OR severity IS NULL
                OR reason IS NULL
                OR details_json IS NULL
            """
        )
        self._conn.commit()

    @staticmethod
    def _event_type_value(event_type: Optional[str | EventType]) -> Optional[str]:
        if event_type is None:
            return None
        if isinstance(event_type, EventType):
            return event_type.value
        return event_type

    @staticmethod
    def _json_dump(payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=True)

    # ---------------------------------------------------------------------
    # Inserts
    # ---------------------------------------------------------------------

    def add_raw_document(
        self,
        raw_document: RawDocument | RawDocumentRecord | dict,
        source_trace: SourceTrace,
    ) -> RawDocumentRecord:
        if isinstance(raw_document, RawDocumentRecord):
            record = raw_document
        else:
            payload = (
                raw_document.model_dump(mode="json")
                if hasattr(raw_document, "model_dump")
                else dict(raw_document)
            )
            record = RawDocumentRecord(
                id=str(payload.get("id")),
                payload_json=payload,
                created_at=self._coerce_datetime(
                    payload.get("created_at") or payload.get("retrieved_at")
                ),
            )

        source_url = record.payload_json.get("source_url")
        document_hash = record.payload_json.get("document_hash")
        source = record.payload_json.get("source")
        # INSERT OR IGNORE: raw documents are immutable content-addressed objects.
        # If the same document (same id = UUID5 from source+hash+asset) is ingested
        # again, silently skip — the content has not changed.
        self._conn.execute(
            """
            INSERT OR IGNORE INTO raw_documents(
                id, created_at, source, document_hash, source_url, payload_json, source_trace_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.created_at.isoformat(),
                source,
                document_hash,
                source_url,
                self._json_dump(record.payload_json),
                source_trace.model_dump_json(),
            ),
        )
        self._conn.commit()
        return record

    def add_extraction_result(
        self,
        extraction_result: ExtractionResult | ExtractionResultRecord | dict,
        source_trace: SourceTrace,
        *,
        raw_document_id: Optional[str] = None,
    ) -> ExtractionResultRecord:
        if isinstance(extraction_result, ExtractionResultRecord):
            record = extraction_result
            payload = record.payload_json
        else:
            payload = (
                extraction_result.model_dump(mode="json")
                if hasattr(extraction_result, "model_dump")
                else dict(extraction_result)
            )
            doc_id = str(
                raw_document_id
                or payload.get("raw_document_id")
                or payload.get("document_id")
                or ""
            )
            if not doc_id:
                raise ValueError(
                    "raw_document_id/document_id is required for extraction result storage"
                )
            extracted_at = payload.get("extracted_at") or payload.get("created_at")
            record = ExtractionResultRecord(
                id=str(payload.get("id") or payload.get("document_id") or uuid.uuid4()),
                raw_document_id=doc_id,
                payload_json=payload,
                created_at=self._coerce_datetime(extracted_at),
            )

        signal_payload = payload.get("signal") if isinstance(payload.get("signal"), dict) else {}
        signal_id = signal_payload.get("id")
        event_id = signal_payload.get("event_id")
        event_type = payload.get("event_type_detected") or signal_payload.get("event_type")
        company_id = payload.get("company_id") or signal_payload.get("company_id")
        asset_id = payload.get("asset_id") or signal_payload.get("asset_id")

        self._conn.execute(
            """
            INSERT OR REPLACE INTO extraction_results(
                id, raw_document_id, signal_id, event_id, company_id, asset_id,
                event_type, created_at, payload_json, source_trace_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.raw_document_id,
                signal_id,
                event_id,
                company_id,
                asset_id,
                event_type,
                record.created_at.isoformat(),
                self._json_dump(record.payload_json),
                source_trace.model_dump_json(),
            ),
        )
        self._mark_processed_document_hash(
            raw_document_id=record.raw_document_id,
            processed_at=record.created_at,
        )
        self._conn.commit()
        return record

    def add_structured_signal(
        self,
        signal: StructuredSignal | StructuredSignalRecord | dict,
        source_trace: SourceTrace,
        *,
        extraction_result_id: Optional[str] = None,
    ) -> StructuredSignalRecord:
        if isinstance(signal, StructuredSignalRecord):
            record = signal
            payload = record.payload_json
        else:
            payload = (
                signal.model_dump(mode="json") if hasattr(signal, "model_dump") else dict(signal)
            )
            x_id = str(payload.get("extraction_result_id") or extraction_result_id or "")
            if not x_id:
                raise ValueError("extraction_result_id is required for structured signal storage")
            record = StructuredSignalRecord(
                id=str(payload.get("id")),
                extraction_result_id=x_id,
                payload_json=payload,
                created_at=self._coerce_datetime(payload.get("created_at")),
            )

        event_id = record.payload_json.get("event_id")
        company_id = record.payload_json.get("company_id")
        asset_id = record.payload_json.get("asset_id")
        event_type = record.payload_json.get("event_type")
        signal_date = record.payload_json.get("signal_date")

        self._conn.execute(
            """
            INSERT OR REPLACE INTO structured_signals(
                id, extraction_result_id, event_id, company_id, asset_id,
                event_type, signal_date, created_at, payload_json, source_trace_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.extraction_result_id,
                event_id,
                company_id,
                asset_id,
                event_type,
                signal_date,
                record.created_at.isoformat(),
                self._json_dump(record.payload_json),
                source_trace.model_dump_json(),
            ),
        )

        # Keep explicit event->signal relationship when the event row already exists.
        if event_id:
            self._conn.execute(
                "UPDATE events SET signal_id = ? WHERE id = ?",
                (record.id, event_id),
            )

        self._conn.commit()
        return record

    def add_evidence_fact(
        self,
        fact: Any,
        source_trace: SourceTrace,
    ) -> EvidenceFactRecord:
        payload = fact.model_dump(mode="json") if hasattr(fact, "model_dump") else dict(fact)
        record = EvidenceFactRecord(
            fact_id=str(payload.get("fact_id")),
            company_id=str(payload.get("company_id")),
            asset_id=str(payload.get("asset_id")),
            fact_namespace=str(payload.get("fact_namespace")),
            fact_key=str(payload.get("fact_key")),
            entity_type=str(payload.get("entity_type")),
            entity_id=str(payload.get("entity_id")),
            source_type=str(
                (payload.get("provenance") or {}).get("source_type")
                or payload.get("source_type")
                or ""
            ),
            conflict_status=str(payload.get("conflict_status") or "pending"),
            is_active=bool(payload.get("is_active")),
            payload_json=payload,
            created_at=self._coerce_datetime(payload.get("created_at")),
        )
        self._conn.execute(
            """
            INSERT OR REPLACE INTO evidence_facts(
                fact_id, company_id, asset_id, fact_namespace, fact_key, entity_type, entity_id,
                source_type, conflict_status, is_active, created_at, payload_json, source_trace_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.fact_id,
                record.company_id,
                record.asset_id,
                record.fact_namespace,
                record.fact_key,
                record.entity_type,
                record.entity_id,
                record.source_type,
                record.conflict_status,
                1 if record.is_active else 0,
                record.created_at.isoformat(),
                self._json_dump(record.payload_json),
                source_trace.model_dump_json(),
            ),
        )
        self._conn.commit()
        return record

    def link_event_signal(self, event_id: str, signal_id: str) -> None:
        """Explicitly link an event to a structured signal."""
        self._conn.execute(
            "UPDATE events SET signal_id = ? WHERE id = ?",
            (signal_id, event_id),
        )
        self._conn.commit()

    def raw_document_exists(self, document_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM raw_documents WHERE id = ? LIMIT 1",
            (document_id,),
        ).fetchone()
        return row is not None

    def processed_document_hash_exists(self, *, source: str, document_hash: str) -> bool:
        """
        True when this (source, document_hash) already has a persisted extraction result.

        This is stricter than raw_document_exists(): a raw document may have been stored
        before a crash, but we only want to skip extraction when the document was actually
        processed by the extractor already.
        """
        row = self._conn.execute(
            """
            SELECT 1
              FROM processed_document_hashes
             WHERE source = ?
               AND document_hash = ?
             LIMIT 1
            """,
            (source, document_hash),
        ).fetchone()
        if row is not None:
            return True

        row = self._conn.execute(
            """
            SELECT 1
              FROM raw_documents d
              JOIN extraction_results er
                ON er.raw_document_id = d.id
             WHERE d.source = ?
               AND d.document_hash = ?
             LIMIT 1
            """,
            (source, document_hash),
        ).fetchone()
        return row is not None

    def _mark_processed_document_hash(
        self,
        *,
        raw_document_id: str,
        processed_at: datetime,
    ) -> None:
        row = self._conn.execute(
            """
            SELECT source, document_hash
            FROM raw_documents
            WHERE id = ?
            LIMIT 1
            """,
            (raw_document_id,),
        ).fetchone()
        if row is None:
            return

        source = str(row["source"] or "").strip()
        document_hash = str(row["document_hash"] or "").strip()
        if not source or not document_hash:
            return

        processed_at_iso = self._coerce_datetime(processed_at).isoformat()
        self._conn.execute(
            """
            INSERT INTO processed_document_hashes(
                source, document_hash, raw_document_id, first_processed_at, last_processed_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source, document_hash) DO UPDATE SET
                raw_document_id = excluded.raw_document_id,
                last_processed_at = excluded.last_processed_at
            """,
            (
                source,
                document_hash,
                raw_document_id,
                processed_at_iso,
                processed_at_iso,
            ),
        )

    def mark_document_hash_processed_explicit(
        self,
        *,
        source: str,
        document_hash: str,
        raw_document_id: str,
        processed_at: datetime,
    ) -> None:
        processed_at_iso = self._coerce_datetime(processed_at).isoformat()
        self._conn.execute(
            """
            INSERT INTO processed_document_hashes(
                source, document_hash, raw_document_id, first_processed_at, last_processed_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source, document_hash) DO UPDATE SET
                raw_document_id = excluded.raw_document_id,
                last_processed_at = excluded.last_processed_at
            """,
            (
                source,
                document_hash,
                raw_document_id,
                processed_at_iso,
                processed_at_iso,
            ),
        )
        self._conn.commit()

    def event_exists(self, event_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM events WHERE id = ? LIMIT 1",
            (event_id,),
        ).fetchone()
        return row is not None

    def valuation_diff_exists_for_event(self, event_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM valuation_diffs WHERE event_id = ? LIMIT 1",
            (event_id,),
        ).fetchone()
        return row is not None

    def get_structured_signal_by_event_id(self, event_id: str) -> Optional[StructuredSignal]:
        row = self._conn.execute(
            """
            SELECT payload_json
              FROM structured_signals
             WHERE event_id = ?
             ORDER BY created_at DESC
             LIMIT 1
            """,
            (event_id,),
        ).fetchone()
        if row is None:
            return None
        return StructuredSignal.model_validate_json(row["payload_json"])

    def get_design_assessment(self, signal_id: str):
        """
        Return a TrialDesignAssessment for *signal_id*, or None when unavailable.

        Assessments are computed from the stored structured signal on read.
        """
        row = self._conn.execute(
            """
            SELECT payload_json
            FROM structured_signals
            WHERE id = ?
            LIMIT 1
            """,
            (signal_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            signal = StructuredSignal.model_validate_json(row["payload_json"])
            from bve.intelligence.trial_design_assessment import assess_trial_design

            return assess_trial_design(signal)
        except Exception:
            return None

    def add_event(
        self,
        event: Event,
        source_trace: SourceTrace,
        *,
        signal_id: Optional[str] = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO events(
                id, event_key, signal_id, company_id, asset_id, indication_id, event_type,
                observed_at, ingested_at, source_url, source_type, headline,
                confidence, payload_json, source_trace_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.id,
                signal_id,
                event.company_id,
                event.asset_id,
                event.indication_id,
                event.event_type.value,
                event.observed_at.isoformat(),
                event.ingested_at.isoformat(),
                event.source_url,
                event.source_type,
                event.headline,
                float(event.confidence),
                event.model_dump_json(),
                source_trace.model_dump_json(),
            ),
        )
        self._conn.commit()

    @staticmethod
    def _normalize_stored_valuation_diff(diff: object) -> StoredValuationDiff:
        if isinstance(diff, StoredValuationDiff):
            return diff

        if isinstance(diff, dict):
            payload: dict[str, Any] = dict(diff)
        elif hasattr(diff, "model_dump"):
            payload = diff.model_dump(mode="json")
        else:
            raise TypeError("Unsupported valuation diff type")

        run_id = str(payload.get("run_id") or payload.get("id") or uuid.uuid4())
        event_id = str(payload.get("event_id") or "")
        asset_id = str(payload.get("asset_id") or "")
        if not event_id or not asset_id:
            raise ValueError("valuation diff must include event_id and asset_id")

        created_at = (
            payload.get("created_at") or payload.get("generated_at") or datetime.now(timezone.utc)
        )

        valuation_before = payload.get("valuation_before") or {}
        valuation_after = payload.get("valuation_after") or {}

        delta_npv_raw = payload.get("delta_npv")
        if delta_npv_raw is None:
            before_npv = float(valuation_before.get("rnpv_millions", 0.0) or 0.0)
            after_npv = float(valuation_after.get("rnpv_millions", 0.0) or 0.0)
            delta_npv = round(after_npv - before_npv, 2)
        else:
            delta_npv = float(delta_npv_raw)

        valuation_delta = payload.get("valuation_delta") or {}
        if not valuation_delta:
            for key in (
                "delta_npv",
                "delta_nav_per_share",
                "delta_mc_mean_millions",
                "delta_bull_rnpv_millions",
                "delta_base_rnpv_millions",
                "delta_bear_rnpv_millions",
            ):
                value = payload.get(key)
                if value is not None:
                    valuation_delta[key] = float(value)

        market_cap_raw = payload.get("market_cap_snapshot_millions")
        return StoredValuationDiff(
            run_id=run_id,
            event_id=event_id,
            asset_id=asset_id,
            valuation_before=valuation_before,
            valuation_after=valuation_after,
            delta_npv=delta_npv,
            created_at=KnowledgeStore._coerce_datetime(created_at),
            valuation_delta=valuation_delta,
            assumptions_changed=list(payload.get("assumptions_changed") or []),
            applied_overrides=dict(payload.get("applied_overrides") or {}),
            market_cap_snapshot_millions=float(market_cap_raw)
            if market_cap_raw is not None
            else None,
        )

    def add_valuation_diff(
        self,
        diff: object,
        *,
        company_id: Optional[str],
        source_trace: SourceTrace,
        assumptions_snapshot: Optional[dict] = None,
        valuation_snapshot: Optional[dict] = None,
    ) -> StoredValuationDiff:
        stored = self._normalize_stored_valuation_diff(diff)

        snapshot = valuation_snapshot or stored.valuation_after
        self._conn.execute(
            """
            INSERT OR REPLACE INTO valuation_diffs(
                run_id, company_id, asset_id, event_id, created_at, delta_npv,
                payload_json, assumptions_snapshot_json, valuation_snapshot_json, source_trace_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                stored.run_id,
                company_id,
                stored.asset_id,
                stored.event_id,
                stored.created_at.isoformat(),
                float(stored.delta_npv),
                stored.model_dump_json(),
                self._json_dump(assumptions_snapshot or {}),
                self._json_dump(snapshot),
                source_trace.model_dump_json(),
            ),
        )
        self._conn.commit()
        return stored

    # ------------------------------------------------------------------
    # Score updates (live scanner score-update contract — commit 1)
    # ------------------------------------------------------------------
    def add_score_update(
        self,
        record: ScoreUpdateRecord,
        *,
        source_trace: SourceTrace,
    ) -> ScoreUpdateRecord:
        """Persist one auditable scanner score-movement record."""
        self._conn.execute(
            """
            INSERT OR REPLACE INTO score_updates(
                id, run_id, asset_id, as_of, prior_score, new_score, delta, decision,
                components_json, contributing_signal_ids_json,
                contributing_event_ids_json, source_trace_json, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                record.run_id,
                record.asset_id,
                record.as_of.isoformat(),
                record.prior_score,
                float(record.new_score),
                float(record.delta),
                record.decision,
                self._json_dump(record.components),
                self._json_dump(record.contributing_signal_ids),
                self._json_dump(record.contributing_event_ids),
                source_trace.model_dump_json(),
                record.created_at.isoformat(),
            ),
        )
        self._conn.commit()
        return record

    def get_score_updates(
        self,
        *,
        asset_id: Optional[str] = None,
        run_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[ScoreUpdateRecord]:
        """Query persisted score-update records, newest first."""
        import json as _json

        clauses: list[str] = []
        params: list[object] = []
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        if run_id is not None:
            clauses.append("run_id = ?")
            params.append(run_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM score_updates {where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()

        out: list[ScoreUpdateRecord] = []
        for row in rows:
            out.append(ScoreUpdateRecord(
                id=row["id"],
                run_id=row["run_id"],
                asset_id=row["asset_id"],
                as_of=date.fromisoformat(row["as_of"]),
                prior_score=row["prior_score"],
                new_score=row["new_score"],
                delta=row["delta"],
                decision=row["decision"] if "decision" in row.keys() else "auto_apply",
                components=_json.loads(row["components_json"] or "{}"),
                contributing_signal_ids=_json.loads(row["contributing_signal_ids_json"] or "[]"),
                contributing_event_ids=_json.loads(row["contributing_event_ids_json"] or "[]"),
                created_at=datetime.fromisoformat(row["created_at"]),
            ))
        return out

    # ------------------------------------------------------------------
    # Runtime state + opportunity alerts (Wave 7)
    # ------------------------------------------------------------------

    def mark_run_state_started(
        self,
        *,
        run_id: str,
        stage: str,
        asset_id: str,
        started_at: datetime,
        checkpoint_json: Optional[dict[str, Any]] = None,
    ) -> RunStateRecord:
        record = RunStateRecord(
            run_id=run_id,
            stage=stage,
            asset_id=asset_id,
            status="running",
            started_at=self._coerce_datetime(started_at),
            finished_at=None,
            checkpoint_json=checkpoint_json or {},
            error_json={},
        )
        self._conn.execute(
            """
            INSERT OR REPLACE INTO run_state(
                run_id, stage, asset_id, status, started_at, finished_at,
                checkpoint_json, error_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.run_id,
                record.stage,
                record.asset_id,
                record.status,
                record.started_at.isoformat(),
                None,
                self._json_dump(record.checkpoint_json),
                self._json_dump(record.error_json),
            ),
        )
        self._conn.commit()
        return record

    def mark_run_state_finished(
        self,
        *,
        run_id: str,
        stage: str,
        asset_id: str,
        status: Literal["success", "failure", "skipped"],
        started_at: datetime,
        finished_at: datetime,
        checkpoint_json: Optional[dict[str, Any]] = None,
        error_json: Optional[dict[str, Any]] = None,
    ) -> RunStateRecord:
        record = RunStateRecord(
            run_id=run_id,
            stage=stage,
            asset_id=asset_id,
            status=status,
            started_at=self._coerce_datetime(started_at),
            finished_at=self._coerce_datetime(finished_at),
            checkpoint_json=checkpoint_json or {},
            error_json=error_json or {},
        )
        self._conn.execute(
            """
            INSERT OR REPLACE INTO run_state(
                run_id, stage, asset_id, status, started_at, finished_at,
                checkpoint_json, error_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.run_id,
                record.stage,
                record.asset_id,
                record.status,
                record.started_at.isoformat(),
                record.finished_at.isoformat() if record.finished_at is not None else None,
                self._json_dump(record.checkpoint_json),
                self._json_dump(record.error_json),
            ),
        )
        self._conn.commit()
        return record

    def get_run_states(
        self,
        *,
        run_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        stage: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 1000,
    ) -> list[RunStateRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if run_id is not None:
            clauses.append("run_id = ?")
            params.append(run_id)
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        if stage is not None:
            clauses.append("stage = ?")
            params.append(stage)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)

        sql = (
            "SELECT run_id, stage, asset_id, status, started_at, finished_at, "
            "checkpoint_json, error_json FROM run_state"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        out: list[RunStateRecord] = []
        for row in rows:
            out.append(
                RunStateRecord(
                    run_id=row["run_id"],
                    stage=row["stage"],
                    asset_id=row["asset_id"],
                    status=row["status"],
                    started_at=self._coerce_datetime(row["started_at"]),
                    finished_at=self._coerce_datetime(row["finished_at"])
                    if row["finished_at"] is not None
                    else None,
                    checkpoint_json=json.loads(row["checkpoint_json"] or "{}"),
                    error_json=json.loads(row["error_json"] or "{}"),
                )
            )
        return out

    def get_stage_checkpoint(
        self,
        *,
        run_id: str,
        stage: str,
        asset_id: str,
    ) -> dict[str, Any]:
        row = self._conn.execute(
            """
            SELECT checkpoint_json
            FROM run_state
            WHERE run_id = ? AND stage = ? AND asset_id = ?
            LIMIT 1
            """,
            (run_id, stage, asset_id),
        ).fetchone()
        if row is None:
            return {}
        return json.loads(row["checkpoint_json"] or "{}")

    def log_data_quality(
        self,
        score: "DataQualityScore",
        *,
        run_id: Optional[str] = None,
    ) -> None:
        """Persist one row per check for auditability and root-cause diagnosis."""
        checked_at = self._coerce_datetime(score.generated_at).isoformat()
        checks = score.checks or []
        if not checks:
            checks = []
        for check in checks:
            self._conn.execute(
                """
                INSERT INTO data_quality_log(
                    run_id, asset_id, check_name, status, severity, reason,
                    value, threshold, overall_score, gated, details_json, checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    score.asset_id,
                    check.check_type,
                    "pass" if check.passed else "fail",
                    check.severity,
                    check.reason,
                    None if check.value is None else str(check.value),
                    check.threshold,
                    float(score.overall_score),
                    1 if score.gated else 0,
                    self._json_dump(
                        {
                            "details": check.details,
                            "source": score.source,
                            "failing_checks": score.failing_checks,
                        }
                    ),
                    checked_at,
                ),
            )
        if not checks:
            self._conn.execute(
                """
                INSERT INTO data_quality_log(
                    run_id, asset_id, check_name, status, severity, reason,
                    value, threshold, overall_score, gated, details_json, checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    score.asset_id,
                    "overall",
                    "pass" if not score.gated else "fail",
                    "info" if not score.gated else "warning",
                    "no_checks",
                    None,
                    "",
                    float(score.overall_score),
                    1 if score.gated else 0,
                    self._json_dump(
                        {"source": score.source, "failing_checks": score.failing_checks}
                    ),
                    checked_at,
                ),
            )
        self._conn.commit()

    def get_latest_data_quality(self, asset_id: str) -> Optional["DataQualityScore"]:
        """Return latest data-quality score for asset, or None."""
        row = self._conn.execute(
            """
            SELECT run_id, asset_id, overall_score, gated, checked_at
            FROM data_quality_log
            WHERE asset_id = ?
            ORDER BY checked_at DESC, id DESC
            LIMIT 1
            """,
            (asset_id,),
        ).fetchone()
        if row is None:
            return None

        from bve.ops.data_quality import DataQualityCheck, DataQualityScore

        run_id = row["run_id"]
        checked_at = self._coerce_datetime(row["checked_at"])
        if run_id:
            check_rows = self._conn.execute(
                """
                SELECT check_name, status, severity, reason, value, threshold, details_json
                FROM data_quality_log
                WHERE asset_id = ? AND run_id = ?
                ORDER BY id ASC
                """,
                (asset_id, run_id),
            ).fetchall()
        else:
            check_rows = self._conn.execute(
                """
                SELECT check_name, status, severity, reason, value, threshold, details_json
                FROM data_quality_log
                WHERE asset_id = ? AND checked_at = ?
                ORDER BY id ASC
                """,
                (asset_id, checked_at.isoformat()),
            ).fetchall()

        checks: list[DataQualityCheck] = []
        source = "knowledge_store"
        failing_checks: list[str] = []
        for check_row in check_rows:
            details_payload = json.loads(check_row["details_json"] or "{}")
            source = str(details_payload.get("source") or source)
            failing_checks = list(details_payload.get("failing_checks") or failing_checks)
            status = str(check_row["status"] or "pass").lower()
            value_raw = check_row["value"]
            value: float | int | str | None
            if value_raw is None:
                value = None
            else:
                text = str(value_raw)
                try:
                    value = int(text)
                except ValueError:
                    try:
                        value = float(text)
                    except ValueError:
                        value = text
            checks.append(
                DataQualityCheck(
                    check_type=str(check_row["check_name"]),
                    asset_id=asset_id,
                    value=value,
                    threshold=str(check_row["threshold"] or ""),
                    passed=status == "pass",
                    severity=str(check_row["severity"] or "info"),
                    reason=str(check_row["reason"] or "ok"),
                    details=str(details_payload.get("details") or ""),
                )
            )
        return DataQualityScore(
            source=source,
            asset_id=row["asset_id"],
            overall_score=float(row["overall_score"]),
            checks=checks,
            failing_checks=failing_checks or [c.check_type for c in checks if not c.passed],
            gated=bool(row["gated"]),
            generated_at=checked_at,
        )

    def list_latest_data_quality(self, *, limit: int = 1000) -> list["DataQualityScore"]:
        """Return latest data-quality score per asset, newest first."""
        rows = self._conn.execute(
            """
            SELECT asset_id
            FROM data_quality_log
            WHERE asset_id IS NOT NULL AND asset_id <> ''
            GROUP BY asset_id
            ORDER BY MAX(checked_at) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        out: list["DataQualityScore"] = []
        for row in rows:
            score = self.get_latest_data_quality(str(row["asset_id"]))
            if score is not None:
                out.append(score)
        return out

    def log_kg_integrity(self, report: Any) -> None:
        """Persist one KG integrity report row."""
        checked_at = self._coerce_datetime(
            getattr(report, "checked_at", None),
            default=datetime.now(timezone.utc),
        )
        self._conn.execute(
            """
            INSERT INTO kg_integrity_log(report_json, passed, checked_at)
            VALUES(?, ?, ?)
            """,
            (
                report.model_dump_json() if hasattr(report, "model_dump_json") else self._json_dump(report),
                1 if bool(getattr(report, "passed", False)) else 0,
                checked_at.isoformat(),
            ),
        )
        self._conn.commit()

    def get_latest_kg_integrity(self) -> Optional[dict[str, Any]]:
        """Return the most recent KG integrity log row as plain dict, or None."""
        row = self._conn.execute(
            """
            SELECT id, report_json, passed, checked_at
            FROM kg_integrity_log
            ORDER BY checked_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        return {
            "id": int(row["id"]),
            "report_json": json.loads(row["report_json"] or "{}"),
            "passed": bool(row["passed"]),
            "checked_at": self._coerce_datetime(row["checked_at"]),
        }

    def add_opportunity_alert(
        self,
        record: OpportunityAlertRecord,
    ) -> bool:
        cur = self._conn.execute(
            """
            INSERT OR IGNORE INTO opportunity_alerts(
                asset_id, event_type, window, run_id, created_at, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record.asset_id,
                record.event_type,
                record.window,
                record.run_id,
                self._coerce_datetime(record.created_at).isoformat(),
                self._json_dump(record.payload_json),
            ),
        )
        self._conn.commit()
        return cur.rowcount > 0

    def get_opportunity_alerts(
        self,
        *,
        asset_id: Optional[str] = None,
        event_type: Optional[str] = None,
        window: Optional[str] = None,
        limit: int = 100,
    ) -> list[OpportunityAlertRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        if event_type is not None:
            clauses.append("event_type = ?")
            params.append(event_type)
        if window is not None:
            clauses.append("window = ?")
            params.append(window)

        sql = (
            "SELECT asset_id, event_type, window, run_id, created_at, payload_json "
            "FROM opportunity_alerts"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [
            OpportunityAlertRecord(
                asset_id=row["asset_id"],
                event_type=row["event_type"],
                window=row["window"],
                run_id=row["run_id"],
                created_at=self._coerce_datetime(row["created_at"]),
                payload_json=json.loads(row["payload_json"] or "{}"),
            )
            for row in rows
        ]

    def write_backtest_snapshot(self, snapshot: BacktestSnapshot) -> None:
        """Persist one snapshot row for portfolio backtesting."""
        self._conn.execute(
            """
            INSERT OR REPLACE INTO backtest_snapshots(
                snapshot_id, alert_id, asset_id, signal_date, signal_id, signal_timestamp,
                composite_score, extraction_confidence, delta_npv_millions,
                intrinsic_value_millions, mispricing_score, catalyst_date, catalyst_type,
                catalyst_score, rank_at_signal, model_version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.snapshot_id,
                snapshot.alert_id,
                snapshot.asset_id,
                snapshot.signal_date.isoformat(),
                snapshot.signal_id,
                self._coerce_datetime(snapshot.signal_timestamp).isoformat()
                if snapshot.signal_timestamp is not None
                else None,
                snapshot.composite_score,
                snapshot.extraction_confidence,
                snapshot.delta_npv_millions,
                snapshot.intrinsic_value_millions,
                snapshot.mispricing_score,
                snapshot.catalyst_date.isoformat() if snapshot.catalyst_date is not None else None,
                snapshot.catalyst_type,
                snapshot.catalyst_score,
                snapshot.rank_at_signal,
                snapshot.model_version,
                self._coerce_datetime(snapshot.created_at).isoformat(),
            ),
        )
        self._conn.commit()

    def get_backtest_snapshots(
        self,
        *,
        asset_id: Optional[str] = None,
        since: Optional[date | datetime] = None,
    ) -> list[BacktestSnapshot]:
        """Return snapshot rows for backtesting, newest first."""
        clauses: list[str] = []
        params: list[Any] = []
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        if since is not None:
            since_date = since.date() if isinstance(since, datetime) else since
            clauses.append("signal_date >= ?")
            params.append(since_date.isoformat())

        sql = "SELECT * FROM backtest_snapshots"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY signal_date DESC, created_at DESC"

        rows = self._conn.execute(sql, params).fetchall()
        out: list[BacktestSnapshot] = []
        for row in rows:
            out.append(
                BacktestSnapshot(
                    snapshot_id=row["snapshot_id"],
                    alert_id=row["alert_id"],
                    asset_id=row["asset_id"],
                    signal_date=date.fromisoformat(row["signal_date"]),
                    signal_id=row["signal_id"],
                    signal_timestamp=(
                        self._coerce_datetime(row["signal_timestamp"])
                        if row["signal_timestamp"] is not None
                        else None
                    ),
                    composite_score=row["composite_score"],
                    extraction_confidence=row["extraction_confidence"],
                    delta_npv_millions=row["delta_npv_millions"],
                    intrinsic_value_millions=row["intrinsic_value_millions"],
                    mispricing_score=row["mispricing_score"],
                    catalyst_date=(
                        date.fromisoformat(row["catalyst_date"])
                        if row["catalyst_date"] is not None
                        else None
                    ),
                    catalyst_type=row["catalyst_type"],
                    catalyst_score=row["catalyst_score"],
                    rank_at_signal=row["rank_at_signal"],
                    model_version=row["model_version"],
                    created_at=self._coerce_datetime(row["created_at"]),
                )
            )
        return out

    # ------------------------------------------------------------------
    # Asset registry (Sprint 1)
    # ------------------------------------------------------------------

    def upsert_asset_registry_entry(self, entry: AssetRegistryEntry) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO asset_registry(
                asset_id, ticker, company_id, drug_name, indication,
                therapeutic_area, modality, stage, nct_id, tam_millions,
                created_at, source, last_competitor_discovery_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.asset_id,
                entry.ticker,
                entry.company_id,
                entry.drug_name,
                entry.indication,
                entry.therapeutic_area,
                entry.modality,
                entry.stage,
                entry.nct_id,
                entry.tam_millions,
                self._coerce_datetime(entry.created_at).isoformat(),
                entry.source,
                self._coerce_datetime(entry.last_competitor_discovery_at).isoformat()
                if entry.last_competitor_discovery_at is not None
                else None,
            ),
        )
        self._conn.commit()

    @classmethod
    def _asset_registry_from_row(cls, row: sqlite3.Row) -> AssetRegistryEntry:
        return AssetRegistryEntry(
            asset_id=row["asset_id"],
            ticker=row["ticker"],
            company_id=row["company_id"],
            drug_name=row["drug_name"],
            indication=row["indication"],
            therapeutic_area=row["therapeutic_area"],
            modality=row["modality"],
            stage=row["stage"],
            nct_id=row["nct_id"],
            tam_millions=row["tam_millions"],
            created_at=cls._coerce_datetime(row["created_at"]),
            source=row["source"],
            last_competitor_discovery_at=cls._coerce_datetime(row["last_competitor_discovery_at"])
            if row["last_competitor_discovery_at"] is not None
            else None,
        )

    def get_asset_registry_entry(self, asset_id: str) -> Optional[AssetRegistryEntry]:
        row = self._conn.execute(
            "SELECT * FROM asset_registry WHERE asset_id = ? LIMIT 1",
            (asset_id,),
        ).fetchone()
        if row is None:
            return None
        return self._asset_registry_from_row(row)

    def list_asset_registry(
        self,
        ta: Optional[str] = None,
        stage: Optional[str] = None,
    ) -> list[AssetRegistryEntry]:
        clauses: list[str] = []
        params: list[Any] = []
        if ta is not None:
            clauses.append("therapeutic_area = ?")
            params.append(ta)
        if stage is not None:
            clauses.append("stage = ?")
            params.append(stage)

        sql = "SELECT * FROM asset_registry"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY asset_id"

        rows = self._conn.execute(sql, params).fetchall()
        return [self._asset_registry_from_row(row) for row in rows]

    def count_competitor_programs(self, asset_id: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM competitor_programs WHERE asset_id = ?",
            (asset_id,),
        ).fetchone()
        return int(row["n"]) if row is not None else 0

    def update_competitor_discovery_timestamp(self, asset_id: str, ts: datetime) -> None:
        self._conn.execute(
            """
            UPDATE asset_registry
               SET last_competitor_discovery_at = ?
             WHERE asset_id = ?
            """,
            (self._coerce_datetime(ts).isoformat(), asset_id),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Market price methods (Wave 1A)
    # ------------------------------------------------------------------

    def upsert_market_price(self, record: "MarketPriceRecord") -> None:
        """Insert or replace one market price row (idempotent on ticker+date)."""
        self._conn.execute(
            """
            INSERT OR REPLACE INTO market_prices(
                ticker, price_date, close_usd, adj_close_usd, volume,
                market_cap_millions, is_adjusted, source, ingested_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.ticker,
                record.price_date.isoformat(),
                record.close_usd,
                record.adj_close_usd,
                record.volume,
                record.market_cap_millions,
                1 if record.is_adjusted else 0,
                record.source,
                record.ingested_at.isoformat(),
            ),
        )
        self._conn.commit()

    def upsert_market_prices(self, records: "list[MarketPriceRecord]") -> int:
        """Bulk upsert; returns number of rows written."""
        if not records:
            return 0
        self._conn.executemany(
            """
            INSERT OR REPLACE INTO market_prices(
                ticker, price_date, close_usd, adj_close_usd, volume,
                market_cap_millions, is_adjusted, source, ingested_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    r.ticker,
                    r.price_date.isoformat(),
                    r.close_usd,
                    r.adj_close_usd,
                    r.volume,
                    r.market_cap_millions,
                    1 if r.is_adjusted else 0,
                    r.source,
                    r.ingested_at.isoformat(),
                )
                for r in records
            ],
        )
        self._conn.commit()
        return len(records)

    def get_latest_price(self, ticker: str) -> Optional["MarketPriceRecord"]:
        """Return the most recent price row for *ticker*, or None."""
        row = self._conn.execute(
            """
            SELECT ticker, price_date, close_usd, adj_close_usd, volume,
                   market_cap_millions, is_adjusted, source, ingested_at
            FROM market_prices WHERE ticker = ?
            ORDER BY price_date DESC LIMIT 1
            """,
            (ticker,),
        ).fetchone()
        if row is None:
            return None
        from bve.connectors.market_prices import MarketPriceRecord
        from datetime import date as _date

        return MarketPriceRecord(
            ticker=row["ticker"],
            price_date=_date.fromisoformat(row["price_date"]),
            close_usd=row["close_usd"],
            adj_close_usd=row["adj_close_usd"],
            volume=row["volume"] or 0,
            market_cap_millions=row["market_cap_millions"],
            is_adjusted=bool(row["is_adjusted"]),
            source=row["source"],
            ingested_at=self._coerce_datetime(row["ingested_at"]),
        )

    def get_price_on_or_before(self, ticker: str, as_of: "date") -> Optional["MarketPriceRecord"]:
        """Return the latest price row for *ticker* on or before *as_of*."""
        row = self._conn.execute(
            """
            SELECT ticker, price_date, close_usd, adj_close_usd, volume,
                   market_cap_millions, is_adjusted, source, ingested_at
            FROM market_prices WHERE ticker = ? AND price_date <= ?
            ORDER BY price_date DESC LIMIT 1
            """,
            (ticker, as_of.isoformat()),
        ).fetchone()
        if row is None:
            return None
        from bve.connectors.market_prices import MarketPriceRecord
        from datetime import date as _date

        return MarketPriceRecord(
            ticker=row["ticker"],
            price_date=_date.fromisoformat(row["price_date"]),
            close_usd=row["close_usd"],
            adj_close_usd=row["adj_close_usd"],
            volume=row["volume"] or 0,
            market_cap_millions=row["market_cap_millions"],
            is_adjusted=bool(row["is_adjusted"]),
            source=row["source"],
            ingested_at=self._coerce_datetime(row["ingested_at"]),
        )

    def get_20day_avg_volume(self, ticker: str, as_of: "date") -> Optional[float]:
        """Return 20-trading-day average volume on or before *as_of*, or None."""
        row = self._conn.execute(
            """
            SELECT AVG(volume) as avg_vol FROM (
                SELECT volume FROM market_prices
                WHERE ticker = ? AND price_date <= ?
                ORDER BY price_date DESC LIMIT 20
            )
            """,
            (ticker, as_of.isoformat()),
        ).fetchone()
        if row is None or row["avg_vol"] is None:
            return None
        return float(row["avg_vol"])

    # ------------------------------------------------------------------
    # Market expectation methods (Wave 1D)
    # ------------------------------------------------------------------

    def upsert_market_expectation(self, exp: "MarketExpectation") -> None:
        """Insert or replace one market expectation row."""
        self._conn.execute(
            """
            INSERT OR REPLACE INTO market_expectations(
                expectation_id, asset_id, ticker, expectation_date,
                implied_pos, model_pos, pos_gap, cash_estimate_millions,
                methodology, computed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                exp.expectation_id,
                exp.asset_id,
                exp.ticker,
                exp.expectation_date.isoformat(),
                exp.implied_pos,
                exp.model_pos,
                exp.pos_gap,
                exp.cash_estimate_millions,
                exp.methodology,
                exp.computed_at.isoformat(),
            ),
        )
        self._conn.commit()

    def get_latest_expectation(self, asset_id: str) -> Optional["MarketExpectation"]:
        """Return the most recent market_expectation row for *asset_id*, or None."""
        row = self._conn.execute(
            """
            SELECT expectation_id, asset_id, ticker, expectation_date,
                   implied_pos, model_pos, pos_gap, cash_estimate_millions,
                   methodology, computed_at
            FROM market_expectations WHERE asset_id = ?
            ORDER BY expectation_date DESC, computed_at DESC LIMIT 1
            """,
            (asset_id,),
        ).fetchone()
        if row is None:
            return None
        from bve.intelligence.market_expectations import MarketExpectation
        from datetime import date as _date

        return MarketExpectation(
            expectation_id=row["expectation_id"],
            asset_id=row["asset_id"],
            ticker=row["ticker"],
            expectation_date=_date.fromisoformat(row["expectation_date"]),
            implied_pos=row["implied_pos"],
            implied_success_probability=row["implied_pos"],
            model_pos=row["model_pos"],
            pos_gap=row["pos_gap"],
            cash_estimate_millions=row["cash_estimate_millions"],
            methodology=row["methodology"],
            computed_at=self._coerce_datetime(row["computed_at"]),
        )

    def upsert_acquisition_discount_snapshot(
        self,
        snapshot: "AcquisitionDiscountSnapshot",
    ) -> None:
        """Insert or replace one acquisition discount snapshot row."""
        self._conn.execute(
            """
            INSERT OR REPLACE INTO acquisition_discount_snapshots(
                snapshot_id, asset_id, ticker, snapshot_date, formula_version,
                model_rnpv_millions, model_pos, market_cap_millions, market_cap_as_of,
                market_cap_source, enterprise_value_millions, net_cash_millions,
                ev_methodology, acquisition_discount, passes_threshold,
                exclusion_reason, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.snapshot_id,
                snapshot.asset_id,
                snapshot.ticker,
                snapshot.snapshot_date.isoformat(),
                snapshot.formula_version,
                snapshot.model_rnpv_millions,
                snapshot.model_pos,
                snapshot.market_cap_millions,
                snapshot.market_cap_as_of.isoformat() if snapshot.market_cap_as_of else None,
                snapshot.market_cap_source,
                snapshot.enterprise_value_millions,
                snapshot.net_cash_millions,
                snapshot.ev_methodology,
                snapshot.acquisition_discount,
                1 if snapshot.passes_threshold else 0,
                snapshot.exclusion_reason,
                snapshot.created_at.isoformat(),
            ),
        )
        self._conn.commit()

    def get_latest_acquisition_discount_snapshot(
        self,
        asset_id: str,
    ) -> Optional["AcquisitionDiscountSnapshot"]:
        """Return the most recent acquisition discount snapshot for *asset_id*."""
        row = self._conn.execute(
            """
            SELECT snapshot_id, asset_id, ticker, snapshot_date, formula_version,
                   model_rnpv_millions, model_pos, market_cap_millions, market_cap_as_of,
                   market_cap_source, enterprise_value_millions, net_cash_millions,
                   ev_methodology, acquisition_discount, passes_threshold,
                   exclusion_reason, created_at
            FROM acquisition_discount_snapshots
            WHERE asset_id = ?
            ORDER BY snapshot_date DESC, created_at DESC
            LIMIT 1
            """,
            (asset_id,),
        ).fetchone()
        if row is None:
            return None
        from bve.intelligence.acquisition_screen import AcquisitionDiscountSnapshot

        return AcquisitionDiscountSnapshot(
            snapshot_id=row["snapshot_id"],
            asset_id=row["asset_id"],
            ticker=row["ticker"],
            snapshot_date=date.fromisoformat(row["snapshot_date"]),
            formula_version=row["formula_version"],
            model_rnpv_millions=row["model_rnpv_millions"],
            model_pos=row["model_pos"],
            market_cap_millions=row["market_cap_millions"],
            market_cap_as_of=(
                date.fromisoformat(row["market_cap_as_of"])
                if row["market_cap_as_of"]
                else None
            ),
            market_cap_source=row["market_cap_source"],
            enterprise_value_millions=row["enterprise_value_millions"],
            net_cash_millions=row["net_cash_millions"],
            ev_methodology=row["ev_methodology"],
            acquisition_discount=row["acquisition_discount"],
            passes_threshold=bool(row["passes_threshold"]),
            exclusion_reason=row["exclusion_reason"],
            created_at=self._coerce_datetime(row["created_at"]),
        )

    def list_acquisition_discount_snapshots(
        self,
        *,
        asset_id: Optional[str] = None,
        snapshot_date: Optional[date] = None,
        passes_threshold: Optional[bool] = None,
        limit: int = 100,
    ) -> list["AcquisitionDiscountSnapshot"]:
        """List acquisition discount snapshots with optional filters."""
        clauses = []
        params: list[object] = []
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        if snapshot_date is not None:
            clauses.append("snapshot_date = ?")
            params.append(snapshot_date.isoformat())
        if passes_threshold is not None:
            clauses.append("passes_threshold = ?")
            params.append(1 if passes_threshold else 0)

        sql = (
            "SELECT snapshot_id, asset_id, ticker, snapshot_date, formula_version, "
            "model_rnpv_millions, model_pos, market_cap_millions, market_cap_as_of, "
            "market_cap_source, enterprise_value_millions, net_cash_millions, "
            "ev_methodology, acquisition_discount, passes_threshold, "
            "exclusion_reason, created_at "
            "FROM acquisition_discount_snapshots"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY snapshot_date DESC, acquisition_discount DESC, created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        from bve.intelligence.acquisition_screen import AcquisitionDiscountSnapshot

        snapshots: list[AcquisitionDiscountSnapshot] = []
        for row in rows:
            snapshots.append(
                AcquisitionDiscountSnapshot(
                    snapshot_id=row["snapshot_id"],
                    asset_id=row["asset_id"],
                    ticker=row["ticker"],
                    snapshot_date=date.fromisoformat(row["snapshot_date"]),
                    formula_version=row["formula_version"],
                    model_rnpv_millions=row["model_rnpv_millions"],
                    model_pos=row["model_pos"],
                    market_cap_millions=row["market_cap_millions"],
                    market_cap_as_of=(
                        date.fromisoformat(row["market_cap_as_of"])
                        if row["market_cap_as_of"]
                        else None
                    ),
                    market_cap_source=row["market_cap_source"],
                    enterprise_value_millions=row["enterprise_value_millions"],
                    net_cash_millions=row["net_cash_millions"],
                    ev_methodology=row["ev_methodology"],
                    acquisition_discount=row["acquisition_discount"],
                    passes_threshold=bool(row["passes_threshold"]),
                    exclusion_reason=row["exclusion_reason"],
                    created_at=self._coerce_datetime(row["created_at"]),
                )
            )
        return snapshots

    # ------------------------------------------------------------------
    # Screen snapshots  (Sprint 10, Task 10.4)
    # ------------------------------------------------------------------

    def write_screen_snapshots(
        self,
        rows: "list",  # ScreenRow from bve.analysis.implied_pos_batch
        snapshot_date: Optional[date] = None,
    ) -> int:
        """
        Upsert a list of ScreenRow objects into screen_snapshots.

        Parameters
        ----------
        rows          : list of ScreenRow from implied_pos_batch.run_screen()
        snapshot_date : override date (default: each row's data_date)

        Returns the number of rows written.
        """
        from uuid import uuid4

        written = 0
        for row in rows:
            snap_date = snapshot_date or row.data_date
            self._conn.execute(
                """
                INSERT OR REPLACE INTO screen_snapshots(
                    snapshot_id, ticker, asset_id, snapshot_date, program_label, stage, ta,
                    model_pos, implied_pos, spread_pp, rnpv_millions, ev_millions,
                    acquisition_discount_pct, next_catalyst, catalyst_date,
                    days_to_catalyst, single_asset, approximation_warning,
                    thesis_strength, market_exceeds_model, config_quality, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    row.ticker,
                    getattr(row, "asset_id", "") or "",
                    snap_date.isoformat(),
                    row.program_label,
                    row.stage,
                    row.ta,
                    row.model_pos,
                    row.implied_pos,
                    row.spread_pp,
                    row.rnpv_millions,
                    row.ev_millions,
                    row.acquisition_discount_pct,
                    row.next_catalyst,
                    row.catalyst_date.isoformat() if row.catalyst_date else None,
                    row.days_to_catalyst,
                    1 if row.single_asset else 0,
                    row.approximation_warning,
                    getattr(row, "thesis_strength", None),
                    1 if getattr(row, "market_exceeds_model", False) else 0,
                    getattr(row, "config_quality", None),
                    datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
                        "+00:00",
                        "Z",
                    ),
                ),
            )
            written += 1
        self._conn.commit()
        return written

    def get_screen_snapshots(
        self,
        snapshot_date: Optional[date] = None,
        *,
        ticker: Optional[str] = None,
        limit: int = 200,
    ) -> "list[dict]":
        """
        Return screen snapshot rows as plain dicts (keys = column names).

        Parameters
        ----------
        snapshot_date : if given, return rows for that date only;
                        otherwise return the most recent date's rows
        ticker        : if given, filter to a single ticker
        limit         : max rows returned
        """
        clauses: list[str] = []
        params: list[object] = []

        if snapshot_date is not None:
            clauses.append("snapshot_date = ?")
            params.append(snapshot_date.isoformat())
        else:
            # Most recent date
            latest_row = self._conn.execute(
                "SELECT MAX(snapshot_date) FROM screen_snapshots"
            ).fetchone()
            if latest_row is None or latest_row[0] is None:
                return []
            clauses.append("snapshot_date = ?")
            params.append(latest_row[0])

        if ticker is not None:
            clauses.append("ticker = ?")
            params.append(ticker)

        sql = (
            "SELECT ticker, asset_id, snapshot_date, program_label, stage, ta, "
            "model_pos, implied_pos, spread_pp, rnpv_millions, ev_millions, "
            "acquisition_discount_pct, next_catalyst, catalyst_date, "
            "days_to_catalyst, single_asset, approximation_warning, "
            "thesis_strength, market_exceeds_model, config_quality, created_at "
            "FROM screen_snapshots"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY spread_pp DESC NULLS LAST, rnpv_millions DESC, ticker ASC, asset_id ASC LIMIT ?"
        params.append(limit)

        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def list_screen_snapshot_dates(self) -> list[date]:
        """Return all distinct snapshot_dates in descending order."""
        rows = self._conn.execute(
            "SELECT DISTINCT snapshot_date FROM screen_snapshots "
            "ORDER BY snapshot_date DESC"
        ).fetchall()
        return [date.fromisoformat(r[0]) for r in rows]

    def latest_screen_snapshot_date_on_or_before(self, as_of: date) -> Optional[date]:
        """Return the most recent screen_snapshot date on or before *as_of*."""
        row = self._conn.execute(
            "SELECT MAX(snapshot_date) FROM screen_snapshots WHERE snapshot_date <= ?",
            (as_of.isoformat(),),
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return date.fromisoformat(str(row[0]))

    def get_screen_snapshots_on_or_before(
        self,
        as_of: date,
        *,
        ticker: Optional[str] = None,
        limit: int = 200,
    ) -> tuple[Optional[date], "list[dict]"]:
        """
        Return screen snapshots for the latest snapshot_date on or before *as_of*.

        Returns ``(resolved_snapshot_date, rows)``. If no snapshot exists on or before
        *as_of*, returns ``(None, [])``.
        """
        snapshot_date = self.latest_screen_snapshot_date_on_or_before(as_of)
        if snapshot_date is None:
            return None, []
        return snapshot_date, self.get_screen_snapshots(
            snapshot_date=snapshot_date,
            ticker=ticker,
            limit=limit,
        )

    def get_screen_snapshot_for_ticker_on_or_before(
        self,
        *,
        ticker: str,
        as_of: date,
    ) -> Optional[dict]:
        """
        Return the latest stored screen snapshot for one ticker on or before *as_of*.

        Unlike ``get_screen_snapshots_on_or_before()``, this resolves the latest
        snapshot date for the specific ticker rather than the global screen date.
        """
        row = self._conn.execute(
            """
            SELECT ticker, snapshot_date, program_label, stage, ta,
                   asset_id,
                   model_pos, implied_pos, spread_pp, rnpv_millions, ev_millions,
                   acquisition_discount_pct, next_catalyst, catalyst_date,
                   days_to_catalyst, single_asset, approximation_warning,
                   thesis_strength, market_exceeds_model, config_quality, created_at
            FROM screen_snapshots
            WHERE ticker = ? AND snapshot_date <= ?
            ORDER BY snapshot_date DESC, spread_pp DESC NULLS LAST, rnpv_millions DESC, asset_id ASC
            LIMIT 1
            """,
            (ticker, as_of.isoformat()),
        ).fetchone()
        return dict(row) if row is not None else None

    def get_screen_snapshot_for_asset_on_or_before(
        self,
        *,
        asset_id: str,
        as_of: date,
    ) -> Optional[dict]:
        """
        Return the latest stored screen snapshot for one asset on or before *as_of*.
        """
        row = self._conn.execute(
            """
            SELECT ticker, asset_id, snapshot_date, program_label, stage, ta,
                   model_pos, implied_pos, spread_pp, rnpv_millions, ev_millions,
                   acquisition_discount_pct, next_catalyst, catalyst_date,
                   days_to_catalyst, single_asset, approximation_warning,
                   thesis_strength, market_exceeds_model, config_quality, created_at
            FROM screen_snapshots
            WHERE asset_id = ? AND snapshot_date <= ?
            ORDER BY snapshot_date DESC
            LIMIT 1
            """,
            (asset_id, as_of.isoformat()),
        ).fetchone()
        return dict(row) if row is not None else None

    # ------------------------------------------------------------------
    # Company SOTP snapshots
    # ------------------------------------------------------------------

    def write_company_sotp_snapshots(
        self,
        rows: "list",
        snapshot_date: Optional[date] = None,
    ) -> int:
        from uuid import uuid4

        rows = list(rows)
        snapshot_dates = {
            (snapshot_date or getattr(row, "snapshot_date")).isoformat()
            for row in rows
        }
        for snap_date in snapshot_dates:
            self._conn.execute(
                "DELETE FROM company_sotp_snapshots WHERE snapshot_date = ?",
                (snap_date,),
            )

        written = 0
        for row in rows:
            snap_date = snapshot_date or getattr(row, "snapshot_date")
            buckets = [
                bucket.model_dump(mode="json") if hasattr(bucket, "model_dump") else dict(bucket)
                for bucket in getattr(row, "buckets", [])
            ]
            limitations = list(getattr(row, "limitations", []))
            modeled_asset_ids = list(getattr(row, "modeled_asset_ids", []))
            balance_sheet_snapshot_date = getattr(row, "balance_sheet_snapshot_date", None)
            balance_sheet_period_end_date = getattr(row, "balance_sheet_period_end_date", None)
            self._conn.execute(
                """
                INSERT OR REPLACE INTO company_sotp_snapshots(
                    snapshot_id, ticker, company_id, company_name, snapshot_date, rank,
                    market_cap_millions, enterprise_value_millions, sotp_equity_value_millions,
                    sotp_per_share, sotp_discount, ranked_sotp_discount,
                    reconciliation_gap_millions, reconciliation_gap_pct,
                    reconciliation_status, reconciliation_passes_gate,
                    mcap_trend_3m_pct, sotp_tier, sotp_action, sotp_confidence_tier,
                    sotp_tier_reason, modeled_asset_coverage_pct, asset_count_modeled, modeled_asset_ids_json,
                    config_quality_summary, modeled_asset_confidence_min,
                    modeled_asset_confidence_avg, manual_bucket_share_pct,
                    manual_bucket_confidence_avg, n_bucket_sources,
                    action_policy, action_reason,
                    market_cap_source, balance_sheet_source, balance_sheet_source_ref,
                    balance_sheet_snapshot_date, balance_sheet_period_end_date,
                    balance_sheet_form_type, balance_sheet_is_point_in_time,
                    balance_sheet_age_days, balance_sheet_passes_recency_gate,
                    balance_sheet_recency_penalty, bucket_count, buckets_json,
                    limitations_json, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    getattr(row, "ticker"),
                    getattr(row, "company_id"),
                    getattr(row, "company_name"),
                    snap_date.isoformat(),
                    int(getattr(row, "rank", 0)),
                    float(getattr(row, "market_cap_millions")),
                    float(getattr(row, "enterprise_value_millions")),
                    float(getattr(row, "sotp_equity_value_millions")),
                    float(getattr(row, "sotp_per_share")),
                    float(getattr(row, "sotp_discount")),
                    float(getattr(row, "ranked_sotp_discount")),
                    float(getattr(row, "reconciliation_gap_millions", 0.0)),
                    float(getattr(row, "reconciliation_gap_pct", 0.0)),
                    getattr(row, "reconciliation_status", None),
                    1 if bool(getattr(row, "reconciliation_passes_gate", True)) else 0,
                    (
                        float(getattr(row, "mcap_trend_3m_pct"))
                        if getattr(row, "mcap_trend_3m_pct", None) is not None
                        else None
                    ),
                    getattr(row, "sotp_tier", None),
                    getattr(row, "sotp_action", None),
                    getattr(row, "sotp_confidence_tier", None),
                    getattr(row, "sotp_tier_reason", None),
                    float(getattr(row, "modeled_asset_coverage_pct")),
                    int(getattr(row, "asset_count_modeled")),
                    json.dumps(modeled_asset_ids),
                    getattr(row, "config_quality_summary", None),
                    float(getattr(row, "modeled_asset_confidence_min", 0.0)),
                    float(getattr(row, "modeled_asset_confidence_avg", 0.0)),
                    float(getattr(row, "manual_bucket_share_pct", 0.0)),
                    (
                        float(getattr(row, "manual_bucket_confidence_avg"))
                        if getattr(row, "manual_bucket_confidence_avg", None) is not None
                        else None
                    ),
                    int(getattr(row, "n_bucket_sources", 0)),
                    getattr(row, "action_policy", None),
                    getattr(row, "action_reason", None),
                    getattr(row, "market_cap_source", None),
                    getattr(row, "balance_sheet_source", None),
                    getattr(row, "balance_sheet_source_ref", None),
                    (
                        balance_sheet_snapshot_date.isoformat()
                        if balance_sheet_snapshot_date is not None
                        else None
                    ),
                    (
                        balance_sheet_period_end_date.isoformat()
                        if balance_sheet_period_end_date is not None
                        else None
                    ),
                    getattr(row, "balance_sheet_form_type", None),
                    1 if bool(getattr(row, "balance_sheet_is_point_in_time", False)) else 0,
                    getattr(row, "balance_sheet_age_days", None),
                    1 if bool(getattr(row, "balance_sheet_passes_recency_gate", False)) else 0,
                    float(getattr(row, "balance_sheet_recency_penalty", 1.0)),
                    len(buckets),
                    json.dumps(buckets),
                    json.dumps(limitations),
                    getattr(row, "notes", None),
                    datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
                        "+00:00",
                        "Z",
                    ),
                ),
            )
            written += 1
        self._conn.commit()
        return written

    def get_company_sotp_snapshots(
        self,
        snapshot_date: Optional[date] = None,
        *,
        ticker: Optional[str] = None,
        limit: int = 200,
    ) -> "list[dict]":
        clauses: list[str] = []
        params: list[object] = []

        if snapshot_date is not None:
            clauses.append("snapshot_date = ?")
            params.append(snapshot_date.isoformat())
        else:
            latest_row = self._conn.execute(
                "SELECT MAX(snapshot_date) FROM company_sotp_snapshots"
            ).fetchone()
            if latest_row is None or latest_row[0] is None:
                return []
            clauses.append("snapshot_date = ?")
            params.append(latest_row[0])

        if ticker is not None:
            clauses.append("ticker = ?")
            params.append(ticker)

        sql = (
            "SELECT ticker, company_id, company_name, snapshot_date, rank, "
            "market_cap_millions, enterprise_value_millions, sotp_equity_value_millions, "
            "sotp_per_share, sotp_discount, ranked_sotp_discount, "
            "reconciliation_gap_millions, reconciliation_gap_pct, reconciliation_status, reconciliation_passes_gate, "
            "mcap_trend_3m_pct, sotp_tier, sotp_action, sotp_confidence_tier, sotp_tier_reason, modeled_asset_coverage_pct, "
            "asset_count_modeled, modeled_asset_ids_json, config_quality_summary, "
            "modeled_asset_confidence_min, modeled_asset_confidence_avg, "
            "manual_bucket_share_pct, manual_bucket_confidence_avg, n_bucket_sources, "
            "action_policy, action_reason, market_cap_source, balance_sheet_source, balance_sheet_source_ref, "
            "balance_sheet_snapshot_date, balance_sheet_period_end_date, balance_sheet_form_type, "
            "balance_sheet_is_point_in_time, balance_sheet_age_days, "
            "balance_sheet_passes_recency_gate, balance_sheet_recency_penalty, bucket_count, "
            "buckets_json, limitations_json, notes, created_at "
            "FROM company_sotp_snapshots"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY ranked_sotp_discount DESC, ticker ASC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [self._decode_company_sotp_snapshot_row(dict(row)) for row in rows]

    def list_company_sotp_snapshot_dates(self) -> list[date]:
        rows = self._conn.execute(
            "SELECT DISTINCT snapshot_date FROM company_sotp_snapshots ORDER BY snapshot_date DESC"
        ).fetchall()
        return [date.fromisoformat(r[0]) for r in rows]

    def latest_company_sotp_snapshot_date_on_or_before(self, as_of: date) -> Optional[date]:
        row = self._conn.execute(
            "SELECT MAX(snapshot_date) FROM company_sotp_snapshots WHERE snapshot_date <= ?",
            (as_of.isoformat(),),
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return date.fromisoformat(str(row[0]))

    def get_company_sotp_snapshots_on_or_before(
        self,
        as_of: date,
        *,
        ticker: Optional[str] = None,
        limit: int = 200,
    ) -> tuple[Optional[date], "list[dict]"]:
        snapshot_date = self.latest_company_sotp_snapshot_date_on_or_before(as_of)
        if snapshot_date is None:
            return None, []
        return snapshot_date, self.get_company_sotp_snapshots(
            snapshot_date=snapshot_date,
            ticker=ticker,
            limit=limit,
        )

    def get_company_sotp_snapshot_for_ticker_on_or_before(
        self,
        *,
        ticker: str,
        as_of: date,
    ) -> Optional[dict]:
        row = self._conn.execute(
            """
            SELECT ticker, company_id, company_name, snapshot_date, rank,
                   market_cap_millions, enterprise_value_millions, sotp_equity_value_millions,
                   sotp_per_share, sotp_discount, ranked_sotp_discount,
                   reconciliation_gap_millions, reconciliation_gap_pct,
                   reconciliation_status, reconciliation_passes_gate,
                   mcap_trend_3m_pct, sotp_tier, sotp_action, sotp_confidence_tier,
                   sotp_tier_reason, modeled_asset_coverage_pct, asset_count_modeled, modeled_asset_ids_json,
                   config_quality_summary, modeled_asset_confidence_min,
                   modeled_asset_confidence_avg, manual_bucket_share_pct,
                   manual_bucket_confidence_avg, n_bucket_sources, action_policy, action_reason,
                   market_cap_source, balance_sheet_source, balance_sheet_source_ref,
                   balance_sheet_snapshot_date, balance_sheet_period_end_date,
                   balance_sheet_form_type, balance_sheet_is_point_in_time,
                   balance_sheet_age_days, balance_sheet_passes_recency_gate,
                   balance_sheet_recency_penalty, bucket_count, buckets_json,
                   limitations_json, notes, created_at
            FROM company_sotp_snapshots
            WHERE ticker = ? AND snapshot_date <= ?
            ORDER BY snapshot_date DESC, ranked_sotp_discount DESC
            LIMIT 1
            """,
            (ticker, as_of.isoformat()),
        ).fetchone()
        if row is None:
            return None
        return self._decode_company_sotp_snapshot_row(dict(row))

    def get_company_sotp_snapshot_for_company_id_on_or_before(
        self,
        *,
        company_id: str,
        as_of: date,
    ) -> Optional[dict]:
        row = self._conn.execute(
            """
            SELECT ticker, company_id, company_name, snapshot_date, rank,
                   market_cap_millions, enterprise_value_millions, sotp_equity_value_millions,
                   sotp_per_share, sotp_discount, ranked_sotp_discount,
                   reconciliation_gap_millions, reconciliation_gap_pct,
                   reconciliation_status, reconciliation_passes_gate,
                   mcap_trend_3m_pct, sotp_tier, sotp_action, sotp_confidence_tier,
                   sotp_tier_reason, modeled_asset_coverage_pct, asset_count_modeled, modeled_asset_ids_json,
                   config_quality_summary, modeled_asset_confidence_min,
                   modeled_asset_confidence_avg, manual_bucket_share_pct,
                   manual_bucket_confidence_avg, n_bucket_sources, action_policy, action_reason,
                   market_cap_source, balance_sheet_source, balance_sheet_source_ref,
                   balance_sheet_snapshot_date, balance_sheet_period_end_date,
                   balance_sheet_form_type, balance_sheet_is_point_in_time,
                   balance_sheet_age_days, balance_sheet_passes_recency_gate,
                   balance_sheet_recency_penalty, bucket_count, buckets_json,
                   limitations_json, notes, created_at
            FROM company_sotp_snapshots
            WHERE company_id = ? AND snapshot_date <= ?
            ORDER BY snapshot_date DESC, ranked_sotp_discount DESC
            LIMIT 1
            """,
            (company_id, as_of.isoformat()),
        ).fetchone()
        if row is None:
            return None
        return self._decode_company_sotp_snapshot_row(dict(row))

    # ------------------------------------------------------------------
    # Equity policy snapshots
    # ------------------------------------------------------------------

    def write_equity_policy_snapshots(
        self,
        rows: list[EquityPolicySnapshotRecord],
    ) -> int:
        from uuid import uuid4

        if not rows:
            return 0

        written = 0
        for row in rows:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO equity_policy_snapshots(
                    snapshot_id, ticker, as_of_date, reference_snapshot_date,
                    company_snapshot_date, source_mode, company_action_policy,
                    company_action_reason, company_ranked_discount, composite_score,
                    current_price, base_sotp_per_share, bear_sotp_per_share,
                    bull_sotp_per_share, conviction, adv_millions,
                    next_catalyst_days, catalyst_description, action, sizing_pct,
                    rationale, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    row.ticker,
                    row.as_of_date.isoformat(),
                    (
                        row.reference_snapshot_date.isoformat()
                        if row.reference_snapshot_date is not None
                        else None
                    ),
                    (
                        row.company_snapshot_date.isoformat()
                        if row.company_snapshot_date is not None
                        else None
                    ),
                    row.source_mode,
                    row.company_action_policy,
                    row.company_action_reason,
                    row.company_ranked_discount,
                    row.composite_score,
                    row.current_price,
                    row.base_sotp_per_share,
                    row.bear_sotp_per_share,
                    row.bull_sotp_per_share,
                    row.conviction,
                    row.adv_millions,
                    row.next_catalyst_days,
                    row.catalyst_description,
                    row.action,
                    row.sizing_pct,
                    row.rationale,
                    self._coerce_datetime(row.created_at).isoformat(timespec="seconds").replace(
                        "+00:00",
                        "Z",
                    ),
                ),
            )
            written += 1
        self._conn.commit()
        return written

    def get_equity_policy_snapshots(
        self,
        as_of_date: Optional[date] = None,
        *,
        ticker: Optional[str] = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[object] = []

        if as_of_date is not None:
            clauses.append("as_of_date = ?")
            params.append(as_of_date.isoformat())
        else:
            latest_row = self._conn.execute(
                "SELECT MAX(as_of_date) FROM equity_policy_snapshots"
            ).fetchone()
            if latest_row is None or latest_row[0] is None:
                return []
            clauses.append("as_of_date = ?")
            params.append(latest_row[0])

        if ticker is not None:
            clauses.append("ticker = ?")
            params.append(ticker)

        sql = (
            "SELECT ticker, as_of_date, reference_snapshot_date, company_snapshot_date, "
            "source_mode, company_action_policy, company_action_reason, company_ranked_discount, "
            "composite_score, current_price, base_sotp_per_share, bear_sotp_per_share, "
            "bull_sotp_per_share, conviction, adv_millions, next_catalyst_days, "
            "catalyst_description, action, sizing_pct, rationale, created_at "
            "FROM equity_policy_snapshots"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY composite_score DESC NULLS LAST, ticker ASC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [self._decode_equity_policy_snapshot_row(dict(row)) for row in rows]

    def get_equity_policy_snapshot_for_ticker_on_or_before(
        self,
        *,
        ticker: str,
        as_of: date,
    ) -> Optional[dict[str, Any]]:
        row = self._conn.execute(
            """
            SELECT ticker, as_of_date, reference_snapshot_date, company_snapshot_date,
                   source_mode, company_action_policy, company_action_reason,
                   company_ranked_discount, composite_score, current_price,
                   base_sotp_per_share, bear_sotp_per_share, bull_sotp_per_share,
                   conviction, adv_millions, next_catalyst_days, catalyst_description,
                   action, sizing_pct, rationale, created_at
            FROM equity_policy_snapshots
            WHERE ticker = ? AND as_of_date <= ?
            ORDER BY as_of_date DESC
            LIMIT 1
            """,
            (ticker, as_of.isoformat()),
        ).fetchone()
        if row is None:
            return None
        return self._decode_equity_policy_snapshot_row(dict(row))

    @staticmethod
    def _decode_equity_policy_snapshot_row(row: dict[str, Any]) -> dict[str, Any]:
        for key in ("as_of_date", "reference_snapshot_date", "company_snapshot_date"):
            if row.get(key):
                row[key] = date.fromisoformat(str(row[key]))
            else:
                row[key] = None
        row["created_at"] = KnowledgeStore._coerce_datetime(row.get("created_at"))
        return row

    @staticmethod
    def _decode_company_sotp_snapshot_row(row: dict[str, Any]) -> dict[str, Any]:
        row["snapshot_date"] = date.fromisoformat(str(row["snapshot_date"]))
        if row.get("balance_sheet_snapshot_date"):
            row["balance_sheet_snapshot_date"] = date.fromisoformat(
                str(row["balance_sheet_snapshot_date"])
            )
        else:
            row["balance_sheet_snapshot_date"] = None
        if row.get("balance_sheet_period_end_date"):
            row["balance_sheet_period_end_date"] = date.fromisoformat(
                str(row["balance_sheet_period_end_date"])
            )
        else:
            row["balance_sheet_period_end_date"] = None
        row["balance_sheet_is_point_in_time"] = bool(row.get("balance_sheet_is_point_in_time", 0))
        row["balance_sheet_passes_recency_gate"] = bool(
            row.get("balance_sheet_passes_recency_gate", 0)
        )
        row["reconciliation_passes_gate"] = bool(row.get("reconciliation_passes_gate", 1))
        if row.get("mcap_trend_3m_pct") is not None:
            row["mcap_trend_3m_pct"] = float(row["mcap_trend_3m_pct"])
        row["modeled_asset_ids"] = json.loads(row.pop("modeled_asset_ids_json", "[]") or "[]")
        row["buckets"] = json.loads(row.pop("buckets_json", "[]") or "[]")
        row["limitations"] = json.loads(row.pop("limitations_json", "[]") or "[]")
        row["created_at"] = row.get("created_at")
        return row

    # ------------------------------------------------------------------
    # Universe snapshots  (Sprint 12B)
    # ------------------------------------------------------------------

    def write_universe_snapshot(self, candidates: "list") -> int:
        """
        Upsert UniverseCandidate rows into universe_snapshots.
        Returns number of rows written.
        """
        import json as _json
        from uuid import uuid4

        written = 0
        for c in candidates:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO universe_snapshots(
                    snapshot_id, ticker, build_date, company_name,
                    market_cap_m, adv_m, has_phase2_plus, active_nct_ids,
                    passed, exclusion_reason, sources, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    c.ticker,
                    c.as_of.isoformat(),
                    c.company_name,
                    c.market_cap_m,
                    c.adv_m,
                    1 if c.has_phase2_plus else 0,
                    _json.dumps(c.active_phase2_studies),
                    1 if c.passed else 0,
                    c.exclusion_reason,
                    _json.dumps(c.sources),
                    datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
                        "+00:00",
                        "Z",
                    ),
                ),
            )
            written += 1
        self._conn.commit()
        return written

    def get_universe_snapshot(
        self,
        build_date: Optional[date] = None,
        *,
        passed_only: bool = False,
        limit: int = 300,
    ) -> list[dict]:
        """
        Return universe snapshot rows as plain dicts.

        Parameters
        ----------
        build_date  : filter to specific date; if None returns most recent build
        passed_only : if True, return only rows where passed=1
        limit       : max rows
        """
        import json as _json

        clauses: list[str] = []
        params: list[object] = []

        if build_date is not None:
            clauses.append("build_date = ?")
            params.append(build_date.isoformat())
        else:
            latest = self._conn.execute(
                "SELECT MAX(build_date) FROM universe_snapshots"
            ).fetchone()
            if latest is None or latest[0] is None:
                return []
            clauses.append("build_date = ?")
            params.append(latest[0])

        if passed_only:
            clauses.append("passed = 1")

        sql = (
            "SELECT ticker, build_date, company_name, market_cap_m, adv_m, "
            "has_phase2_plus, active_nct_ids, passed, exclusion_reason, sources "
            "FROM universe_snapshots"
        )
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY passed DESC, market_cap_m DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["has_phase2_plus"] = bool(d["has_phase2_plus"])
            d["passed"] = bool(d["passed"])
            d["active_nct_ids"] = _json.loads(d["active_nct_ids"] or "[]")
            d["sources"] = _json.loads(d["sources"] or "[]")
            result.append(d)
        return result

    def list_universe_build_dates(self) -> list[date]:
        """Return all distinct universe build dates in descending order."""
        rows = self._conn.execute(
            "SELECT DISTINCT build_date FROM universe_snapshots "
            "ORDER BY build_date DESC"
        ).fetchall()
        return [date.fromisoformat(r[0]) for r in rows]

    # ------------------------------------------------------------------
    # Sprint 16 — pos_predictions + pos_outcomes (calibration database)
    # ------------------------------------------------------------------

    def insert_pos_prediction(self, pred: "PredictionRecord") -> str:  # type: ignore[name-defined]  # noqa: F821
        """
        Insert one PredictionRecord into pos_predictions.

        Discipline: ONLY call at the time the prediction is made.
        Returns the new row id.
        """
        import uuid as _uuid
        from datetime import datetime as _dt, timezone as _tz

        row_id = str(_uuid.uuid4())
        created_at = _dt.now(_tz.utc).isoformat(timespec="seconds")
        predicted_at = (
            pred.predicted_at.isoformat()
            if pred.predicted_at is not None
            else created_at[:10]
        )
        trial_end = (
            pred.trial_end_expected.isoformat()
            if pred.trial_end_expected is not None
            else None
        )
        self._conn.execute(
            """
            INSERT INTO pos_predictions(
                id, program_id, ticker, ta, phase, model_pos, implied_pos,
                spread_pp, peak_sales_millions, rnpv_millions,
                predicted_at, trial_end_expected, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_id, pred.program_id, pred.ticker, pred.ta, pred.phase,
                pred.model_pos, pred.implied_pos, pred.spread_pp,
                pred.peak_sales_millions, pred.rnpv_millions,
                predicted_at, trial_end, created_at,
            ),
        )
        self._conn.commit()
        return row_id

    def get_pos_predictions(
        self,
        *,
        program_id: Optional[str] = None,
        ticker: Optional[str] = None,
        limit: int = 1000,
    ) -> list[dict]:
        """Return pos_predictions rows as dicts, newest first."""
        clauses: list[str] = []
        params: list = []
        if program_id is not None:
            clauses.append("program_id = ?")
            params.append(program_id)
        if ticker is not None:
            clauses.append("ticker = ?")
            params.append(ticker)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        cols = [
            "id", "program_id", "ticker", "ta", "phase", "model_pos", "implied_pos",
            "spread_pp", "peak_sales_millions", "rnpv_millions",
            "predicted_at", "trial_end_expected", "created_at",
        ]
        rows = self._conn.execute(
            f"SELECT {', '.join(cols)} FROM pos_predictions {where} "
            f"ORDER BY predicted_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def upsert_pos_outcome(self, outcome: "OutcomeRecord") -> None:  # type: ignore[name-defined]  # noqa: F821
        """
        Insert or replace one OutcomeRecord in pos_outcomes.

        UNIQUE(program_id) — one outcome per program.
        """
        import uuid as _uuid
        from datetime import datetime as _dt, timezone as _tz

        row_id = str(_uuid.uuid4())
        created_at = _dt.now(_tz.utc).isoformat(timespec="seconds")
        outcome_date = (
            outcome.outcome_date.isoformat()
            if outcome.outcome_date is not None
            else None
        )
        self._conn.execute(
            """
            INSERT OR REPLACE INTO pos_outcomes(
                id, program_id, outcome_date, outcome_type, trial_name, source, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_id, outcome.program_id, outcome_date, outcome.outcome_type,
                outcome.trial_name, outcome.source, created_at,
            ),
        )
        self._conn.commit()

    def get_pos_outcomes(
        self,
        *,
        program_id: Optional[str] = None,
        outcome_type: Optional[str] = None,
    ) -> list[dict]:
        """Return pos_outcomes rows as dicts."""
        clauses: list[str] = []
        params: list = []
        if program_id is not None:
            clauses.append("program_id = ?")
            params.append(program_id)
        if outcome_type is not None:
            clauses.append("outcome_type = ?")
            params.append(outcome_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        cols = ["id", "program_id", "outcome_date", "outcome_type", "trial_name", "source", "created_at"]
        rows = self._conn.execute(
            f"SELECT {', '.join(cols)} FROM pos_outcomes {where}",
            params,
        ).fetchall()
        return [dict(zip(cols, r)) for r in rows]

    # ------------------------------------------------------------------
    # Sprint 15 — detected_events (real-time event monitor)
    # ------------------------------------------------------------------

    def insert_detected_events(self, events: "list") -> int:
        """
        Insert DetectedEvent list into detected_events table.

        Deduplication: UNIQUE(ticker, event_type, headline_key, detected_date).
        Duplicate rows are silently ignored (INSERT OR IGNORE).

        Returns number of rows actually inserted.
        """
        import json as _json
        from datetime import datetime as _dt, timezone as _tz

        inserted = 0
        for ev in events:
            import uuid as _uuid
            row_id = str(_uuid.uuid4())
            headline_key = ev.headline[:80]
            detected_at_str = (
                ev.detected_at.isoformat()
                if hasattr(ev.detected_at, "isoformat")
                else str(ev.detected_at)
            )
            detected_date = detected_at_str[:10]  # YYYY-MM-DD
            created_at = _dt.now(_tz.utc).isoformat(timespec="seconds")
            cursor = self._conn.execute(
                """
                INSERT OR IGNORE INTO detected_events(
                    id, ticker, asset_id, event_type, headline, headline_key,
                    source_url, detected_at, detected_date, requires_recompute,
                    extra_json, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row_id,
                    ev.ticker,
                    ev.asset_id,
                    ev.event_type,
                    ev.headline,
                    headline_key,
                    ev.source_url,
                    detected_at_str,
                    detected_date,
                    1 if ev.requires_recompute else 0,
                    _json.dumps(ev.extra) if ev.extra else None,
                    created_at,
                ),
            )
            inserted += cursor.rowcount
        self._conn.commit()
        return inserted

    def get_detected_events(
        self,
        since: Optional[str] = None,
        *,
        ticker: Optional[str] = None,
        requires_recompute: Optional[bool] = None,
        limit: int = 500,
    ) -> list[dict]:
        """
        Return detected_events rows as list of dicts.

        Parameters
        ----------
        since           : ISO datetime string; only events detected_at >= since
        ticker          : filter to one ticker
        requires_recompute : filter to rows where requires_recompute matches
        limit           : max rows (default 500)
        """
        clauses: list[str] = []
        params: list = []

        if since is not None:
            clauses.append("detected_at >= ?")
            params.append(since)
        if ticker is not None:
            clauses.append("ticker = ?")
            params.append(ticker)
        if requires_recompute is not None:
            clauses.append("requires_recompute = ?")
            params.append(1 if requires_recompute else 0)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"SELECT id, ticker, asset_id, event_type, headline, headline_key, "
            f"source_url, detected_at, detected_date, requires_recompute, extra_json, created_at "
            f"FROM detected_events {where} "
            f"ORDER BY detected_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()

        cols = [
            "id", "ticker", "asset_id", "event_type", "headline", "headline_key",
            "source_url", "detected_at", "detected_date", "requires_recompute",
            "extra_json", "created_at",
        ]
        return [dict(zip(cols, r)) for r in rows]

    def add_review_decision(
        self,
        decision: ReviewDecision,
        *,
        company_id: Optional[str],
        asset_id: Optional[str],
        source_trace: SourceTrace,
    ) -> None:
        import json as _json

        analyst_tags_json = _json.dumps(decision.analyst_tags) if decision.analyst_tags else "[]"
        self._conn.execute(
            """
            INSERT OR REPLACE INTO review_decisions(
                id, proposal_id, run_id, company_id, asset_id, decision, reviewer_id,
                reviewed_at, override_value, rationale, notes,
                reviewer_confidence, analyst_tags_json, supporting_quote,
                payload_json, source_trace_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision.id,
                decision.proposal_id,
                decision.run_id,
                company_id,
                asset_id,
                decision.decision,
                decision.reviewer_id,
                decision.reviewed_at.isoformat(),
                decision.override_value,
                decision.rationale,
                decision.notes,
                decision.reviewer_confidence,
                analyst_tags_json,
                decision.supporting_quote,
                decision.model_dump_json(),
                source_trace.model_dump_json(),
            ),
        )
        # Append-only audit log entry for every review decision (Wave 3C).
        # For ACCEPTED decisions, populate lineage fields (Task 9.22) so a
        # compliance reviewer can answer "why did assumption X change?".
        lineage: dict = {}
        if decision.decision == "accepted" and decision.override_value is not None:
            lineage["assumption_field"] = "override_value"
            lineage["assumption_new_value"] = str(decision.override_value)
            # Surface the signal_id from the proposal when available
            try:
                proposal = self.get_proposal(decision.proposal_id)
                if proposal:
                    lineage["evidence_signal_id"] = getattr(proposal, "signal_id", None)
            except Exception:
                pass
            lineage["review_decision_id"] = decision.id

        self._append_audit_log(
            event_type="review_decision",
            entity_type="proposal",
            entity_id=decision.proposal_id,
            actor_id=decision.reviewer_id,
            action=decision.decision,
            payload_json=decision.model_dump_json(),
            **lineage,
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Audit log (3C) — internal helpers + public query interface
    # ------------------------------------------------------------------

    def _append_audit_log(
        self,
        *,
        event_type: str,
        entity_type: str,
        entity_id: str,
        actor_id: Optional[str],
        action: str,
        payload_json: str,
        # Task 9.22 — optional signal-to-assumption lineage fields
        assumption_field: Optional[str] = None,
        assumption_old_value: Optional[str] = None,
        assumption_new_value: Optional[str] = None,
        evidence_signal_id: Optional[str] = None,
        review_decision_id: Optional[str] = None,
    ) -> None:
        """Append one row to the append-only audit_log table.

        The five optional lineage fields (Task 9.22) link an accepted review
        decision to the specific assumption change it triggered.  Pass them
        when recording an ACCEPTED decision that modifies a valuation field.
        """
        import uuid as _uuid

        self._conn.execute(
            """
            INSERT INTO audit_log
                (audit_id, event_type, entity_type, entity_id,
                 actor_id, action, payload_json, created_at,
                 assumption_field, assumption_old_value, assumption_new_value,
                 evidence_signal_id, review_decision_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(_uuid.uuid4()),
                event_type,
                entity_type,
                entity_id,
                actor_id,
                action,
                payload_json,
                datetime.now(timezone.utc).isoformat(),
                assumption_field,
                assumption_old_value,
                assumption_new_value,
                evidence_signal_id,
                review_decision_id,
            ),
        )

    def query_audit_log(
        self,
        *,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        action: Optional[str] = None,
        assumption_field: Optional[str] = None,
        signal_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        """
        Return audit log rows as plain dicts, newest first.

        All filter parameters are optional; unset parameters match any value.

        Task 9.22 additions:
          assumption_field — filter to rows where a specific field was changed
          signal_id        — filter to rows linked to a specific evidence signal
        """
        clauses: list[str] = []
        params: list = []

        if entity_type is not None:
            clauses.append("entity_type = ?")
            params.append(entity_type)
        if entity_id is not None:
            clauses.append("entity_id = ?")
            params.append(entity_id)
        if actor_id is not None:
            clauses.append("actor_id = ?")
            params.append(actor_id)
        if action is not None:
            clauses.append("action = ?")
            params.append(action)
        if assumption_field is not None:
            clauses.append("assumption_field = ?")
            params.append(assumption_field)
        if signal_id is not None:
            clauses.append("evidence_signal_id = ?")
            params.append(signal_id)

        sql = "SELECT * FROM audit_log"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def add_memo(self, memo: MemoRecord) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO memos(
                id, company_id, asset_id, memo_type, title, created_at, payload_json, source_trace_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                memo.id,
                memo.company_id,
                memo.asset_id,
                memo.memo_type,
                memo.title,
                memo.created_at.isoformat(),
                memo.model_dump_json(),
                memo.source_trace.model_dump_json(),
            ),
        )
        self._conn.commit()

    def add_literature_review(
        self,
        review: object,
        *,
        source_trace: SourceTrace,
        company_id: Optional[str] = None,
        asset_id: Optional[str] = None,
    ) -> LiteratureReviewRecord:
        payload = review.model_dump(mode="json") if hasattr(review, "model_dump") else dict(review)
        review_id = str(payload.get("review_id") or payload.get("id") or uuid.uuid4())
        generated_at = self._coerce_datetime(payload.get("generated_at"))
        resolved_company_id = company_id if company_id is not None else payload.get("company_id")
        resolved_asset_id = asset_id if asset_id is not None else payload.get("asset_id")
        self._conn.execute(
            """
            INSERT OR REPLACE INTO literature_reviews(
                id, company_id, asset_id, generated_at, payload_json, source_trace_json
            ) VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                review_id,
                resolved_company_id,
                resolved_asset_id,
                generated_at.isoformat(),
                self._json_dump(payload),
                source_trace.model_dump_json(),
            ),
        )
        self._conn.commit()
        return LiteratureReviewRecord(
            id=review_id,
            company_id=resolved_company_id,
            asset_id=resolved_asset_id,
            generated_at=generated_at,
            payload_json=payload,
            source_trace=source_trace,
        )

    def add_competitive_landscape(
        self,
        landscape: object,
        *,
        source_trace: SourceTrace,
        company_id: Optional[str] = None,
        asset_id: Optional[str] = None,
    ) -> CompetitiveLandscapeRecord:
        payload = (
            landscape.model_dump(mode="json")
            if hasattr(landscape, "model_dump")
            else dict(landscape)
        )
        landscape_id = str(payload.get("landscape_id") or payload.get("id") or uuid.uuid4())
        generated_at = self._coerce_datetime(payload.get("generated_at"))
        resolved_company_id = company_id if company_id is not None else payload.get("company_id")
        resolved_asset_id = asset_id if asset_id is not None else payload.get("asset_id")
        self._conn.execute(
            """
            INSERT OR REPLACE INTO competitive_landscapes(
                id, company_id, asset_id, generated_at, payload_json, source_trace_json
            ) VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                landscape_id,
                resolved_company_id,
                resolved_asset_id,
                generated_at.isoformat(),
                self._json_dump(payload),
                source_trace.model_dump_json(),
            ),
        )
        self._conn.commit()
        return CompetitiveLandscapeRecord(
            id=landscape_id,
            company_id=resolved_company_id,
            asset_id=resolved_asset_id,
            generated_at=generated_at,
            payload_json=payload,
            source_trace=source_trace,
        )

    def add_research_report(
        self,
        report: object,
        *,
        source_trace: SourceTrace,
        company_id: Optional[str] = None,
        asset_id: Optional[str] = None,
    ) -> ResearchReportRecord:
        payload = report.model_dump(mode="json") if hasattr(report, "model_dump") else dict(report)
        report_id = str(payload.get("report_id") or payload.get("id") or uuid.uuid4())
        generated_at = self._coerce_datetime(payload.get("generated_at"))
        resolved_company_id = company_id if company_id is not None else payload.get("company_id")
        resolved_asset_id = asset_id if asset_id is not None else payload.get("asset_id")
        self._conn.execute(
            """
            INSERT OR REPLACE INTO research_reports(
                id, company_id, asset_id, report_version, model_version,
                generated_at, payload_json, source_trace_json
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                resolved_company_id,
                resolved_asset_id,
                payload.get("report_version"),
                payload.get("model_version"),
                generated_at.isoformat(),
                self._json_dump(payload),
                source_trace.model_dump_json(),
            ),
        )
        self._conn.commit()
        return ResearchReportRecord(
            id=report_id,
            company_id=resolved_company_id,
            asset_id=resolved_asset_id,
            report_version=payload.get("report_version"),
            model_version=payload.get("model_version"),
            generated_at=generated_at,
            payload_json=payload,
            source_trace=source_trace,
        )

    def add_dossier(self, dossier: DossierRecord) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO dossiers(
                id, company_id, asset_id, generated_at, payload_json, source_trace_json
            ) VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                dossier.id,
                dossier.company_id,
                dossier.asset_id,
                dossier.generated_at.isoformat(),
                dossier.model_dump_json(),
                dossier.source_trace.model_dump_json(),
            ),
        )
        self._conn.commit()

    # ---------------------------------------------------------------------
    # Retrieval
    # ---------------------------------------------------------------------

    def get_raw_documents(
        self,
        *,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 100,
    ) -> list[RawDocumentRecord]:
        clauses = []
        params: list[object] = []
        if date_from is not None:
            clauses.append("DATE(created_at) >= DATE(?)")
            params.append(date_from.isoformat())
        if date_to is not None:
            clauses.append("DATE(created_at) <= DATE(?)")
            params.append(date_to.isoformat())

        sql = "SELECT payload_json FROM raw_documents"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        out: list[RawDocumentRecord] = []
        for r in rows:
            payload = json.loads(r["payload_json"])
            out.append(
                RawDocumentRecord(
                    id=str(payload.get("id")),
                    payload_json=payload,
                    created_at=self._coerce_datetime(
                        payload.get("created_at") or payload.get("retrieved_at")
                    ),
                )
            )
        return out

    def get_evidence_facts(
        self,
        *,
        company_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        fact_key: Optional[str] = None,
        only_active: bool = False,
        limit: int = 200,
    ) -> list[dict]:
        clauses = []
        params: list[object] = []
        if company_id is not None:
            clauses.append("company_id = ?")
            params.append(company_id)
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        if fact_key is not None:
            clauses.append("fact_key = ?")
            params.append(fact_key)
        if only_active:
            clauses.append("is_active = 1")

        sql = "SELECT payload_json FROM evidence_facts"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def apply_retention_policy(
        self,
        *,
        raw_documents_days: int = 90,
        reference_time: Optional[datetime] = None,
    ) -> DataRetentionResult:
        applied_at = self._coerce_datetime(reference_time)
        retention_days = max(1, int(raw_documents_days))
        cutoff = applied_at - timedelta(days=retention_days)
        cur = self._conn.execute(
            """
            DELETE FROM raw_documents
            WHERE julianday(created_at) < julianday(?)
            """,
            (cutoff.isoformat(),),
        )
        self._conn.commit()
        return DataRetentionResult(
            applied_at=applied_at,
            raw_documents_retention_days=retention_days,
            raw_documents_deleted=max(int(cur.rowcount or 0), 0),
            structured_signals_deleted=0,
        )

    def get_extraction_results(
        self,
        *,
        company_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        event_type: Optional[str | EventType] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 100,
    ) -> list[ExtractionResultRecord]:
        clauses = []
        params: list[object] = []
        if company_id is not None:
            clauses.append("company_id = ?")
            params.append(company_id)
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        resolved_event_type = self._event_type_value(event_type)
        if resolved_event_type is not None:
            clauses.append("event_type = ?")
            params.append(resolved_event_type)
        if date_from is not None:
            clauses.append("DATE(created_at) >= DATE(?)")
            params.append(date_from.isoformat())
        if date_to is not None:
            clauses.append("DATE(created_at) <= DATE(?)")
            params.append(date_to.isoformat())

        sql = "SELECT id, raw_document_id, payload_json, created_at FROM extraction_results"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [
            ExtractionResultRecord(
                id=row["id"],
                raw_document_id=row["raw_document_id"],
                payload_json=json.loads(row["payload_json"]),
                created_at=self._coerce_datetime(row["created_at"]),
            )
            for row in rows
        ]

    def get_structured_signals(
        self,
        *,
        company_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        event_type: Optional[str | EventType] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 100,
    ) -> list[StructuredSignalRecord]:
        clauses = []
        params: list[object] = []
        if company_id is not None:
            clauses.append("company_id = ?")
            params.append(company_id)
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        resolved_event_type = self._event_type_value(event_type)
        if resolved_event_type is not None:
            clauses.append("event_type = ?")
            params.append(resolved_event_type)
        if date_from is not None:
            clauses.append("DATE(signal_date) >= DATE(?)")
            params.append(date_from.isoformat())
        if date_to is not None:
            clauses.append("DATE(signal_date) <= DATE(?)")
            params.append(date_to.isoformat())

        sql = "SELECT id, extraction_result_id, payload_json, created_at FROM structured_signals"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY signal_date DESC, created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [
            StructuredSignalRecord(
                id=row["id"],
                extraction_result_id=row["extraction_result_id"],
                payload_json=json.loads(row["payload_json"]),
                created_at=self._coerce_datetime(row["created_at"]),
            )
            for row in rows
        ]

    def get_events(
        self,
        *,
        company_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        event_type: Optional[str | EventType] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 100,
    ) -> list[Event]:
        clauses = []
        params: list[object] = []
        if company_id is not None:
            clauses.append("company_id = ?")
            params.append(company_id)
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        resolved_event_type = self._event_type_value(event_type)
        if resolved_event_type is not None:
            clauses.append("event_type = ?")
            params.append(resolved_event_type)
        if date_from is not None:
            clauses.append("DATE(observed_at) >= DATE(?)")
            params.append(date_from.isoformat())
        if date_to is not None:
            clauses.append("DATE(observed_at) <= DATE(?)")
            params.append(date_to.isoformat())

        sql = "SELECT payload_json FROM events"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY observed_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [Event.model_validate_json(r["payload_json"]) for r in rows]

    def get_valuation_diffs(
        self,
        *,
        company_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        event_type: Optional[str | EventType] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 100,
    ) -> list[StoredValuationDiff]:
        clauses = []
        params: list[object] = []
        if company_id is not None:
            clauses.append("company_id = ?")
            params.append(company_id)
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        resolved_event_type = self._event_type_value(event_type)
        if resolved_event_type is not None:
            clauses.append("event_id IN (SELECT id FROM events WHERE event_type = ?)")
            params.append(resolved_event_type)
        if date_from is not None:
            clauses.append("DATE(created_at) >= DATE(?)")
            params.append(date_from.isoformat())
        if date_to is not None:
            clauses.append("DATE(created_at) <= DATE(?)")
            params.append(date_to.isoformat())

        sql = "SELECT payload_json FROM valuation_diffs"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [StoredValuationDiff.model_validate_json(r["payload_json"]) for r in rows]

    def get_review_decisions(
        self,
        *,
        company_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        decision: Optional[str] = None,
        event_type: Optional[str | EventType] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 100,
    ) -> list[ReviewDecision]:
        clauses = []
        params: list[object] = []
        if company_id is not None:
            clauses.append("company_id = ?")
            params.append(company_id)
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        if decision is not None:
            clauses.append("decision = ?")
            params.append(decision)
        resolved_event_type = self._event_type_value(event_type)
        if resolved_event_type is not None:
            clauses.append(
                "run_id IN ("
                "SELECT run_id FROM valuation_diffs "
                "WHERE event_id IN (SELECT id FROM events WHERE event_type = ?)"
                ")"
            )
            params.append(resolved_event_type)
        if date_from is not None:
            clauses.append("DATE(reviewed_at) >= DATE(?)")
            params.append(date_from.isoformat())
        if date_to is not None:
            clauses.append("DATE(reviewed_at) <= DATE(?)")
            params.append(date_to.isoformat())

        sql = "SELECT payload_json FROM review_decisions"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY reviewed_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [ReviewDecision.model_validate_json(r["payload_json"]) for r in rows]

    def get_memos(
        self,
        *,
        company_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        memo_type: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 100,
    ) -> list[MemoRecord]:
        clauses = []
        params: list[object] = []
        if company_id is not None:
            clauses.append("company_id = ?")
            params.append(company_id)
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        if memo_type is not None:
            clauses.append("memo_type = ?")
            params.append(memo_type)
        if date_from is not None:
            clauses.append("DATE(created_at) >= DATE(?)")
            params.append(date_from.isoformat())
        if date_to is not None:
            clauses.append("DATE(created_at) <= DATE(?)")
            params.append(date_to.isoformat())

        sql = "SELECT payload_json FROM memos"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [MemoRecord.model_validate_json(r["payload_json"]) for r in rows]

    def get_dossiers(
        self,
        *,
        company_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 100,
    ) -> list[DossierRecord]:
        clauses = []
        params: list[object] = []
        if company_id is not None:
            clauses.append("company_id = ?")
            params.append(company_id)
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        if date_from is not None:
            clauses.append("DATE(generated_at) >= DATE(?)")
            params.append(date_from.isoformat())
        if date_to is not None:
            clauses.append("DATE(generated_at) <= DATE(?)")
            params.append(date_to.isoformat())

        sql = "SELECT payload_json FROM dossiers"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY generated_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [DossierRecord.model_validate_json(r["payload_json"]) for r in rows]

    def get_literature_reviews(
        self,
        *,
        company_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[object] = []
        if company_id is not None:
            clauses.append("company_id = ?")
            params.append(company_id)
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        if date_from is not None:
            clauses.append("DATE(generated_at) >= DATE(?)")
            params.append(date_from.isoformat())
        if date_to is not None:
            clauses.append("DATE(generated_at) <= DATE(?)")
            params.append(date_to.isoformat())

        sql = "SELECT payload_json FROM literature_reviews"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY generated_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [json.loads(r["payload_json"]) for r in rows]

    def get_competitive_landscapes(
        self,
        *,
        company_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[object] = []
        if company_id is not None:
            clauses.append("company_id = ?")
            params.append(company_id)
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        if date_from is not None:
            clauses.append("DATE(generated_at) >= DATE(?)")
            params.append(date_from.isoformat())
        if date_to is not None:
            clauses.append("DATE(generated_at) <= DATE(?)")
            params.append(date_to.isoformat())

        sql = "SELECT payload_json FROM competitive_landscapes"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY generated_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [json.loads(r["payload_json"]) for r in rows]

    def get_research_reports(
        self,
        *,
        company_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[object] = []
        if company_id is not None:
            clauses.append("company_id = ?")
            params.append(company_id)
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        if date_from is not None:
            clauses.append("DATE(generated_at) >= DATE(?)")
            params.append(date_from.isoformat())
        if date_to is not None:
            clauses.append("DATE(generated_at) <= DATE(?)")
            params.append(date_to.isoformat())

        sql = "SELECT payload_json FROM research_reports"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY generated_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [json.loads(r["payload_json"]) for r in rows]

    # ---------------------------------------------------------------------
    # Dossier generation
    # ---------------------------------------------------------------------

    def generate_dossier(
        self,
        *,
        company_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        event_limit: int = 10,
        change_limit: int = 5,
        persist: bool = True,
    ) -> DossierRecord:
        if company_id is None and asset_id is None:
            raise ValueError("At least one of company_id or asset_id must be provided")

        recent_events = self.get_events(
            company_id=company_id,
            asset_id=asset_id,
            limit=event_limit,
        )
        recent_changes = self.get_valuation_diffs(
            company_id=company_id,
            asset_id=asset_id,
            limit=change_limit,
        )

        latest_ctx = self._latest_valuation_context(company_id=company_id, asset_id=asset_id)
        current_assumptions = latest_ctx.get("assumptions_snapshot", {})
        latest_valuation_snapshot = latest_ctx.get("valuation_snapshot", {})

        open_questions: list[str] = []
        for decision in self.get_review_decisions(
            company_id=company_id,
            asset_id=asset_id,
            decision="deferred",
            limit=10,
        ):
            open_questions.append(f"Deferred review {decision.id}: {decision.rationale}")
        for memo in self.get_memos(company_id=company_id, asset_id=asset_id, limit=5):
            open_questions.extend(memo.open_questions)

        # Deduplicate while preserving order.
        seen = set()
        deduped = []
        for q in open_questions:
            if q not in seen:
                seen.add(q)
                deduped.append(q)

        dossier = DossierRecord(
            id=str(uuid.uuid4()),
            company_id=company_id,
            asset_id=asset_id,
            generated_at=datetime.now(timezone.utc),
            recent_events=recent_events,
            current_assumptions=current_assumptions,
            latest_valuation_snapshot=latest_valuation_snapshot,
            recent_changes=recent_changes,
            open_questions=deduped,
            source_trace=SourceTrace(
                source_type="knowledge_layer",
                source_ref="KnowledgeStore.generate_dossier",
            ),
        )
        if persist:
            self.add_dossier(dossier)
        return dossier

    def _latest_valuation_context(
        self,
        *,
        company_id: Optional[str],
        asset_id: Optional[str],
    ) -> dict:
        clauses = []
        params: list[object] = []
        if company_id is not None:
            clauses.append("company_id = ?")
            params.append(company_id)
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)

        sql = "SELECT assumptions_snapshot_json, valuation_snapshot_json FROM valuation_diffs"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC LIMIT 1"
        row = self._conn.execute(sql, params).fetchone()
        if row is None:
            return {}
        assumptions_json = row["assumptions_snapshot_json"] or "{}"
        valuation_json = row["valuation_snapshot_json"] or "{}"
        return {
            "assumptions_snapshot": json.loads(assumptions_json),
            "valuation_snapshot": json.loads(valuation_json),
        }

    # ---------------------------------------------------------------------
    # Provenance
    # ---------------------------------------------------------------------

    @staticmethod
    def _table_map() -> dict[str, tuple[str, str]]:
        return {
            "raw_documents": ("raw_documents", "id"),
            "extraction_results": ("extraction_results", "id"),
            "structured_signals": ("structured_signals", "id"),
            "events": ("events", "id"),
            "valuation_diffs": ("valuation_diffs", "run_id"),
            "review_decisions": ("review_decisions", "id"),
            "memos": ("memos", "id"),
            "dossiers": ("dossiers", "id"),
            "literature_reviews": ("literature_reviews", "id"),
            "competitive_landscapes": ("competitive_landscapes", "id"),
            "research_reports": ("research_reports", "id"),
        }

    def get_source_trace(self, record_type: str, record_id: str) -> SourceTrace:
        """
        Retrieve provenance trace for a stored record.

        record_type:
          raw_documents | extraction_results | structured_signals | events |
          valuation_diffs | review_decisions | memos | dossiers |
          literature_reviews | competitive_landscapes | research_reports
        """
        table_map = self._table_map()
        if record_type not in table_map:
            raise ValueError(
                f"Unknown record_type={record_type!r}; expected one of {sorted(table_map)}"
            )
        table, pk = table_map[record_type]
        row = self._conn.execute(
            f"SELECT source_trace_json FROM {table} WHERE {pk} = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"No record found for {record_type}:{record_id}")
        return SourceTrace.model_validate_json(row["source_trace_json"])

    def _fetch_row(self, record_type: str, record_id: str) -> sqlite3.Row:
        table, pk = self._table_map()[record_type]
        row = self._conn.execute(
            f"SELECT * FROM {table} WHERE {pk} = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"No record found for {record_type}:{record_id}")
        return row

    def _node(self, record_type: str, record_id: str) -> Optional[dict[str, Any]]:
        try:
            row = self._fetch_row(record_type, record_id)
        except KeyError:
            return None
        return {
            "record_type": record_type,
            "record_id": record_id,
            "payload": json.loads(row["payload_json"]),
            "source_trace": SourceTrace.model_validate_json(row["source_trace_json"]).model_dump(
                mode="json"
            ),
        }

    def _latest_signal_for_event(
        self, event_id: str, preferred_signal_id: Optional[str]
    ) -> Optional[sqlite3.Row]:
        if preferred_signal_id:
            row = self._conn.execute(
                "SELECT * FROM structured_signals WHERE id = ?",
                (preferred_signal_id,),
            ).fetchone()
            if row is not None:
                return row
        return self._conn.execute(
            """
            SELECT *
              FROM structured_signals
             WHERE event_id = ?
             ORDER BY created_at DESC
             LIMIT 1
            """,
            (event_id,),
        ).fetchone()

    def _valuation_diff_for_event(self, event_id: str) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            """
            SELECT *
              FROM valuation_diffs
             WHERE event_id = ?
             ORDER BY created_at DESC
             LIMIT 1
            """,
            (event_id,),
        ).fetchone()

    def _review_rows_for_run(self, run_id: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            """
            SELECT *
              FROM review_decisions
             WHERE run_id = ?
             ORDER BY reviewed_at DESC
            """,
            (run_id,),
        ).fetchall()

    def _memo_rows_related(
        self, *, run_id: Optional[str], signal_id: Optional[str]
    ) -> list[sqlite3.Row]:
        rows = self._conn.execute("SELECT * FROM memos ORDER BY created_at DESC").fetchall()
        related: list[sqlite3.Row] = []
        for row in rows:
            payload = json.loads(row["payload_json"])
            run_ids = list(payload.get("source_run_ids") or []) + list(
                payload.get("referenced_diff_ids") or []
            )
            signal_ids = list(payload.get("source_signal_ids") or [])
            if run_id and run_id in run_ids:
                related.append(row)
                continue
            if signal_id and signal_id in signal_ids:
                related.append(row)
        return related

    def _build_provenance_chain(
        self,
        *,
        record_type: str,
        record_id: str,
        payload: dict,
    ) -> dict[str, Any]:
        chain: dict[str, Any] = {
            "source_url": None,
            "raw_document": None,
            "extraction_result": None,
            "structured_signal": None,
            "event": None,
            "valuation_diff": None,
            "review_decisions": [],
            "memos": [],
        }

        event_id: Optional[str] = None
        signal_id: Optional[str] = None
        extraction_id: Optional[str] = None
        raw_document_id: Optional[str] = None
        run_id: Optional[str] = None

        if record_type == "raw_documents":
            raw_document_id = record_id
        elif record_type == "extraction_results":
            extraction_id = record_id
            raw_document_id = payload.get("raw_document_id") or payload.get("document_id")
        elif record_type == "structured_signals":
            signal_id = record_id
            extraction_id = payload.get("extraction_result_id")
            event_id = payload.get("event_id")
        elif record_type == "events":
            event_id = record_id
            row = self._fetch_row("events", record_id)
            signal_id = row["signal_id"]
            chain["source_url"] = payload.get("source_url")
        elif record_type == "valuation_diffs":
            run_id = record_id
            event_id = payload.get("event_id")
            chain["valuation_diff"] = self._node("valuation_diffs", record_id)
        elif record_type == "review_decisions":
            run_id = payload.get("run_id")
        elif record_type == "memos":
            source_runs = list(payload.get("source_run_ids") or []) + list(
                payload.get("referenced_diff_ids") or []
            )
            source_signals = payload.get("source_signal_ids") or []
            run_id = source_runs[0] if source_runs else None
            signal_id = source_signals[0] if source_signals else None
        elif record_type == "dossiers":
            recent_events = payload.get("recent_events") or []
            if recent_events:
                event_id = recent_events[0].get("id")
        elif record_type == "literature_reviews":
            cited_raw_documents = payload.get("cited_raw_document_ids") or []
            cited_signals = payload.get("cited_signal_ids") or []
            raw_document_id = cited_raw_documents[0] if cited_raw_documents else None
            signal_id = cited_signals[0] if cited_signals else None
        elif record_type == "competitive_landscapes":
            cited_signals = payload.get("cited_signal_ids") or []
            signal_id = cited_signals[0] if cited_signals else None
        elif record_type == "research_reports":
            cited_raw_documents = payload.get("cited_raw_document_ids") or []
            cited_signals = payload.get("cited_signal_ids") or []
            cited_runs = payload.get("cited_run_ids") or []
            cited_events = payload.get("cited_event_ids") or []
            raw_document_id = cited_raw_documents[0] if cited_raw_documents else None
            signal_id = cited_signals[0] if cited_signals else None
            run_id = cited_runs[0] if cited_runs else None
            event_id = cited_events[0] if cited_events else event_id

        if run_id and chain["valuation_diff"] is None:
            vrow = self._conn.execute(
                "SELECT * FROM valuation_diffs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if vrow is not None:
                chain["valuation_diff"] = self._node("valuation_diffs", run_id)
                vpayload = json.loads(vrow["payload_json"])
                event_id = event_id or vpayload.get("event_id")

        if event_id:
            erow = self._conn.execute(
                "SELECT * FROM events WHERE id = ?",
                (event_id,),
            ).fetchone()
            if erow is not None:
                chain["event"] = self._node("events", event_id)
                epayload = json.loads(erow["payload_json"])
                chain["source_url"] = chain["source_url"] or epayload.get("source_url")
                signal_id = signal_id or erow["signal_id"]

                if chain["valuation_diff"] is None:
                    vrow = self._valuation_diff_for_event(event_id)
                    if vrow is not None:
                        chain["valuation_diff"] = self._node("valuation_diffs", vrow["run_id"])
                        run_id = run_id or vrow["run_id"]

        if signal_id is None and event_id:
            srow = self._latest_signal_for_event(event_id, preferred_signal_id=None)
            if srow is not None:
                signal_id = srow["id"]

        if signal_id:
            srow = self._conn.execute(
                "SELECT * FROM structured_signals WHERE id = ?",
                (signal_id,),
            ).fetchone()
            if srow is not None:
                chain["structured_signal"] = self._node("structured_signals", signal_id)
                extraction_id = extraction_id or srow["extraction_result_id"]
                event_id = event_id or srow["event_id"]

        if extraction_id:
            xrow = self._conn.execute(
                "SELECT * FROM extraction_results WHERE id = ?",
                (extraction_id,),
            ).fetchone()
            if xrow is not None:
                chain["extraction_result"] = self._node("extraction_results", extraction_id)
                raw_document_id = raw_document_id or xrow["raw_document_id"]

        if raw_document_id:
            rrow = self._conn.execute(
                "SELECT * FROM raw_documents WHERE id = ?",
                (raw_document_id,),
            ).fetchone()
            if rrow is not None:
                chain["raw_document"] = self._node("raw_documents", raw_document_id)
                rpayload = json.loads(rrow["payload_json"])
                chain["source_url"] = rpayload.get("source_url") or chain["source_url"]

        if run_id is None and chain["valuation_diff"] is not None:
            run_id = chain["valuation_diff"]["record_id"]

        if run_id:
            chain["review_decisions"] = [
                self._node("review_decisions", row["id"])
                for row in self._review_rows_for_run(run_id)
            ]

        memo_rows = self._memo_rows_related(run_id=run_id, signal_id=signal_id)
        chain["memos"] = [self._node("memos", row["id"]) for row in memo_rows]

        return chain

    def get_record_with_trace(self, record_type: str, record_id: str) -> RecordWithTrace:
        """
        Retrieve one persisted row with payload, trace, and provenance chain.

        record_type:
          raw_documents | extraction_results | structured_signals | events |
          valuation_diffs | review_decisions | memos | dossiers |
          literature_reviews | competitive_landscapes | research_reports
        """
        table_map = self._table_map()
        if record_type not in table_map:
            raise ValueError(
                f"Unknown record_type={record_type!r}; expected one of {sorted(table_map)}"
            )

        table, pk = table_map[record_type]
        row = self._conn.execute(
            f"SELECT payload_json, source_trace_json FROM {table} WHERE {pk} = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"No record found for {record_type}:{record_id}")

        payload = json.loads(row["payload_json"])
        source_trace = SourceTrace.model_validate_json(row["source_trace_json"])
        provenance_chain = self._build_provenance_chain(
            record_type=record_type,
            record_id=record_id,
            payload=payload,
        )
        return RecordWithTrace(
            record_type=record_type,
            record_id=record_id,
            payload=payload,
            source_trace=source_trace,
            provenance_chain=provenance_chain,
        )

    # ------------------------------------------------------------------
    # Knowledge graph (2A)
    # ------------------------------------------------------------------

    @staticmethod
    def _node_from_row(row: sqlite3.Row) -> KGNode:
        return KGNode(
            node_id=row["node_id"],
            node_type=NodeType(row["node_type"]),
            name=row["name"],
            external_id=row["external_id"],
            properties=json.loads(row["properties_json"] or "{}"),
            created_at=KnowledgeStore._coerce_datetime(row["created_at"]),
        )

    @staticmethod
    def _edge_from_row(row: sqlite3.Row) -> KGEdge:
        return KGEdge(
            edge_id=row["edge_id"],
            source_node_id=row["source_node_id"],
            target_node_id=row["target_node_id"],
            edge_type=EdgeType(row["edge_type"]),
            confidence=row["confidence"],
            source_signal_id=row["source_signal_id"],
            properties=json.loads(row["properties_json"] or "{}"),
            created_at=KnowledgeStore._coerce_datetime(row["created_at"]),
        )

    def add_node(self, node: KGNode) -> KGNode:
        """Insert node; silently skip if node_id already exists."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT OR IGNORE INTO kg_nodes
                (node_id, node_type, name, external_id, properties_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                node.node_id,
                node.node_type.value,
                node.name,
                node.external_id,
                json.dumps(node.properties),
                node.created_at.isoformat(),
                now,
            ),
        )
        self._conn.commit()
        return node

    def upsert_node(self, node: KGNode) -> KGNode:
        """Insert or update node, refreshing name, properties, and updated_at."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT INTO kg_nodes
                (node_id, node_type, name, external_id, properties_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
                name = excluded.name,
                external_id = excluded.external_id,
                properties_json = excluded.properties_json,
                updated_at = excluded.updated_at
            """,
            (
                node.node_id,
                node.node_type.value,
                node.name,
                node.external_id,
                json.dumps(node.properties),
                node.created_at.isoformat(),
                now,
            ),
        )
        self._conn.commit()
        return node

    def get_node(self, node_id: str) -> Optional[KGNode]:
        row = self._conn.execute("SELECT * FROM kg_nodes WHERE node_id = ?", (node_id,)).fetchone()
        return self._node_from_row(row) if row else None

    def find_by_type(self, node_type: NodeType) -> list[KGNode]:
        rows = self._conn.execute(
            "SELECT * FROM kg_nodes WHERE node_type = ? ORDER BY name",
            (node_type.value,),
        ).fetchall()
        return [self._node_from_row(r) for r in rows]

    def add_edge(self, edge: KGEdge) -> KGEdge:
        """Insert edge; replace on (source, target, edge_type) conflict."""
        self._conn.execute(
            """
            INSERT INTO kg_edges
                (edge_id, source_node_id, target_node_id, edge_type,
                 confidence, source_signal_id, properties_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_node_id, target_node_id, edge_type) DO UPDATE SET
                confidence = excluded.confidence,
                source_signal_id = excluded.source_signal_id,
                properties_json = excluded.properties_json
            """,
            (
                edge.edge_id,
                edge.source_node_id,
                edge.target_node_id,
                edge.edge_type.value,
                edge.confidence,
                edge.source_signal_id,
                json.dumps(edge.properties),
                edge.created_at.isoformat(),
            ),
        )
        self._conn.commit()
        return edge

    def neighbors(
        self,
        node_id: str,
        edge_type: Optional[EdgeType] = None,
    ) -> list[KGNode]:
        """Return all nodes connected to node_id (undirected), optionally filtered by edge_type."""
        if edge_type:
            rows = self._conn.execute(
                """
                SELECT n.* FROM kg_nodes n
                JOIN kg_edges e ON n.node_id = e.target_node_id
                WHERE e.source_node_id = ? AND e.edge_type = ?
                UNION
                SELECT n.* FROM kg_nodes n
                JOIN kg_edges e ON n.node_id = e.source_node_id
                WHERE e.target_node_id = ? AND e.edge_type = ?
                """,
                (node_id, edge_type.value, node_id, edge_type.value),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT n.* FROM kg_nodes n
                JOIN kg_edges e ON n.node_id = e.target_node_id
                WHERE e.source_node_id = ?
                UNION
                SELECT n.* FROM kg_nodes n
                JOIN kg_edges e ON n.node_id = e.source_node_id
                WHERE e.target_node_id = ?
                """,
                (node_id, node_id),
            ).fetchall()
        return [self._node_from_row(r) for r in rows]

    def get_subgraph(self, node_id: str, depth: int = 2) -> dict[str, list]:
        """BFS to `depth`. Returns {"nodes": [KGNode], "edges": [KGEdge]}."""
        visited_nodes: dict[str, KGNode] = {}
        visited_edges: dict[str, KGEdge] = {}
        frontier = {node_id}

        root = self.get_node(node_id)
        if root:
            visited_nodes[node_id] = root

        for _ in range(depth):
            next_frontier: set[str] = set()
            for nid in frontier:
                edge_rows = self._conn.execute(
                    "SELECT * FROM kg_edges WHERE source_node_id = ? OR target_node_id = ?",
                    (nid, nid),
                ).fetchall()
                for er in edge_rows:
                    edge = self._edge_from_row(er)
                    visited_edges[edge.edge_id] = edge
                    for other_id in (edge.source_node_id, edge.target_node_id):
                        if other_id not in visited_nodes:
                            node = self.get_node(other_id)
                            if node:
                                visited_nodes[other_id] = node
                                next_frontier.add(other_id)
            frontier = next_frontier

        return {"nodes": list(visited_nodes.values()), "edges": list(visited_edges.values())}

    def find_competing_assets(self, asset_node_id: str) -> list[KGNode]:
        """Return all nodes connected via competes_with edges (undirected)."""
        return self.neighbors(asset_node_id, edge_type=EdgeType.COMPETES_WITH)

    def find_node_by_external_id(self, node_type: NodeType, external_id: str) -> Optional[KGNode]:
        """
        Look up a node by (node_type, external_id).

        Used to merge competitor program nodes across assets: the same NCT
        trial should map to exactly one KG node regardless of which asset
        triggered its discovery.
        """
        row = self._conn.execute(
            "SELECT * FROM kg_nodes WHERE node_type = ? AND external_id = ?",
            (node_type.value, external_id),
        ).fetchone()
        return self._node_from_row(row) if row else None

    # ------------------------------------------------------------------
    # Competitor programs (2B)
    # ------------------------------------------------------------------

    def add_competitor_program(self, program: Any) -> None:
        """
        Persist a CompetitorProgram.  Silently skips if (asset_id, nct_id) exists.

        ``program`` is typed as Any to avoid a circular import with
        competitor_discovery.py.  Callers pass a CompetitorProgram instance.
        """
        self._conn.execute(
            """
            INSERT OR IGNORE INTO competitor_programs
                (program_id, asset_id, company, drug_name, nct_id, phase,
                 status, primary_endpoint_type, indication, discovered_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                program.program_id,
                program.asset_id,
                program.company,
                program.drug_name,
                program.nct_id,
                program.phase,
                program.status,
                program.primary_endpoint_type,
                program.indication,
                program.discovered_at.isoformat(),
            ),
        )
        self._conn.commit()

    def get_competitor_programs(self, asset_id: str) -> list[dict]:
        """Return all competitor programs discovered for *asset_id* as plain dicts."""
        rows = self._conn.execute(
            "SELECT * FROM competitor_programs WHERE asset_id = ? ORDER BY discovered_at",
            (asset_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Event impact scores (3A)
    # ------------------------------------------------------------------

    def upsert_event_score(self, score: Any) -> None:
        """
        Insert or replace an EventImpactScore.

        ``score`` is typed as Any to avoid a circular import with
        event_impact_ledger.py.  Callers pass an EventImpactScore instance.
        Conflicts on (event_type, trial_phase, endpoint_type) overwrite.

        Note: SQLite UNIQUE treats each NULL as distinct, so trial_phase and
        endpoint_type are stored as '' (empty string) when None to ensure the
        ON CONFLICT clause fires correctly on re-runs.
        """
        self._conn.execute(
            """
            INSERT INTO event_scores
                (score_id, event_type, trial_phase, endpoint_type,
                 observation_count, mean_return_t30, mean_return_t180,
                 active, half_life_days, computed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_type, trial_phase, endpoint_type) DO UPDATE SET
                score_id            = excluded.score_id,
                observation_count   = excluded.observation_count,
                mean_return_t30     = excluded.mean_return_t30,
                mean_return_t180    = excluded.mean_return_t180,
                active              = excluded.active,
                half_life_days      = excluded.half_life_days,
                computed_at         = excluded.computed_at
            """,
            (
                score.score_id,
                score.category.event_type,
                score.category.trial_phase or "",
                score.category.endpoint_type or "",
                score.observation_count,
                score.mean_return_t30,
                score.mean_return_t180,
                int(score.active),
                score.half_life_days,
                score.computed_at.isoformat(),
            ),
        )
        self._conn.commit()

    @staticmethod
    def _deserialize_event_score_row(row: dict) -> dict:
        """Convert empty-string sentinels back to None for caller convenience."""
        row = dict(row)
        if row.get("trial_phase") == "":
            row["trial_phase"] = None
        if row.get("endpoint_type") == "":
            row["endpoint_type"] = None
        return row

    def get_event_score(
        self,
        event_type: str,
        trial_phase: Optional[str] = None,
        endpoint_type: Optional[str] = None,
    ) -> Optional[dict]:
        """Return one event score as a plain dict, or None if not found."""
        row = self._conn.execute(
            """
            SELECT * FROM event_scores
            WHERE event_type = ?
              AND trial_phase = ?
              AND endpoint_type = ?
            """,
            (event_type, trial_phase or "", endpoint_type or ""),
        ).fetchone()
        return self._deserialize_event_score_row(row) if row else None

    def list_event_scores(self, active_only: bool = False) -> list[dict]:
        """Return all stored event scores as plain dicts."""
        if active_only:
            rows = self._conn.execute(
                "SELECT * FROM event_scores WHERE active = 1 ORDER BY event_type"
            ).fetchall()
        else:
            rows = self._conn.execute("SELECT * FROM event_scores ORDER BY event_type").fetchall()
        return [self._deserialize_event_score_row(r) for r in rows]

    # ------------------------------------------------------------------
    # Forecast records (3B)
    # ------------------------------------------------------------------

    def record_forecast(self, forecast: Any) -> None:
        """
        Insert a ForecastRecord.

        ``forecast`` is typed as Any to avoid circular import with
        forecast_tracker.py.  Callers pass a ForecastRecord instance.
        UNIQUE(signal_id) — a second call for the same signal_id is ignored.
        """
        self._conn.execute(
            """
            INSERT OR IGNORE INTO forecast_records
                (forecast_id, signal_id, event_id, asset_id, event_type,
                 signal_date, extraction_confidence, predicted_direction,
                 predicted_delta_pct, horizon_days, predicted_at, created_at,
                 trial_phase, indication, endpoint_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                forecast.forecast_id,
                forecast.signal_id,
                forecast.event_id,
                forecast.asset_id,
                forecast.event_type,
                forecast.signal_date,
                forecast.extraction_confidence,
                forecast.predicted_direction,
                forecast.predicted_delta_pct,
                forecast.horizon_days,
                forecast.predicted_at.isoformat(),
                forecast.created_at.isoformat(),
                getattr(forecast, "trial_phase", None),
                getattr(forecast, "indication", None),
                getattr(forecast, "endpoint_type", None),
            ),
        )
        self._conn.commit()

    def get_forecast(self, forecast_id: str) -> Optional[dict]:
        """Return one forecast_record as a plain dict, or None."""
        row = self._conn.execute(
            "SELECT * FROM forecast_records WHERE forecast_id = ?",
            (forecast_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_forecast_by_signal(self, signal_id: str) -> Optional[dict]:
        """Return the forecast for a given signal_id, or None."""
        row = self._conn.execute(
            "SELECT * FROM forecast_records WHERE signal_id = ?",
            (signal_id,),
        ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Outcome override log (Wave 0.5)
    # ------------------------------------------------------------------

    def write_outcome_override(
        self,
        event_id: str,
        corrected_label: str,
        *,
        original_label: Optional[str] = None,
        reason: Optional[str] = None,
        operator_id: Optional[str] = None,
    ) -> None:
        """
        Record a manual correction to an event_outcome label.

        Also updates ``event_outcomes.outcome_label`` and sets
        ``outcome_resolution_source = 'manual_override'`` so the learning
        loop uses the corrected truth.

        Parameters
        ----------
        event_id:
            The event_id of the row in event_outcomes to correct.
        corrected_label:
            The verified label: ``"trial_success"``, ``"trial_failure"``,
            ``"ambiguous"``, or ``"market_reaction_only"``.
        original_label:
            Previous label (for audit trail).  If None, the current DB value
            is read automatically.
        reason:
            Free-text explanation for the correction.
        operator_id:
            Reviewer / system actor ID for traceability.
        """
        now = datetime.now(timezone.utc).isoformat()

        if original_label is None:
            row = self._conn.execute(
                "SELECT outcome_label FROM event_outcomes WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            original_label = dict(row).get("outcome_label") if row else None

        self._conn.execute(
            """
            INSERT INTO outcome_override_log
                (override_id, event_id, original_label, corrected_label,
                 reason, operator_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(__import__("uuid").uuid4()),
                event_id,
                original_label,
                corrected_label,
                reason,
                operator_id,
                now,
            ),
        )
        # Update the live outcome row so downstream queries see the correction.
        self._conn.execute(
            """
            UPDATE event_outcomes
               SET outcome_label             = ?,
                   outcome_resolution_source = 'manual_override'
             WHERE event_id = ?
            """,
            (corrected_label, event_id),
        )
        self._conn.commit()

    def get_outcome_overrides(self, event_id: Optional[str] = None) -> list[dict]:
        """
        Return override log entries, optionally filtered by event_id.
        """
        if event_id:
            rows = self._conn.execute(
                "SELECT * FROM outcome_override_log WHERE event_id = ? ORDER BY created_at",
                (event_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM outcome_override_log ORDER BY created_at"
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Cross-asset propagation proposals (Wave D)
    # ------------------------------------------------------------------

    def store_propagation_proposals(
        self,
        proposals: list,
        *,
        source_asset_id: str,
    ) -> int:
        """
        Persist a list of GeneratedPropagationProposal objects.

        Returns the number of rows inserted (duplicates by proposal_id are ignored).
        """
        now = datetime.now(timezone.utc).isoformat()
        inserted = 0
        for p in proposals:
            proposal_json = self._json_dump(p.proposal.model_dump(mode="json"))
            self._conn.execute(
                """
                INSERT OR IGNORE INTO propagation_proposals
                    (proposal_id, source_asset_id, target_asset_id,
                     propagation_type, calibration_confidence, sample_size,
                     proposal_json, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    p.proposal.id,
                    source_asset_id,
                    p.target_asset_id,
                    str(p.propagation_type.value
                        if hasattr(p.propagation_type, "value")
                        else p.propagation_type),
                    float(p.calibration_confidence),
                    int(p.sample_size),
                    proposal_json,
                    now,
                ),
            )
            inserted += self._conn.execute(
                "SELECT changes()"
            ).fetchone()[0]
        self._conn.commit()
        return inserted

    def get_pending_propagation_proposals(
        self,
        target_asset_ids: Optional[list[str]] = None,
        *,
        limit: int = 200,
    ) -> list[dict]:
        """
        Return pending propagation proposals, optionally filtered by target.

        Parameters
        ----------
        target_asset_ids:
            When provided, only returns proposals targeting these assets.
        limit:
            Maximum rows to return (default 200).
        """
        if target_asset_ids is not None:
            placeholders = ", ".join("?" for _ in target_asset_ids)
            rows = self._conn.execute(
                f"""
                SELECT * FROM propagation_proposals
                 WHERE status = 'pending'
                   AND target_asset_id IN ({placeholders})
                 ORDER BY created_at DESC
                 LIMIT ?
                """,
                (*target_asset_ids, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM propagation_proposals
                 WHERE status = 'pending'
                 ORDER BY created_at DESC
                 LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Enrollment snapshots (Wave 3)
    # ------------------------------------------------------------------

    def write_enrollment_snapshot(self, snapshot: "EnrollmentSnapshot") -> None:
        """
        Upsert an enrollment snapshot row.

        ``UNIQUE(nct_id, snapshot_date)`` ensures idempotency — re-extracting
        the same trial on the same day replaces the prior row.
        """
        now = datetime.now(timezone.utc).isoformat()
        payload = snapshot.model_dump(mode="json")
        self._conn.execute(
            """
            INSERT OR REPLACE INTO enrollment_snapshots
                (id, nct_id, asset_id, snapshot_date, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.id,
                snapshot.nct_id,
                snapshot.asset_id,
                snapshot.snapshot_date.isoformat(),
                json.dumps(payload),
                now,
            ),
        )
        self._conn.commit()

    def get_prior_enrollment_snapshot(
        self, nct_id: str, before_date: Optional[date] = None
    ) -> Optional["EnrollmentSnapshot"]:
        """
        Return the most recent enrollment snapshot for *nct_id* strictly before
        *before_date* (or the latest overall when *before_date* is None).
        """
        from bve.intelligence.enrollment_snapshot_extractor import EnrollmentSnapshot as ES
        if before_date is not None:
            row = self._conn.execute(
                """
                SELECT payload_json FROM enrollment_snapshots
                 WHERE nct_id = ? AND snapshot_date < ?
                 ORDER BY snapshot_date DESC LIMIT 1
                """,
                (nct_id, before_date.isoformat()),
            ).fetchone()
        else:
            row = self._conn.execute(
                """
                SELECT payload_json FROM enrollment_snapshots
                 WHERE nct_id = ?
                 ORDER BY snapshot_date DESC LIMIT 1
                """,
                (nct_id,),
            ).fetchone()
        if row is None:
            return None
        try:
            return ES.model_validate(json.loads(row[0]))
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Catalyst events (Wave 1)
    # ------------------------------------------------------------------

    def upsert_catalyst_event(self, event: "CatalystEvent") -> None:
        """
        Insert or replace a catalyst event row.

        On conflict (same primary key id) the full row is replaced so that EV
        fields computed by CatalystEVCalculator are persisted in-place.
        """
        now = datetime.now(timezone.utc).isoformat()
        payload = event.model_dump(mode="json")
        self._conn.execute(
            """
            INSERT OR REPLACE INTO catalyst_events
                (id, asset_id, company_id, catalyst_type, expected_date,
                 date_confidence, source, description, payload_json,
                 is_active, resolved, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                event.asset_id,
                event.company_id,
                event.catalyst_type.value,
                event.expected_date.isoformat(),
                event.date_confidence,
                event.source,
                event.description,
                json.dumps(payload),
                1 if event.is_active else 0,
                1 if event.resolved else 0,
                event.created_at.isoformat(),
                now,
            ),
        )
        self._conn.commit()

    def get_catalyst_events(
        self,
        *,
        asset_id: Optional[str] = None,
        active_only: bool = True,
        days_ahead: Optional[int] = None,
    ) -> "list[CatalystEvent]":
        """
        Return catalyst events ordered by expected_date ascending.

        Parameters
        ----------
        asset_id:
            Filter to a specific asset; None returns all assets.
        active_only:
            When True (default), only return rows where is_active=1.
        days_ahead:
            When set, only return events whose expected_date is within
            today + days_ahead.
        """
        from bve.intelligence.catalyst_calendar import CatalystEvent as CE
        clauses: list[str] = []
        params: list = []

        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        if active_only:
            clauses.append("is_active = 1")
        if days_ahead is not None:
            cutoff = (datetime.now(timezone.utc).date() + __import__("datetime").timedelta(days=days_ahead)).isoformat()
            clauses.append("expected_date <= ?")
            params.append(cutoff)

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._conn.execute(
            f"SELECT payload_json FROM catalyst_events {where} ORDER BY expected_date ASC",
            params,
        ).fetchall()

        events: list[CE] = []
        for row in rows:
            try:
                events.append(CE.model_validate(json.loads(row[0])))
            except Exception:
                continue
        return events

    def resolve_catalyst_event(
        self,
        event_id: str,
        outcome: "Literal['positive', 'negative', 'partial']",
    ) -> bool:
        """
        Mark a catalyst event as resolved with the given outcome.

        Returns True when a row was updated, False when event_id not found.
        """
        from bve.intelligence.catalyst_calendar import CatalystEvent as CE
        row = self._conn.execute(
            "SELECT payload_json FROM catalyst_events WHERE id = ?",
            (event_id,),
        ).fetchone()
        if row is None:
            return False

        try:
            ev = CE.model_validate(json.loads(row[0]))
        except Exception:
            return False

        updated = ev.model_copy(update={
            "resolved": True,
            "is_active": False,
            "actual_outcome": outcome,
            "updated_at": datetime.now(timezone.utc),
        })
        self.upsert_catalyst_event(updated)
        return True

    # ------------------------------------------------------------------
    # Paper tracking log
    # ------------------------------------------------------------------

    def write_paper_tracking_entry(
        self,
        entry_id: str,
        snapshot_date: "date",
        asset_id: str,
        recommendation: str,
        *,
        ticker: Optional[str] = None,
        composite_score: Optional[float] = None,
        mna_likelihood: Optional[float] = None,
        predicted_acquirer: Optional[str] = None,
        catalyst: Optional[str] = None,
        thesis: Optional[str] = None,
        risk_flags: Optional[list] = None,
        watchlist_type: Optional[str] = None,
        calibrated_score: Optional[float] = None,
        calibrated_score_label: Optional[str] = None,
        transaction_driver_count: Optional[int] = None,
        gate_reason_codes: Optional[list] = None,
        top5_acquirers: Optional[list] = None,
    ) -> None:
        """Upsert a single paper tracking snapshot row.

        Replaces any existing entry for (snapshot_date, asset_id).
        """
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO paper_tracking_log(
                entry_id, snapshot_date, asset_id, ticker, recommendation,
                composite_score, mna_likelihood, predicted_acquirer,
                catalyst, thesis, risk_flags, created_at,
                watchlist_type, calibrated_score, calibrated_score_label,
                transaction_driver_count, gate_reason_codes, top5_acquirers
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry_id,
                snapshot_date.isoformat() if hasattr(snapshot_date, "isoformat") else str(snapshot_date),
                asset_id,
                ticker,
                recommendation,
                composite_score,
                mna_likelihood,
                predicted_acquirer,
                catalyst,
                thesis,
                json.dumps(risk_flags) if risk_flags is not None else None,
                now,
                watchlist_type,
                calibrated_score,
                calibrated_score_label,
                transaction_driver_count,
                json.dumps(gate_reason_codes) if gate_reason_codes is not None else None,
                json.dumps(top5_acquirers) if top5_acquirers is not None else None,
            ),
        )
        self._conn.commit()

    def get_paper_tracking_entries(
        self,
        *,
        since: Optional["date"] = None,
        asset_id: Optional[str] = None,
        limit: int = 200,
    ) -> list[dict]:
        """Return paper tracking entries ordered by (snapshot_date DESC, asset_id).

        Parameters
        ----------
        since:
            If provided, only return entries with snapshot_date >= since.
        asset_id:
            If provided, filter to a single asset.
        limit:
            Maximum number of rows to return.
        """
        clauses: list[str] = []
        params: list = []
        if since is not None:
            clauses.append("snapshot_date >= ?")
            params.append(since.isoformat() if hasattr(since, "isoformat") else str(since))
        if asset_id is not None:
            clauses.append("asset_id = ?")
            params.append(asset_id)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        rows = self._conn.execute(
            f"SELECT * FROM paper_tracking_log {where} "
            f"ORDER BY snapshot_date DESC, asset_id ASC LIMIT ?",
            params,
        ).fetchall()
        return [dict(row) for row in rows]
