"""
Wave I — Thesis Evolution Tracker.

Tracks the evolution of an investment thesis over time as a sequence of
structured, verifiable claims.  Each claim has a defined assertion type,
quantitative or categorical value, and lifecycle (open → confirmed / refuted).

Design principles
-----------------
- Structured claims, not free text: each ThesisClaim has an assertion_type,
  a numeric or categorical value, and explicit criteria for resolution.
- Immutable claim records: claims are never edited in-place.  Revisions are
  new claims with superseded_by pointing back.
- Every claim records the signal_id that created or resolved it, enabling
  full signal-to-thesis traceability.
- No LLM calls.  Claim lifecycle is driven by programmatic rules (resolvers).

Claim types
-----------
  ``pos_above_threshold``    — model PoS > N% by date
  ``market_reaction_positive`` — T+30 return > 0 following event
  ``endpoint_met``           — primary endpoint met (boolean)
  ``competitor_failure``     — named competitor failed phase N
  ``label_expansion``        — FDA expands label to second indication
  ``enrollment_on_track``    — trial enrollment ≥ target by date
  ``regulatory_pathway``     — designated path (e.g. Breakthrough Therapy)

Claim status lifecycle
----------------------
  ``open``      → initial state
  ``confirmed`` → evidence supports the claim
  ``refuted``   → evidence contradicts the claim
  ``expired``   → resolution date passed without evidence (treated as refuted)
  ``superseded``→ replaced by a newer claim (original preserved)

Storage
-------
``thesis_claims`` table created lazily on first ThesisTracker construction.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Claim type and status
# ---------------------------------------------------------------------------

class ClaimType(str, Enum):
    POS_ABOVE_THRESHOLD       = "pos_above_threshold"
    MARKET_REACTION_POSITIVE  = "market_reaction_positive"
    ENDPOINT_MET              = "endpoint_met"
    COMPETITOR_FAILURE        = "competitor_failure"
    LABEL_EXPANSION           = "label_expansion"
    ENROLLMENT_ON_TRACK       = "enrollment_on_track"
    REGULATORY_PATHWAY        = "regulatory_pathway"
    CUSTOM                    = "custom"


ClaimStatus = Literal["open", "confirmed", "refuted", "expired", "superseded"]


# ---------------------------------------------------------------------------
# Default claim weights (Wave M — Weighted Thesis Strength)
# ---------------------------------------------------------------------------

#: Default importance weights per claim type.
#: Higher weight = this claim type has more impact on ``weighted_thesis_strength``.
#: A refuted ENDPOINT_MET (2.0) outweighs two confirmed MARKET_REACTION_POSITIVE (0.5 each).
DEFAULT_CLAIM_WEIGHTS: dict[str, float] = {
    ClaimType.ENDPOINT_MET:            2.0,
    ClaimType.REGULATORY_PATHWAY:      1.5,
    ClaimType.COMPETITOR_FAILURE:      1.5,
    ClaimType.LABEL_EXPANSION:         1.25,
    ClaimType.POS_ABOVE_THRESHOLD:     1.0,
    ClaimType.ENROLLMENT_ON_TRACK:     0.75,
    ClaimType.MARKET_REACTION_POSITIVE: 0.5,
    ClaimType.CUSTOM:                  1.0,
}


# ---------------------------------------------------------------------------
# ThesisClaim model
# ---------------------------------------------------------------------------

class ThesisClaim(BaseModel):
    """
    One structured investment thesis claim.

    Attributes
    ----------
    claim_id:
        UUID for this claim record.
    asset_id:
        Asset this claim is about.
    company_id:
        Company ID.
    claim_type:
        Machine-readable claim type (enum).
    assertion:
        Plain English statement of the claim (required, should be short).
    numeric_threshold:
        Quantitative threshold relevant to the claim (e.g. 0.60 for PoS).
    categorical_value:
        Categorical expected outcome (e.g. "phase_3_success", "crl").
    resolution_date:
        Expected date by which this claim should be resolved.
    created_by_signal_id:
        The StructuredSignal that originated this claim.
    resolved_by_signal_id:
        The StructuredSignal that provided resolution evidence.
    status:
        Current lifecycle state.
    resolution_evidence:
        Short description of why the claim was confirmed or refuted.
    superseded_by:
        claim_id of the newer claim if this one was superseded.
    created_at:
        UTC timestamp when the claim was created.
    resolved_at:
        UTC timestamp when the claim was resolved.
    """

    claim_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: str
    company_id: str
    claim_type: ClaimType
    assertion: str                               # required: plain English
    numeric_threshold: Optional[float] = None   # e.g. 0.60 for PoS
    categorical_value: Optional[str] = None     # e.g. "breakthrough_therapy"
    resolution_date: Optional[date] = None
    created_by_signal_id: Optional[str] = None
    weight: float = Field(default=1.0, ge=0.0)  # importance weight for weighted_thesis_strength
    resolved_by_signal_id: Optional[str] = None
    status: ClaimStatus = "open"
    resolution_evidence: Optional[str] = None
    superseded_by: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# ThesisSnapshot
# ---------------------------------------------------------------------------

class ThesisSnapshot(BaseModel):
    """
    Current thesis state for an asset — all open + recent resolved claims.

    Attributes
    ----------
    asset_id:
        Asset ID.
    n_open:
        Number of open claims.
    n_confirmed:
        Confirmed claims.
    n_refuted:
        Refuted claims.
    n_expired:
        Expired claims.
    thesis_strength:
        Heuristic: n_confirmed / (n_confirmed + n_refuted + n_expired).
        None when no resolved claims exist.
    open_claims:
        List of currently open claims.
    confirmed_claims:
        List of confirmed claims.
    refuted_claims:
        List of refuted claims.
    snapshot_at:
        UTC timestamp of this snapshot.
    """

    asset_id: str
    n_open: int = 0
    n_confirmed: int = 0
    n_refuted: int = 0
    n_expired: int = 0
    thesis_strength: Optional[float] = None
    weighted_thesis_strength: Optional[float] = None  # Wave M: weight-adjusted strength
    open_claims: list[ThesisClaim] = Field(default_factory=list)
    confirmed_claims: list[ThesisClaim] = Field(default_factory=list)
    refuted_claims: list[ThesisClaim] = Field(default_factory=list)
    snapshot_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# ThesisTracker
# ---------------------------------------------------------------------------

class ThesisTracker:
    """
    Manages structured thesis claims for assets tracked in a KnowledgeStore.

    Parameters
    ----------
    store:
        A ``KnowledgeStore`` instance.
    """

    def __init__(self, store: Any) -> None:
        self.store = store
        self._ensure_schema()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _ensure_schema(self) -> None:
        self.store._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS thesis_claims (
                claim_id              TEXT PRIMARY KEY,
                asset_id              TEXT NOT NULL,
                company_id            TEXT NOT NULL,
                claim_type            TEXT NOT NULL,
                assertion             TEXT NOT NULL,
                numeric_threshold     REAL,
                categorical_value     TEXT,
                resolution_date       TEXT,
                created_by_signal_id  TEXT,
                resolved_by_signal_id TEXT,
                status                TEXT NOT NULL DEFAULT 'open',
                resolution_evidence   TEXT,
                superseded_by         TEXT,
                created_at            TEXT NOT NULL,
                resolved_at           TEXT
            )
            """
        )
        self.store._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_thesis_claims_asset
                ON thesis_claims(asset_id, status, created_at)
            """
        )
        # Wave M migration: add weight column to existing databases
        try:
            self.store._conn.execute(
                "ALTER TABLE thesis_claims ADD COLUMN weight REAL DEFAULT 1.0"
            )
        except Exception:  # OperationalError if column already exists
            pass
        self.store._conn.commit()

    # ------------------------------------------------------------------
    # Create claim
    # ------------------------------------------------------------------

    def add_claim(
        self,
        asset_id: str,
        company_id: str,
        claim_type: ClaimType,
        assertion: str,
        *,
        numeric_threshold: Optional[float] = None,
        categorical_value: Optional[str] = None,
        resolution_date: Optional[date] = None,
        created_by_signal_id: Optional[str] = None,
        weight: Optional[float] = None,
        created_at: Optional[datetime] = None,
    ) -> ThesisClaim:
        """
        Add a new thesis claim.

        Parameters
        ----------
        weight:
            Importance weight for ``weighted_thesis_strength`` computation.
            Defaults to ``DEFAULT_CLAIM_WEIGHTS[claim_type]`` when None.
        created_at:
            Explicit creation timestamp.  When provided, overrides the default
            ``datetime.now(timezone.utc)``.  Used by replay seeding to place
            claims at a specific historical date.

        Returns
        -------
        ThesisClaim
        """
        resolved_weight = (
            weight
            if weight is not None
            else DEFAULT_CLAIM_WEIGHTS.get(claim_type.value, 1.0)
        )
        claim = ThesisClaim(
            asset_id=asset_id,
            company_id=company_id,
            claim_type=claim_type,
            assertion=assertion,
            numeric_threshold=numeric_threshold,
            categorical_value=categorical_value,
            resolution_date=resolution_date,
            created_by_signal_id=created_by_signal_id,
            weight=resolved_weight,
            created_at=created_at if created_at is not None else datetime.now(timezone.utc),
        )
        self.store._conn.execute(
            """
            INSERT OR IGNORE INTO thesis_claims
                (claim_id, asset_id, company_id, claim_type, assertion,
                 numeric_threshold, categorical_value, resolution_date,
                 created_by_signal_id, status, created_at, weight)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
            """,
            (
                claim.claim_id,
                claim.asset_id,
                claim.company_id,
                claim.claim_type.value,
                claim.assertion,
                claim.numeric_threshold,
                claim.categorical_value,
                str(claim.resolution_date) if claim.resolution_date else None,
                claim.created_by_signal_id,
                claim.created_at.isoformat(),
                claim.weight,
            ),
        )
        self.store._conn.commit()
        return claim

    # ------------------------------------------------------------------
    # Resolve claim
    # ------------------------------------------------------------------

    def resolve_claim(
        self,
        claim_id: str,
        status: ClaimStatus,
        *,
        evidence: Optional[str] = None,
        resolved_by_signal_id: Optional[str] = None,
        resolved_at: Optional[datetime] = None,
    ) -> Optional[ThesisClaim]:
        """
        Resolve a claim to confirmed / refuted / expired.

        Parameters
        ----------
        claim_id:
            ID of the claim to resolve.
        status:
            Target lifecycle state.  Must be one of
            ``"confirmed"`` / ``"refuted"`` / ``"expired"``.
        evidence:
            Short description of the resolution evidence.
        resolved_by_signal_id:
            Signal that provided the resolution trigger.
        resolved_at:
            Timestamp; defaults to utcnow.

        Returns
        -------
        Updated ThesisClaim, or None if the claim was not found.
        """
        if status not in ("confirmed", "refuted", "expired"):
            raise ValueError(f"Invalid resolution status: {status!r}")

        row = self.store._conn.execute(
            "SELECT * FROM thesis_claims WHERE claim_id = ?", (claim_id,)
        ).fetchone()
        if row is None:
            return None

        ts = (resolved_at or datetime.now(timezone.utc)).isoformat()
        self.store._conn.execute(
            """
            UPDATE thesis_claims
               SET status                = ?,
                   resolution_evidence   = ?,
                   resolved_by_signal_id = ?,
                   resolved_at           = ?
             WHERE claim_id = ?
            """,
            (status, evidence, resolved_by_signal_id, ts, claim_id),
        )
        self.store._conn.commit()
        row_dict = dict(row)
        row_dict.update(
            status=status,
            resolution_evidence=evidence,
            resolved_by_signal_id=resolved_by_signal_id,
            resolved_at=ts,
        )
        return self._row_to_claim(row_dict)

    # ------------------------------------------------------------------
    # Supersede claim
    # ------------------------------------------------------------------

    def supersede_claim(
        self,
        old_claim_id: str,
        new_claim: ThesisClaim,
    ) -> ThesisClaim:
        """
        Mark *old_claim_id* as superseded and persist *new_claim*.

        Returns the newly added claim.
        """
        self.store._conn.execute(
            "UPDATE thesis_claims SET status='superseded', superseded_by=? WHERE claim_id=?",
            (new_claim.claim_id, old_claim_id),
        )
        self.store._conn.commit()
        return self.add_claim(
            asset_id=new_claim.asset_id,
            company_id=new_claim.company_id,
            claim_type=new_claim.claim_type,
            assertion=new_claim.assertion,
            numeric_threshold=new_claim.numeric_threshold,
            categorical_value=new_claim.categorical_value,
            resolution_date=new_claim.resolution_date,
            created_by_signal_id=new_claim.created_by_signal_id,
        )

    # ------------------------------------------------------------------
    # Expire stale open claims
    # ------------------------------------------------------------------

    def expire_overdue_claims(self, *, as_of: Optional[date] = None) -> int:
        """
        Expire open claims whose resolution_date has passed.

        Returns the number of claims expired.
        """
        today = (as_of or date.today()).isoformat()
        rows = self.store._conn.execute(
            """
            SELECT claim_id FROM thesis_claims
             WHERE status = 'open'
               AND resolution_date IS NOT NULL
               AND resolution_date < ?
            """,
            (today,),
        ).fetchall()

        now_ts = datetime.now(timezone.utc).isoformat()
        for row in rows:
            self.store._conn.execute(
                """
                UPDATE thesis_claims
                   SET status     = 'expired',
                       resolved_at = ?
                 WHERE claim_id   = ?
                """,
                (now_ts, row["claim_id"]),
            )
        self.store._conn.commit()
        return len(rows)

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(
        self,
        asset_id: str,
        *,
        as_of_date: Optional[date] = None,
    ) -> ThesisSnapshot:
        """
        Compute a ThesisSnapshot for *asset_id*.

        Parameters
        ----------
        asset_id:
            Asset to snapshot.
        as_of_date:
            When provided, only claims with ``created_at <= as_of_date`` are
            included.  This is the time-freeze mechanism used by replay mode;
            the filter is enforced in SQL (not post-hoc in Python).

        Returns a ThesisSnapshot with claim counts and thesis_strength.
        """
        if as_of_date is not None:
            rows = self.store._conn.execute(
                "SELECT * FROM thesis_claims "
                "WHERE asset_id = ? AND date(created_at) <= ? "
                "ORDER BY created_at",
                (asset_id, as_of_date.isoformat()),
            ).fetchall()
        else:
            rows = self.store._conn.execute(
                "SELECT * FROM thesis_claims WHERE asset_id = ? ORDER BY created_at",
                (asset_id,),
            ).fetchall()
        claims = [self._row_to_claim(dict(r)) for r in rows]

        # When time-frozen, treat claims resolved after as_of_date as still open
        # (no-lookahead: the resolution hadn't happened yet at that date).
        if as_of_date is not None:
            as_of_dt = datetime(
                as_of_date.year, as_of_date.month, as_of_date.day,
                23, 59, 59, tzinfo=timezone.utc,
            )
            def _effective_status(c: "ThesisClaim") -> str:
                if c.status != "open" and c.resolved_at is not None:
                    if c.resolved_at > as_of_dt:
                        return "open"
                return c.status
        else:
            def _effective_status(c: "ThesisClaim") -> str:  # type: ignore[misc]
                return c.status

        open_claims = [c for c in claims if _effective_status(c) == "open"]
        confirmed = [c for c in claims if _effective_status(c) == "confirmed"]
        refuted = [c for c in claims if _effective_status(c) == "refuted"]
        expired = [c for c in claims if _effective_status(c) == "expired"]

        n_resolved = len(confirmed) + len(refuted) + len(expired)
        strength: Optional[float] = None
        weighted_strength: Optional[float] = None
        if n_resolved > 0:
            strength = round(len(confirmed) / n_resolved, 4)
            # Weighted thesis strength (Wave M)
            resolved_claims = confirmed + refuted + expired
            w_confirmed = sum(c.weight for c in confirmed)
            w_resolved = sum(c.weight for c in resolved_claims)
            if w_resolved > 0:
                weighted_strength = round(w_confirmed / w_resolved, 4)

        return ThesisSnapshot(
            asset_id=asset_id,
            n_open=len(open_claims),
            n_confirmed=len(confirmed),
            n_refuted=len(refuted),
            n_expired=len(expired),
            thesis_strength=strength,
            weighted_thesis_strength=weighted_strength,
            open_claims=open_claims,
            confirmed_claims=confirmed,
            refuted_claims=refuted,
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_claim(self, claim_id: str) -> Optional[ThesisClaim]:
        """Return a specific claim by ID."""
        row = self.store._conn.execute(
            "SELECT * FROM thesis_claims WHERE claim_id = ?", (claim_id,)
        ).fetchone()
        return self._row_to_claim(dict(row)) if row else None

    def get_claims(
        self,
        *,
        asset_id: Optional[str] = None,
        status: Optional[ClaimStatus] = None,
        claim_type: Optional[ClaimType] = None,
        limit: int = 200,
    ) -> list[ThesisClaim]:
        """Return claims with optional filters."""
        conditions: list[str] = []
        params: list[object] = []
        if asset_id:
            conditions.append("asset_id = ?")
            params.append(asset_id)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if claim_type:
            conditions.append("claim_type = ?")
            params.append(claim_type.value)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        rows = self.store._conn.execute(
            f"SELECT * FROM thesis_claims {where} ORDER BY created_at DESC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [self._row_to_claim(dict(r)) for r in rows]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_claim(row: dict) -> ThesisClaim:
        """Deserialise a DB row dict into a ThesisClaim."""
        ct = row.get("claim_type")
        try:
            claim_type = ClaimType(ct)
        except ValueError:
            claim_type = ClaimType.CUSTOM

        rd = row.get("resolution_date")
        res_date = date.fromisoformat(rd) if rd else None

        resolved_at_str = row.get("resolved_at")
        resolved_at: Optional[datetime] = None
        if resolved_at_str:
            try:
                resolved_at = datetime.fromisoformat(str(resolved_at_str))
                if resolved_at.tzinfo is None:
                    resolved_at = resolved_at.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                pass

        created_at_str = row.get("created_at", "")
        try:
            created_at = datetime.fromisoformat(str(created_at_str))
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            created_at = datetime.now(timezone.utc)

        raw_weight = row.get("weight")
        weight = float(raw_weight) if raw_weight is not None else DEFAULT_CLAIM_WEIGHTS.get(
            str(row.get("claim_type") or "custom"), 1.0
        )

        return ThesisClaim(
            claim_id=str(row["claim_id"]),
            asset_id=str(row["asset_id"]),
            company_id=str(row["company_id"]),
            claim_type=claim_type,
            assertion=str(row.get("assertion") or ""),
            numeric_threshold=row.get("numeric_threshold"),
            categorical_value=row.get("categorical_value"),
            resolution_date=res_date,
            created_by_signal_id=row.get("created_by_signal_id"),
            resolved_by_signal_id=row.get("resolved_by_signal_id"),
            status=str(row.get("status") or "open"),  # type: ignore[arg-type]
            resolution_evidence=row.get("resolution_evidence"),
            superseded_by=row.get("superseded_by"),
            created_at=created_at,
            resolved_at=resolved_at,
            weight=weight,
        )
