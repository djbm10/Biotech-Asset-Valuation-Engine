"""SQLAlchemy ORM models for the BVE platform.

Schema mirrors the blueprint data model (section 7).  All tables use UUID
primary keys stored as TEXT (portable across SQLite and PostgreSQL).
JSON columns use JSON type (TEXT on SQLite, JSONB on PostgreSQL via dialect).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bve.persistence.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# companies
# ---------------------------------------------------------------------------

class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    ticker: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    company_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # public_biotech | big_pharma | private_biotech
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    enterprise_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    cash: Mapped[float | None] = mapped_column(Float, nullable=True)
    debt: Mapped[float | None] = mapped_column(Float, nullable=True)
    shares_outstanding: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    # Relationships
    assets: Mapped[list[Asset]] = relationship("Asset", back_populates="company")
    acquirer_profile: Mapped[AcquirerProfile | None] = relationship(
        "AcquirerProfile", back_populates="company", uselist=False
    )
    market_snapshots: Mapped[list[MarketSnapshot]] = relationship(
        "MarketSnapshot", back_populates="company"
    )
    financing_forecasts: Mapped[list[FinancingForecast]] = relationship(
        "FinancingForecast", back_populates="company"
    )

    __table_args__ = (
        Index("ix_companies_name", "name"),
    )


# ---------------------------------------------------------------------------
# assets
# ---------------------------------------------------------------------------

class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    modality: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mechanism: Mapped[str | None] = mapped_column(String(255), nullable=True)
    therapeutic_area: Mapped[str | None] = mapped_column(String(100), nullable=True)
    indication: Mapped[str | None] = mapped_column(String(255), nullable=True)
    current_phase: Mapped[str | None] = mapped_column(String(50), nullable=True)
    partnered: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    company: Mapped[Company] = relationship("Company", back_populates="assets")
    trials: Mapped[list[Trial]] = relationship("Trial", back_populates="asset")
    catalysts: Mapped[list[Catalyst]] = relationship("Catalyst", back_populates="asset")
    dossier: Mapped[AssetDossierRecord | None] = relationship(
        "AssetDossierRecord", back_populates="asset", uselist=False
    )
    implied_expectations: Mapped[list[ImpliedExpectation]] = relationship(
        "ImpliedExpectation", back_populates="asset"
    )
    variant_theses: Mapped[list[VariantThesis]] = relationship(
        "VariantThesis", back_populates="asset"
    )
    scenario_trees: Mapped[list[ScenarioTree]] = relationship(
        "ScenarioTree", back_populates="asset"
    )
    decision_records: Mapped[list[DecisionRecord]] = relationship(
        "DecisionRecord", back_populates="asset"
    )
    competition_edges_as_source: Mapped[list[CompetitionEdge]] = relationship(
        "CompetitionEdge", foreign_keys="CompetitionEdge.source_asset_id", back_populates="source_asset"
    )
    competition_edges_as_target: Mapped[list[CompetitionEdge]] = relationship(
        "CompetitionEdge", foreign_keys="CompetitionEdge.target_asset_id", back_populates="target_asset"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "name", "indication", name="uq_asset_company_name_indication"),
    )


# ---------------------------------------------------------------------------
# trials
# ---------------------------------------------------------------------------

class Trial(Base):
    __tablename__ = "trials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assets.id"), nullable=False
    )
    nct_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    phase: Mapped[str | None] = mapped_column(String(20), nullable=True)
    endpoint_primary: Mapped[str | None] = mapped_column(Text, nullable=True)
    endpoint_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    enrollment_target: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_of_therapy: Mapped[str | None] = mapped_column(String(50), nullable=True)
    biomarker_strategy: Mapped[str | None] = mapped_column(String(255), nullable=True)
    start_date: Mapped[str | None] = mapped_column(String(20), nullable=True)  # ISO date
    estimated_completion_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    asset: Mapped[Asset] = relationship("Asset", back_populates="trials")


# ---------------------------------------------------------------------------
# catalysts
# ---------------------------------------------------------------------------

class Catalyst(Base):
    __tablename__ = "catalysts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assets.id"), nullable=False
    )
    catalyst_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expected_date: Mapped[str | None] = mapped_column(String(20), nullable=True)  # ISO date
    status: Mapped[str] = mapped_column(String(50), default="pending")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("evidence_items.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    asset: Mapped[Asset] = relationship("Asset", back_populates="catalysts")
    scenario_trees: Mapped[list[ScenarioTree]] = relationship(
        "ScenarioTree", back_populates="catalyst"
    )

    __table_args__ = (
        Index("ix_catalysts_asset_date", "asset_id", "expected_date"),
    )


# ---------------------------------------------------------------------------
# asset_dossiers
# ---------------------------------------------------------------------------

class AssetDossierRecord(Base):
    __tablename__ = "asset_dossiers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assets.id"), unique=True, nullable=False
    )
    jsonb_state: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    completeness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    asset: Mapped[Asset] = relationship("Asset", back_populates="dossier")


# ---------------------------------------------------------------------------
# acquirer_profiles
# ---------------------------------------------------------------------------

class AcquirerProfile(Base):
    __tablename__ = "acquirer_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id"), unique=True, nullable=False
    )
    strategic_areas: Mapped[list | None] = mapped_column(JSON, nullable=True)
    pipeline_gaps: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    loe_cliffs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    bd_preferences: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    cash_firepower: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    company: Mapped[Company] = relationship("Company", back_populates="acquirer_profile")


# ---------------------------------------------------------------------------
# evidence_items
# ---------------------------------------------------------------------------

class EvidenceItem(Base):
    __tablename__ = "evidence_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    parsed_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    materiality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    __table_args__ = (
        Index("ix_evidence_checksum", "checksum"),
        Index("ix_evidence_source_type", "source_type"),
    )


# ---------------------------------------------------------------------------
# market_snapshots
# ---------------------------------------------------------------------------

class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id"), nullable=False
    )
    as_of: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_cap: Mapped[float | None] = mapped_column(Float, nullable=True)
    enterprise_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    iv_event_move: Mapped[float | None] = mapped_column(Float, nullable=True)

    company: Mapped[Company] = relationship("Company", back_populates="market_snapshots")
    implied_expectations: Mapped[list[ImpliedExpectation]] = relationship(
        "ImpliedExpectation", back_populates="market_snapshot"
    )

    __table_args__ = (
        UniqueConstraint("company_id", "as_of", name="uq_market_snapshot_company_asof"),
    )


# ---------------------------------------------------------------------------
# implied_expectations
# ---------------------------------------------------------------------------

class ImpliedExpectation(Base):
    __tablename__ = "implied_expectations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assets.id"), nullable=False
    )
    market_snapshot_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("market_snapshots.id"), nullable=False
    )
    implied_pos: Mapped[float | None] = mapped_column(Float, nullable=True)
    implied_peak_sales: Mapped[float | None] = mapped_column(Float, nullable=True)
    valuation_gap_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    solver_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    asset: Mapped[Asset] = relationship("Asset", back_populates="implied_expectations")
    market_snapshot: Mapped[MarketSnapshot] = relationship(
        "MarketSnapshot", back_populates="implied_expectations"
    )

    __table_args__ = (
        UniqueConstraint(
            "asset_id", "market_snapshot_id", name="uq_implied_exp_asset_snapshot"
        ),
    )


# ---------------------------------------------------------------------------
# variant_theses
# ---------------------------------------------------------------------------

class VariantThesis(Base):
    __tablename__ = "variant_theses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assets.id"), nullable=False
    )
    market_view: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model_view: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    delta_view: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    kill_criteria: Mapped[list | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|broken|resolved
    documented: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    asset: Mapped[Asset] = relationship("Asset", back_populates="variant_theses")


# ---------------------------------------------------------------------------
# scenario_trees
# ---------------------------------------------------------------------------

class ScenarioTree(Base):
    __tablename__ = "scenario_trees"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assets.id"), nullable=False
    )
    catalyst_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("catalysts.id"), nullable=True
    )
    tree_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    expected_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    skew_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    setup_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    asset: Mapped[Asset] = relationship("Asset", back_populates="scenario_trees")
    catalyst: Mapped[Catalyst | None] = relationship("Catalyst", back_populates="scenario_trees")


# ---------------------------------------------------------------------------
# financing_forecasts
# ---------------------------------------------------------------------------

class FinancingForecast(Base):
    __tablename__ = "financing_forecasts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id"), nullable=False
    )
    runway_months: Mapped[float | None] = mapped_column(Float, nullable=True)
    pre_catalyst_raise_prob: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_dilution_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    expected_dilution_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    distress_risk: Mapped[float | None] = mapped_column(Float, nullable=True)
    as_of: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_now)

    company: Mapped[Company] = relationship("Company", back_populates="financing_forecasts")


# ---------------------------------------------------------------------------
# competition_edges
# ---------------------------------------------------------------------------

class CompetitionEdge(Base):
    __tablename__ = "competition_edges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assets.id"), nullable=False
    )
    target_asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assets.id"), nullable=False
    )
    edge_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)

    source_asset: Mapped[Asset] = relationship(
        "Asset", foreign_keys=[source_asset_id], back_populates="competition_edges_as_source"
    )
    target_asset: Mapped[Asset] = relationship(
        "Asset", foreign_keys=[target_asset_id], back_populates="competition_edges_as_target"
    )

    __table_args__ = (
        UniqueConstraint(
            "source_asset_id", "target_asset_id", "edge_type",
            name="uq_competition_edge"
        ),
    )


# ---------------------------------------------------------------------------
# acquisition_scores
# ---------------------------------------------------------------------------

class AcquisitionScore(Base):
    __tablename__ = "acquisition_scores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    target_company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id"), nullable=False
    )
    acquirer_company_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("companies.id"), nullable=False
    )
    fit_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    timing_bucket: Mapped[str | None] = mapped_column(String(30), nullable=True)
    affordability_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    strategic_fit_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    pipeline_gap_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    target_company: Mapped[Company] = relationship(
        "Company", foreign_keys=[target_company_id]
    )
    acquirer_company: Mapped[Company] = relationship(
        "Company", foreign_keys=[acquirer_company_id]
    )

    __table_args__ = (
        UniqueConstraint(
            "target_company_id", "acquirer_company_id", name="uq_acquisition_score"
        ),
    )


# ---------------------------------------------------------------------------
# decision_records
# ---------------------------------------------------------------------------

class DecisionRecord(Base):
    __tablename__ = "decision_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    asset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("assets.id"), nullable=False
    )
    decision_type: Mapped[str | None] = mapped_column(String(30), nullable=True)  # trade|mna_target
    recommendation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    parameter_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("parameter_versions.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    asset: Mapped[Asset] = relationship("Asset", back_populates="decision_records")
    outcome: Mapped[OutcomeRecord | None] = relationship(
        "OutcomeRecord", back_populates="decision", uselist=False
    )
    parameter_version: Mapped[ParameterVersion | None] = relationship(
        "ParameterVersion", back_populates="decisions"
    )


# ---------------------------------------------------------------------------
# outcome_records
# ---------------------------------------------------------------------------

class OutcomeRecord(Base):
    __tablename__ = "outcome_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    decision_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("decision_records.id"), unique=True, nullable=False
    )
    realized_outcome: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    decision: Mapped[DecisionRecord] = relationship(
        "DecisionRecord", back_populates="outcome"
    )


# ---------------------------------------------------------------------------
# parameter_versions
# ---------------------------------------------------------------------------

class ParameterVersion(Base):
    __tablename__ = "parameter_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    weights: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    promoted: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    decisions: Mapped[list[DecisionRecord]] = relationship(
        "DecisionRecord", back_populates="parameter_version"
    )
