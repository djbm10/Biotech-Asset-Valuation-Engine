"""Repository for EvidenceItem deduplication and storage."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from bve.persistence.models import EvidenceItem


class EvidenceRepo:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, evidence_id: str) -> Optional[EvidenceItem]:
        return self._db.get(EvidenceItem, evidence_id)

    def get_by_checksum(self, checksum: str) -> Optional[EvidenceItem]:
        return (
            self._db.query(EvidenceItem)
            .filter(EvidenceItem.checksum == checksum)
            .first()
        )

    @staticmethod
    def compute_checksum(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    def store_if_new(
        self,
        source_type: str,
        raw_text: str,
        *,
        source_url: Optional[str] = None,
        published_at: Optional[datetime] = None,
        title: Optional[str] = None,
        parsed_json: Optional[dict] = None,
        materiality_score: Optional[float] = None,
    ) -> tuple[EvidenceItem, bool]:
        """Store evidence item if not already present (deduplication via checksum).

        Returns (item, is_new).
        """
        checksum = self.compute_checksum(raw_text)
        existing = self.get_by_checksum(checksum)
        if existing:
            return existing, False

        item = EvidenceItem(
            source_type=source_type,
            source_url=source_url,
            published_at=published_at,
            title=title,
            raw_text=raw_text,
            checksum=checksum,
            parsed_json=parsed_json,
            materiality_score=materiality_score,
        )
        self._db.add(item)
        self._db.flush()
        return item, True

    def list_recent(self, source_type: Optional[str] = None, limit: int = 100) -> list[EvidenceItem]:
        q = self._db.query(EvidenceItem).order_by(EvidenceItem.created_at.desc())
        if source_type:
            q = q.filter(EvidenceItem.source_type == source_type)
        return q.limit(limit).all()

    def list_high_materiality(self, threshold: float = 0.7, limit: int = 50) -> list[EvidenceItem]:
        return (
            self._db.query(EvidenceItem)
            .filter(EvidenceItem.materiality_score >= threshold)
            .order_by(EvidenceItem.materiality_score.desc())
            .limit(limit)
            .all()
        )
