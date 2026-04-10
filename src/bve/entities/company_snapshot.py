"""
CompanySnapshot — canonical, persisted truth record for company-level analysis.

This is the Phase 1 core object.  It is SEPARATE from:
  - Company (the thin valuation-engine balance-sheet entity)
  - CompanySOTPResult (an ephemeral computation output)

A CompanySnapshot is immutable once written.  State transitions create new
snapshot versions linked via ``provenance.parent_snapshot_id``.

Lifecycle (ReviewerState):
    draft → reviewed → approved ← quarantined ← stale

A name is eligible for capital-candidate actions only when:
    reviewer_state == approved AND pack_version >= 1 AND stale_since is None

See docs/PRODUCT_SPEC.md for the full governance table.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ReviewerState(str, Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    QUARANTINED = "quarantined"
    STALE = "stale"


# ---------------------------------------------------------------------------
# ValueBucket — enriched material bucket with methodology + corroboration
# ---------------------------------------------------------------------------

class ValueBucket(BaseModel, frozen=True):
    """
    One value contribution to a company SOTP.

    Unlike the lighter ``CompanySOTPBucket``, this carries:
    - explicit methodology (how the value was derived)
    - corroboration count and refs (how many independent sources confirmed it)
    - reviewer identity (who approved the bucket)
    - change tracking (when and why the value last changed)
    """

    bucket_id: str
    bucket_type: Literal[
        "modeled_asset",
        "net_cash",
        "platform",
        "unmodeled_pipeline",
        "royalty",
        "dilution_reserve",
    ]
    label: str
    value_millions: float

    methodology: Literal[
        "rnpv",
        "dcf",
        "market_comp",
        "precedent_transaction",
        "rule_of_thumb",
        "analyst_estimate",
        "balance_sheet",
    ]
    source_type: Literal[
        "modeled",
        "sec_filing",
        "contractual",
        "company_disclosure",
        "investor_day",
        "analyst_bridge",
        "inferred",
    ]
    source_ref: str  # e.g. "10-K:2025-12-31:pg42" or "bve-asset:relay_rly2608.yaml:2026-04-01"
    as_of_date: date

    corroboration_count: int = Field(default=0, ge=0)
    corroboration_refs: list[str] = Field(default_factory=list)

    reviewer: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)

    last_changed_at: Optional[datetime] = None
    change_reason: Optional[str] = None

    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# DilutionBridge — explicit dilution modeling
# ---------------------------------------------------------------------------

class DilutionBridge(BaseModel, frozen=True):
    """
    Explicit financing / dilution model replacing the flat burn_rate proxy.

    ``fully_diluted_shares_millions`` accounts for current shares plus all
    known dilutive instruments (warrants, convertibles) plus expected
    future dilution from financing rounds.
    """

    current_shares_millions: float = Field(gt=0.0)
    expected_dilution_pct: float = Field(default=0.0, ge=0.0, le=1.0,
        description="Fraction of current shares expected to be newly issued (financing scenario)")

    financing_runway_quarters: Optional[float] = Field(default=None, ge=0.0,
        description="Quarters of runway at current burn before needing a raise; None = unknown")

    atm_active: bool = False
    atm_remaining_millions: Optional[float] = Field(default=None, ge=0.0,
        description="Remaining capacity on active at-the-market program (USD millions)")

    shelf_registration_millions: Optional[float] = Field(default=None, ge=0.0,
        description="Remaining capacity on active shelf registration (USD millions)")

    warrant_shares_millions: float = Field(default=0.0, ge=0.0,
        description="Outstanding warrant shares (already exercisable or expected to vest)")
    convertible_shares_millions: float = Field(default=0.0, ge=0.0,
        description="Shares underlying convertible notes / preferred stock")

    source_ref: Optional[str] = None
    as_of_date: Optional[date] = None
    notes: Optional[str] = None

    @property
    def fully_diluted_shares_millions(self) -> float:
        """
        Total shares including expected future issuance, warrants, and convertibles.
        Does NOT double-count: expected_dilution_pct is applied to current_shares only.
        """
        future_new = self.current_shares_millions * self.expected_dilution_pct
        return (
            self.current_shares_millions
            + future_new
            + self.warrant_shares_millions
            + self.convertible_shares_millions
        )

    @property
    def dilution_multiple(self) -> float:
        """fully_diluted / current — 1.0 means no dilution."""
        if self.current_shares_millions <= 0:
            return 1.0
        return self.fully_diluted_shares_millions / self.current_shares_millions


# ---------------------------------------------------------------------------
# CatalystEntry
# ---------------------------------------------------------------------------

class CatalystEntry(BaseModel, frozen=True):
    description: str
    expected_date: Optional[str] = None  # ISO date string or fuzzy ("H2 2026")
    catalyst_type: Literal[
        "readout", "fda_action", "partnership", "milestone",
        "financing", "conference", "other"
    ] = "readout"
    probability_positive: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    source_ref: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# ManagementFlag
# ---------------------------------------------------------------------------

class ManagementFlag(BaseModel, frozen=True):
    flag_type: Literal[
        "ceo_change", "cfo_change", "cmo_change",
        "restatement", "sec_investigation", "going_concern",
        "activist_involvement", "insider_selling_cluster",
    ]
    flagged_date: date
    severity: Literal["info", "watch", "warning", "critical"]
    description: str
    source_ref: Optional[str] = None
    resolved: bool = False


# ---------------------------------------------------------------------------
# ConfidenceMetadata
# ---------------------------------------------------------------------------

class ConfidenceMetadata(BaseModel, frozen=True):
    overall_confidence: float = Field(ge=0.0, le=1.0)
    bucket_confidence_min: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    bucket_confidence_avg: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    modeled_asset_coverage_pct: float = Field(default=0.0, ge=0.0, le=1.0,
        description="Fraction of estimated company value that has been explicitly modeled")
    corroboration_score: float = Field(default=0.0, ge=0.0, le=1.0,
        description="Average corroboration_count / 2.0 across material buckets (capped at 1.0)")
    data_age_days_max: Optional[int] = Field(default=None, ge=0,
        description="Oldest material bucket in days since as_of_date")
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# ProvenanceMetadata
# ---------------------------------------------------------------------------

class ProvenanceMetadata(BaseModel, frozen=True):
    pack_version: int = Field(default=0, ge=0,
        description="0 = auto-generated / screening-grade; ≥1 = human-reviewed pack")
    pack_quarter: Optional[str] = None  # "2026Q2"
    created_by: str = "system"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    parent_snapshot_id: Optional[str] = None
    change_summary: Optional[str] = None


# ---------------------------------------------------------------------------
# CompanySnapshot — the canonical truth record
# ---------------------------------------------------------------------------

class CompanySnapshot(BaseModel, frozen=True):
    """
    Immutable, versioned, reviewer-gated company truth record.

    This is the canonical unit of analysis in Mode 2 (Capital Candidate)
    and Mode 3 (Shadow Book).  Screening-grade names use screening configs
    instead; they never have an approved CompanySnapshot.

    Computed properties
    -------------------
    net_cash_millions           cash - debt
    modeled_asset_value_millions  sum of modeled_assets ValueBuckets
    royalty_value_millions        sum of royalty_streams ValueBuckets
    platform_value_millions       platform_value bucket or 0
    unmodeled_pipeline_value_millions  unmodeled_pipeline bucket or 0
    dilution_reserve_millions     equity destruction from dilution bridge
    sotp_equity_value_millions    net_cash + all buckets - dilution
    sotp_discount                 (sotp - market_cap) / market_cap
    all_buckets                   flat list of all ValueBuckets
    is_capital_candidate_eligible gated on approved state + pack_version ≥ 1
    """

    snapshot_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str
    company_name: str
    ticker: str
    as_of_date: date

    # --- Market data (point-in-time) ---
    market_cap_millions: float = Field(ge=0.0)
    enterprise_value_millions: float = Field(default=0.0)  # can be negative when net cash > market cap
    share_price: Optional[float] = Field(default=None, ge=0.0)

    # --- Balance sheet ---
    cash_millions: float = Field(ge=0.0)
    debt_millions: float = Field(default=0.0, ge=0.0)

    # --- Value buckets ---
    modeled_assets: list[ValueBucket] = Field(default_factory=list)
    royalty_streams: list[ValueBucket] = Field(default_factory=list)
    platform_value: Optional[ValueBucket] = None
    unmodeled_pipeline: Optional[ValueBucket] = None

    # --- Bridges ---
    dilution_bridge: Optional[DilutionBridge] = None

    # --- Catalysts and governance flags ---
    catalysts: list[CatalystEntry] = Field(default_factory=list)
    management_flags: list[ManagementFlag] = Field(default_factory=list)

    # --- Metadata ---
    confidence: ConfidenceMetadata
    provenance: ProvenanceMetadata
    reviewer_state: ReviewerState = ReviewerState.DRAFT

    # --- Staleness ---
    stale_since: Optional[date] = None
    stale_reason: Optional[str] = None

    notes: Optional[str] = None

    # -----------------------------------------------------------------------
    # Validators
    # -----------------------------------------------------------------------

    @model_validator(mode="after")
    def _validate_snapshot(self) -> "CompanySnapshot":
        if (
            self.reviewer_state == ReviewerState.APPROVED
            and self.provenance.pack_version < 1
        ):
            raise ValueError(
                "A snapshot cannot be APPROVED with pack_version=0. "
                "Set pack_version >= 1 (requires a human-reviewed pack)."
            )
        if self.stale_since is not None and not self.stale_reason:
            raise ValueError("stale_since requires stale_reason to be set.")
        return self

    # -----------------------------------------------------------------------
    # Computed properties
    # -----------------------------------------------------------------------

    @property
    def net_cash_millions(self) -> float:
        return self.cash_millions - self.debt_millions

    @property
    def modeled_asset_value_millions(self) -> float:
        return sum(b.value_millions for b in self.modeled_assets)

    @property
    def royalty_value_millions(self) -> float:
        return sum(b.value_millions for b in self.royalty_streams)

    @property
    def platform_value_millions(self) -> float:
        return self.platform_value.value_millions if self.platform_value else 0.0

    @property
    def unmodeled_pipeline_value_millions(self) -> float:
        return self.unmodeled_pipeline.value_millions if self.unmodeled_pipeline else 0.0

    @property
    def dilution_reserve_millions(self) -> float:
        """
        Implied equity value destroyed by expected future dilution.

        Uses current price (market_cap / current_shares) × added_shares.
        Returns 0 when no bridge is set or market_cap is zero.
        """
        if self.dilution_bridge is None or self.market_cap_millions <= 0:
            return 0.0
        bridge = self.dilution_bridge
        current = bridge.current_shares_millions
        if current <= 0:
            return 0.0
        price_per_share = self.market_cap_millions / current
        added_shares = bridge.fully_diluted_shares_millions - current
        return max(0.0, added_shares * price_per_share)

    @property
    def sotp_equity_value_millions(self) -> float:
        return (
            self.net_cash_millions
            + self.modeled_asset_value_millions
            + self.platform_value_millions
            + self.unmodeled_pipeline_value_millions
            + self.royalty_value_millions
            - self.dilution_reserve_millions
        )

    @property
    def sotp_discount(self) -> float:
        """(SOTP - market_cap) / market_cap.  Positive = undervalued vs model."""
        if self.market_cap_millions <= 0:
            return 0.0
        return (
            (self.sotp_equity_value_millions - self.market_cap_millions)
            / self.market_cap_millions
        )

    @property
    def all_buckets(self) -> list[ValueBucket]:
        buckets: list[ValueBucket] = list(self.modeled_assets) + list(self.royalty_streams)
        if self.platform_value:
            buckets.append(self.platform_value)
        if self.unmodeled_pipeline:
            buckets.append(self.unmodeled_pipeline)
        return buckets

    @property
    def is_capital_candidate_eligible(self) -> bool:
        """
        True when this snapshot may be used for capital-candidate actions.
        Matches the gate in docs/PRODUCT_SPEC.md:
            reviewer_state == APPROVED AND pack_version >= 1 AND not stale
        """
        return (
            self.reviewer_state == ReviewerState.APPROVED
            and self.provenance.pack_version >= 1
            and self.stale_since is None
        )

    @property
    def critical_management_flags(self) -> list[ManagementFlag]:
        return [f for f in self.management_flags if f.severity == "critical" and not f.resolved]
