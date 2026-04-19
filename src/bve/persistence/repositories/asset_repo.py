"""Repository for Asset CRUD operations."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from bve.persistence.models import Asset


class AssetRepo:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, asset_id: str) -> Optional[Asset]:
        return self._db.get(Asset, asset_id)

    def list_by_company(self, company_id: str) -> list[Asset]:
        return (
            self._db.query(Asset)
            .filter(Asset.company_id == company_id)
            .order_by(Asset.name)
            .all()
        )

    def list_by_phase(self, phase: str) -> list[Asset]:
        return self._db.query(Asset).filter(Asset.current_phase == phase).all()

    def list_by_ta(self, therapeutic_area: str) -> list[Asset]:
        return (
            self._db.query(Asset)
            .filter(Asset.therapeutic_area == therapeutic_area)
            .all()
        )

    def find_by_name(self, name: str, company_id: Optional[str] = None) -> Optional[Asset]:
        q = self._db.query(Asset).filter(Asset.name == name)
        if company_id:
            q = q.filter(Asset.company_id == company_id)
        return q.first()

    def upsert(self, company_id: str, name: str, indication: Optional[str] = None, **kwargs) -> Asset:
        q = (
            self._db.query(Asset)
            .filter(Asset.company_id == company_id, Asset.name == name)
        )
        if indication is not None:
            q = q.filter(Asset.indication == indication)
        asset = q.first()
        if asset is None:
            asset = Asset(company_id=company_id, name=name, indication=indication, **kwargs)
            self._db.add(asset)
        else:
            for k, v in kwargs.items():
                setattr(asset, k, v)
            if indication is not None:
                asset.indication = indication
        self._db.flush()
        return asset

    def list_with_catalysts(self) -> list[Asset]:
        """Return assets that have at least one pending catalyst."""
        from bve.persistence.models import Catalyst
        return (
            self._db.query(Asset)
            .join(Catalyst, Catalyst.asset_id == Asset.id)
            .filter(Catalyst.status == "pending")
            .distinct()
            .all()
        )
