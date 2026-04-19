"""Repository for Company CRUD operations."""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from bve.persistence.models import Company


class CompanyRepo:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, company_id: str) -> Optional[Company]:
        return self._db.get(Company, company_id)

    def get_by_ticker(self, ticker: str) -> Optional[Company]:
        return self._db.query(Company).filter(Company.ticker == ticker.upper()).first()

    def get_by_name(self, name: str) -> Optional[Company]:
        return self._db.query(Company).filter(Company.name == name).first()

    def list_all(self, company_type: Optional[str] = None) -> list[Company]:
        q = self._db.query(Company)
        if company_type:
            q = q.filter(Company.company_type == company_type)
        return q.order_by(Company.name).all()

    def upsert_by_ticker(self, ticker: str, **kwargs) -> Company:
        """Create or update a company by ticker symbol."""
        ticker = ticker.upper()
        company = self.get_by_ticker(ticker)
        if company is None:
            company = Company(ticker=ticker, **kwargs)
            self._db.add(company)
        else:
            for k, v in kwargs.items():
                setattr(company, k, v)
        self._db.flush()
        return company

    def upsert_by_name(self, name: str, **kwargs) -> Company:
        """Create or update a company by name (for companies without tickers)."""
        company = self.get_by_name(name)
        if company is None:
            company = Company(name=name, **kwargs)
            self._db.add(company)
        else:
            for k, v in kwargs.items():
                setattr(company, k, v)
        self._db.flush()
        return company

    def delete(self, company_id: str) -> bool:
        company = self.get_by_id(company_id)
        if company:
            self._db.delete(company)
            self._db.flush()
            return True
        return False
