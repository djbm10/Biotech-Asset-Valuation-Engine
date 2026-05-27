"""AssetRepository — CRUD for the asset_state DB table.

Wraps ``AssetStateRecord`` (in ``bve.persistence.models``) and handles
serialisation/deserialisation between ``AssetState`` dataclasses and JSON
column blobs.

Usage (production)
------------------
    from bve.persistence.db import session_scope, engine
    from bve.state.asset_repository import AssetRepository

    AssetRepository.create_table(engine)   # idempotent; call once at startup
    with session_scope() as session:
        repo = AssetRepository(session)
        state = repo.load("SRPT")

Usage (tests)
-------------
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from bve.state.asset_repository import AssetRepository

    engine = create_engine("sqlite:///:memory:")
    AssetRepository.create_table(engine)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        repo = AssetRepository(session)
        repo.upsert(some_state)
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from bve.refresh.financial_refresh import FinancialSnapshot
from bve.refresh.input_integrity import InputIntegrityScore, SurfaceScore
from bve.refresh.market_data_refresh import MarketDataSnapshot
from bve.reporting.provenance import ProvenanceItem
from bve.state.asset_state import AssetState, ClinicalAssetState, ValuationInputState, _parse_date


class AssetRepository:
    """CRUD operations over the ``asset_state`` table.

    Parameters
    ----------
    session:
        An active SQLAlchemy session.  The caller is responsible for
        committing or rolling back.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Schema management
    # ------------------------------------------------------------------

    @staticmethod
    def create_table(engine) -> None:
        """Create the ``asset_state`` table if it does not already exist.

        Safe to call repeatedly (uses ``checkfirst=True``).
        """
        from bve.persistence.models import AssetStateRecord  # noqa: F401 — registers model
        AssetStateRecord.__table__.create(bind=engine, checkfirst=True)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def upsert(self, state: AssetState) -> None:
        """Insert or update the full state for *state.ticker*.

        Existing provenance entries are overwritten.  To preserve historical
        provenance, callers should load first, append new items, then upsert.
        """
        from bve.persistence.models import AssetStateRecord

        ticker = state.ticker.upper()
        record = self._session.get(AssetStateRecord, ticker)
        if record is None:
            record = AssetStateRecord(ticker=ticker)
            self._session.add(record)

        record.company_name = state.company_name
        record.last_refreshed = state.last_refreshed.isoformat()
        record.market_data_json = state.market_data.to_dict()
        record.financials_json = state.financials.to_dict()
        record.clinical_json = [c.to_dict() for c in state.clinical_assets]
        record.valuation_json = state.valuation_inputs.to_dict()
        record.provenance_json = [_provenance_to_dict(p) for p in state.source_provenance]
        record.integrity_json = state.integrity_score.to_dict()
        self._session.flush()

    def mark_stale(self, ticker: str, field_name: str) -> None:
        """Flag a specific provenance field as stale without a full re-fetch."""
        from sqlalchemy.orm.attributes import flag_modified
        from bve.persistence.models import AssetStateRecord

        record = self._session.get(AssetStateRecord, ticker.upper())
        if record is None:
            return
        prov: list[dict] = [dict(item) for item in (record.provenance_json or [])]
        for item in prov:
            if item.get("field") == field_name:
                item["staleness_warning"] = f"{field_name} marked stale"
                item["confidence"] = "stale"
        record.provenance_json = prov
        flag_modified(record, "provenance_json")
        self._session.flush()

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def load(self, ticker: str) -> Optional[AssetState]:
        """Load the current state for *ticker*. Returns ``None`` if not found."""
        from bve.persistence.models import AssetStateRecord

        record = self._session.get(AssetStateRecord, ticker.upper())
        if record is None:
            return None
        return _record_to_state(record)

    def load_or_scaffold(
        self,
        ticker: str,
        yaml_path: Optional[Path] = None,
    ) -> AssetState:
        """Load from DB; if missing, build a skeleton state and persist it."""
        state = self.load(ticker)
        if state is not None:
            return state
        state = _scaffold_state(ticker.upper(), yaml_path)
        self.upsert(state)
        return state

    def list_tickers(self) -> list[str]:
        """Return all tickers with stored state, sorted alphabetically."""
        from bve.persistence.models import AssetStateRecord

        rows = self._session.query(AssetStateRecord).all()
        return sorted(r.ticker for r in rows)

    def last_refreshed(self, ticker: str) -> Optional[date]:
        """Return the ``last_refreshed`` date for *ticker*, or None."""
        from bve.persistence.models import AssetStateRecord

        record = self._session.get(AssetStateRecord, ticker.upper())
        if record is None or not record.last_refreshed:
            return None
        return date.fromisoformat(record.last_refreshed)


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _provenance_to_dict(p: ProvenanceItem) -> dict:
    return {
        "field": p.field,
        "value": str(p.value) if p.value is not None else None,
        "source": p.source,
        "as_of": p.as_of.isoformat() if p.as_of else None,
        "staleness_warning": p.staleness_warning,
        "confidence": p.confidence,
        "notes": p.notes,
    }


def _provenance_from_dict(d: dict) -> ProvenanceItem:
    return ProvenanceItem(
        field=d.get("field", ""),
        value=d.get("value"),
        source=d.get("source", "not_available"),
        as_of=_parse_date(d.get("as_of")),
        staleness_warning=d.get("staleness_warning"),
        confidence=d.get("confidence", "medium"),
        notes=d.get("notes"),
    )


def _mds_from_dict(d: dict) -> MarketDataSnapshot:
    return MarketDataSnapshot(
        ticker=d.get("ticker", ""),
        price=d.get("price"),
        shares_outstanding_millions=d.get("shares_outstanding_millions"),
        market_cap_millions=d.get("market_cap_millions"),
        enterprise_value_millions=d.get("enterprise_value_millions"),
        volume_avg_30d=d.get("volume_avg_30d"),
        as_of=_parse_date(d.get("as_of")),
        source=d.get("source", "not_available"),
        confidence=d.get("confidence", "not_available"),
        staleness_warning=d.get("staleness_warning"),
    )


def _fin_from_dict(d: dict) -> FinancialSnapshot:
    return FinancialSnapshot(
        ticker=d.get("ticker", ""),
        cash_millions=d.get("cash_millions"),
        total_debt_millions=d.get("total_debt_millions"),
        net_cash_millions=d.get("net_cash_millions"),
        shares_outstanding_millions=d.get("shares_outstanding_millions"),
        quarterly_burn_millions=d.get("quarterly_burn_millions"),
        runway_quarters=d.get("runway_quarters"),
        filing_date=_parse_date(d.get("filing_date")),
        as_of=_parse_date(d.get("as_of")),
        source=d.get("source", "not_available"),
        confidence=d.get("confidence", "not_available"),
        staleness_warning=d.get("staleness_warning"),
    )


def _integrity_from_dict(d: dict) -> InputIntegrityScore:
    surfaces = d.get("surfaces", {})

    def _surface(name: str) -> SurfaceScore:
        s = surfaces.get(name, {})
        return SurfaceScore(
            surface_name=name,
            score=s.get("score", 0.0),
            confidence=s.get("confidence", "not_available"),
            as_of=_parse_date(s.get("as_of")),
            notes=s.get("notes", []),
        )

    return InputIntegrityScore(
        overall_score=d.get("overall_score", 0.0),
        overall_grade=d.get("overall_grade", "D"),
        market_data=_surface("market_data"),
        financials=_surface("financials"),
        profiles=_surface("profiles"),
        trials=_surface("trials"),
        as_of=_parse_date(d.get("as_of")),
        warnings=d.get("warnings", []),
    )


# ---------------------------------------------------------------------------
# ORM → AssetState conversion
# ---------------------------------------------------------------------------

def _record_to_state(record) -> AssetState:
    ticker = record.ticker or ""
    mds = _mds_from_dict(record.market_data_json or {"ticker": ticker})
    fin = _fin_from_dict(record.financials_json or {"ticker": ticker})
    clinical = [
        ClinicalAssetState.from_dict(c)
        for c in (record.clinical_json or [])
    ]
    val = ValuationInputState.from_dict(record.valuation_json or {})
    prov = [_provenance_from_dict(p) for p in (record.provenance_json or [])]
    integrity = _integrity_from_dict(record.integrity_json or {})
    last_refreshed = _parse_date(record.last_refreshed) or date.today()

    return AssetState(
        ticker=ticker,
        company_name=record.company_name or ticker,
        market_data=mds,
        financials=fin,
        clinical_assets=clinical,
        valuation_inputs=val,
        source_provenance=prov,
        last_refreshed=last_refreshed,
        integrity_score=integrity,
    )


# ---------------------------------------------------------------------------
# Scaffold helpers
# ---------------------------------------------------------------------------

def _scaffold_state(ticker: str, yaml_path: Optional[Path] = None) -> AssetState:
    """Build a minimal skeleton AssetState seeded from YAML (or empty defaults)."""
    today = date.today()
    company_name = f"{ticker} Therapeutics"

    if yaml_path and yaml_path.exists():
        try:
            import yaml  # type: ignore[import-untyped]
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            company_name = data.get("company_name", company_name)
        except Exception:
            pass

    seed_prov = ProvenanceItem(
        field="initial_scaffold",
        value="YAML seed",
        source="yaml_config",
        as_of=today,
        confidence="low",
        notes="Auto-generated by bve-init-asset",
    )

    return AssetState(
        ticker=ticker,
        company_name=company_name,
        market_data=MarketDataSnapshot(ticker=ticker),
        financials=FinancialSnapshot(ticker=ticker),
        clinical_assets=[],
        valuation_inputs=ValuationInputState(is_screening_grade=True),
        source_provenance=[seed_prov],
        last_refreshed=today,
        integrity_score=InputIntegrityScore(),
    )
