"""Repository for AcquisitionScore and AcquirerProfile operations."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from bve.persistence.models import AcquirerProfile, AcquisitionScore


class AcquirerProfileRepo:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_company_id(self, company_id: str) -> Optional[AcquirerProfile]:
        return (
            self._db.query(AcquirerProfile)
            .filter(AcquirerProfile.company_id == company_id)
            .first()
        )

    def upsert(self, company_id: str, **kwargs) -> AcquirerProfile:
        profile = self.get_by_company_id(company_id)
        if profile is None:
            profile = AcquirerProfile(company_id=company_id, **kwargs)
            self._db.add(profile)
        else:
            for k, v in kwargs.items():
                setattr(profile, k, v)
        self._db.flush()
        return profile

    def list_all(self) -> list[AcquirerProfile]:
        return self._db.query(AcquirerProfile).all()


class AcquisitionScoreRepo:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, target_company_id: str, acquirer_company_id: str) -> Optional[AcquisitionScore]:
        return (
            self._db.query(AcquisitionScore)
            .filter(
                AcquisitionScore.target_company_id == target_company_id,
                AcquisitionScore.acquirer_company_id == acquirer_company_id,
            )
            .first()
        )

    def upsert(self, target_company_id: str, acquirer_company_id: str, **kwargs) -> AcquisitionScore:
        score = self.get(target_company_id, acquirer_company_id)
        if score is None:
            score = AcquisitionScore(
                target_company_id=target_company_id,
                acquirer_company_id=acquirer_company_id,
                **kwargs,
            )
            self._db.add(score)
        else:
            for k, v in kwargs.items():
                setattr(score, k, v)
        self._db.flush()
        return score

    def top_targets_for_acquirer(
        self, acquirer_company_id: str, limit: int = 20, min_fit_score: float = 0.0
    ) -> list[AcquisitionScore]:
        return (
            self._db.query(AcquisitionScore)
            .filter(
                AcquisitionScore.acquirer_company_id == acquirer_company_id,
                AcquisitionScore.fit_score >= min_fit_score,
            )
            .order_by(AcquisitionScore.fit_score.desc())
            .limit(limit)
            .all()
        )

    def top_acquirers_for_target(
        self, target_company_id: str, limit: int = 10
    ) -> list[AcquisitionScore]:
        return (
            self._db.query(AcquisitionScore)
            .filter(AcquisitionScore.target_company_id == target_company_id)
            .order_by(AcquisitionScore.fit_score.desc())
            .limit(limit)
            .all()
        )

    def list_by_timing(self, timing_bucket: str) -> list[AcquisitionScore]:
        return (
            self._db.query(AcquisitionScore)
            .filter(AcquisitionScore.timing_bucket == timing_bucket)
            .order_by(AcquisitionScore.fit_score.desc())
            .all()
        )
