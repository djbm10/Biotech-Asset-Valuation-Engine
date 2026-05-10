"""
ProvenanceRegistry — queryable provenance for every material field in a CompanySnapshot.

Phase 2A objective
------------------
Every material field must be attributable to:
  - a source class (ValueBucket or CompanySnapshot)
  - an exact as-of date
  - a corroboration count
  - a reviewer status (who approved the value)
  - a confidence score

Design
------
The registry wraps a SnapshotStore and provides a per-field provenance query.

Two provenance classes:
  1. ValueBucket fields — source class "ValueBucket"; provenance drawn directly
     from the bucket's own ``source_ref``, ``as_of_date``, ``corroboration_count``,
     ``reviewer``, and ``confidence``.

  2. Top-level snapshot fields — source class "CompanySnapshot"; provenance drawn
     from the snapshot's ``as_of_date``, ``provenance.created_by``, and
     ``confidence.overall_confidence``.  These have ``corroboration_count=0``
     because they are single-source balance-sheet / market-data fields.

The ``field_name`` key for bucket fields is the bucket_id, e.g.
``"vktx_gb004_asset"`` or ``"net_cash"``.  Top-level numeric fields use the
Python attribute name, e.g. ``"market_cap_millions"``, ``"cash_millions"``.

Usage
-----
    registry = ProvenanceRegistry(store)
    prov = registry.get_field_provenance("vktx", "vktx_gb004_asset")
    all_prov = registry.get_all_provenance("vktx")
    report = registry.export_provenance_report("vktx")
"""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from bve.entities.company_snapshot import CompanySnapshot

if TYPE_CHECKING:
    from bve.persistence.snapshot_store import SnapshotStore

# Top-level numeric snapshot fields considered material (tracked as provenance).
_SNAPSHOT_NUMERIC_FIELDS: tuple[str, ...] = (
    "market_cap_millions",
    "enterprise_value_millions",
    "cash_millions",
    "debt_millions",
    "share_price",
)


class FieldProvenance(BaseModel, frozen=True):
    """
    Provenance record for one material field in a CompanySnapshot.

    Parameters
    ----------
    field_name
        Attribute name or bucket_id identifying the field.
    source_class
        "ValueBucket" for bucket fields; "CompanySnapshot" for top-level fields.
    source_ref
        Human-readable citation, e.g. "10-K:2025-12-31:pg42" or
        "bve-asset:relay_rly2608.yaml:2026-04-01".
    as_of_date
        Point-in-time date of the underlying data.
    corroboration_count
        Number of independent sources that agree on this value.
        0 for single-source top-level snapshot fields.
    reviewer_status
        Reviewer identity string, or None when no reviewer has signed off.
    confidence
        Confidence score in [0, 1].
    """
    field_name: str
    source_class: str  # "ValueBucket" | "CompanySnapshot"
    source_ref: str
    as_of_date: date
    corroboration_count: int = Field(default=0, ge=0)
    reviewer_status: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)


def _bucket_provenance(bucket, bucket_id_override: Optional[str] = None) -> FieldProvenance:
    """Build FieldProvenance from a ValueBucket."""
    return FieldProvenance(
        field_name=bucket_id_override or bucket.bucket_id,
        source_class="ValueBucket",
        source_ref=bucket.source_ref,
        as_of_date=bucket.as_of_date,
        corroboration_count=bucket.corroboration_count,
        reviewer_status=bucket.reviewer,
        confidence=bucket.confidence,
    )


def _snapshot_field_provenance(snapshot: CompanySnapshot, field_name: str) -> FieldProvenance:
    """Build FieldProvenance for a top-level snapshot numeric field."""
    return FieldProvenance(
        field_name=field_name,
        source_class="CompanySnapshot",
        source_ref=(
            f"CompanySnapshot:{snapshot.company_id}:{snapshot.as_of_date.isoformat()}"
        ),
        as_of_date=snapshot.as_of_date,
        corroboration_count=0,
        reviewer_status=snapshot.provenance.created_by if snapshot.provenance.created_by != "system" else None,
        confidence=snapshot.confidence.overall_confidence,
    )


class ProvenanceRegistry:
    """
    Queryable provenance index for CompanySnapshot material fields.

    Wraps a ``SnapshotStore`` and operates on the latest snapshot for a given
    company_id (or the latest on/before ``as_of``).

    Methods
    -------
    get_field_provenance(company_id, field_name, *, as_of)
        Returns the FieldProvenance for one field, or None if not found.

    get_all_provenance(company_id, *, as_of)
        Returns all provenance records as ``dict[field_name, FieldProvenance]``.

    export_provenance_report(company_id, *, as_of)
        Returns a JSON-serializable dict for audit export.
    """

    def __init__(self, store: "SnapshotStore") -> None:  # type: ignore[name-defined]
        self._store = store

    def _load_snapshot(
        self, company_id: str, *, as_of: Optional[date] = None
    ) -> Optional[CompanySnapshot]:
        return self._store.get_latest_snapshot(company_id, as_of=as_of)

    def get_field_provenance(
        self,
        company_id: str,
        field_name: str,
        *,
        as_of: Optional[date] = None,
    ) -> Optional[FieldProvenance]:
        """
        Return FieldProvenance for a specific field name.

        For top-level numeric fields, ``field_name`` must be one of:
            market_cap_millions, enterprise_value_millions, cash_millions,
            debt_millions, share_price.

        For value buckets, ``field_name`` is the ``bucket_id``.

        Returns None when:
        - No snapshot exists for company_id
        - field_name is not found in either buckets or top-level fields
        """
        snap = self._load_snapshot(company_id, as_of=as_of)
        if snap is None:
            return None

        # Check top-level numeric fields first
        if field_name in _SNAPSHOT_NUMERIC_FIELDS:
            return _snapshot_field_provenance(snap, field_name)

        # Check value buckets by bucket_id
        for bucket in snap.all_buckets:
            if bucket.bucket_id == field_name:
                return _bucket_provenance(bucket)

        return None

    def get_all_provenance(
        self,
        company_id: str,
        *,
        as_of: Optional[date] = None,
    ) -> dict[str, FieldProvenance]:
        """
        Return provenance for all material fields in the latest snapshot.

        Returns an empty dict when no snapshot exists.
        Keys are: bucket_ids + snapshot top-level field names.
        """
        snap = self._load_snapshot(company_id, as_of=as_of)
        if snap is None:
            return {}

        result: dict[str, FieldProvenance] = {}

        # Top-level numeric fields
        for field_name in _SNAPSHOT_NUMERIC_FIELDS:
            if field_name == "share_price" and snap.share_price is None:
                continue  # skip optional field when not set
            result[field_name] = _snapshot_field_provenance(snap, field_name)

        # ValueBucket fields
        for bucket in snap.all_buckets:
            result[bucket.bucket_id] = _bucket_provenance(bucket)

        return result

    def export_provenance_report(
        self,
        company_id: str,
        *,
        as_of: Optional[date] = None,
    ) -> dict:
        """
        Return a JSON-serializable provenance audit report.

        Structure
        ---------
        {
            "company_id": str,
            "snapshot_id": str | None,
            "as_of_date": str | None,
            "reviewer_state": str | None,
            "total_fields": int,
            "fields": [
                {
                    "field_name": str,
                    "source_class": str,
                    "source_ref": str,
                    "as_of_date": str,
                    "corroboration_count": int,
                    "reviewer_status": str | None,
                    "confidence": float,
                },
                ...
            ]
        }
        """
        snap = self._load_snapshot(company_id, as_of=as_of)
        all_prov = self.get_all_provenance(company_id, as_of=as_of)

        fields = [
            {
                "field_name": fp.field_name,
                "source_class": fp.source_class,
                "source_ref": fp.source_ref,
                "as_of_date": fp.as_of_date.isoformat(),
                "corroboration_count": fp.corroboration_count,
                "reviewer_status": fp.reviewer_status,
                "confidence": fp.confidence,
            }
            for fp in all_prov.values()
        ]

        return {
            "company_id": company_id,
            "snapshot_id": snap.snapshot_id if snap else None,
            "as_of_date": snap.as_of_date.isoformat() if snap else None,
            "reviewer_state": snap.reviewer_state.value if snap else None,
            "total_fields": len(fields),
            "fields": fields,
        }
