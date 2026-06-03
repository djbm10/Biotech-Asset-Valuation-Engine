"""Tests for SQLAlchemy ORM models and repositories (Step 1: Database Foundation).

Uses SQLite in-memory database — no external dependencies required.
"""

from __future__ import annotations

import os
import pytest

# Use in-memory SQLite for tests
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

from bve.persistence.db import Base, SessionLocal, create_engine, engine  # noqa: E402
from bve.persistence.models import (  # noqa: E402
    AcquirerProfile,
    AcquisitionScore,
    Asset,
    AssetDossierRecord,
    Catalyst,
    Company,
    CompetitionEdge,
    DecisionRecord,
    EvidenceItem,
    FinancingForecast,
    ImpliedExpectation,
    MarketSnapshot,
    OutcomeRecord,
    ParameterVersion,
    ScenarioTree,
    Trial,
    VariantThesis,
)
from bve.persistence.repositories.company_repo import CompanyRepo  # noqa: E402
from bve.persistence.repositories.asset_repo import AssetRepo  # noqa: E402
from bve.persistence.repositories.evidence_repo import EvidenceRepo  # noqa: E402
from bve.persistence.repositories.acquisition_repo import (  # noqa: E402
    AcquirerProfileRepo,
    AcquisitionScoreRepo,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def db():
    """Provide a fresh in-memory database session for each test."""
    import sqlalchemy as sa

    test_engine = sa.create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    TestSession = sa.orm.sessionmaker(bind=test_engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)


# ---------------------------------------------------------------------------
# Company model
# ---------------------------------------------------------------------------

class TestCompanyModel:
    def test_create_company(self, db):
        c = Company(ticker="MRNA", name="Moderna", company_type="public_biotech")
        db.add(c)
        db.commit()
        assert c.id is not None
        assert len(c.id) == 36  # UUID format

    def test_company_id_is_uuid_string(self, db):
        c = Company(name="Pfizer", company_type="big_pharma")
        db.add(c)
        db.commit()
        assert "-" in c.id

    def test_company_timestamps_set(self, db):
        c = Company(name="AstraZeneca", company_type="big_pharma")
        db.add(c)
        db.commit()
        assert c.created_at is not None
        assert c.updated_at is not None

    def test_company_numeric_fields_nullable(self, db):
        c = Company(name="BioNTech", company_type="public_biotech")
        db.add(c)
        db.commit()
        assert c.market_cap is None
        assert c.cash is None

    def test_company_with_financials(self, db):
        c = Company(
            ticker="LLY",
            name="Eli Lilly",
            company_type="big_pharma",
            market_cap=750_000.0,
            cash=10_000.0,
            debt=15_000.0,
        )
        db.add(c)
        db.commit()
        fetched = db.get(Company, c.id)
        assert fetched.market_cap == 750_000.0


# ---------------------------------------------------------------------------
# CompanyRepo
# ---------------------------------------------------------------------------

class TestCompanyRepo:
    def test_upsert_creates_new(self, db):
        repo = CompanyRepo(db)
        c = repo.upsert_by_ticker("NVAX", name="Novavax", company_type="public_biotech")
        db.commit()
        assert c.ticker == "NVAX"

    def test_upsert_updates_existing(self, db):
        repo = CompanyRepo(db)
        repo.upsert_by_ticker("NVAX", name="Novavax", company_type="public_biotech")
        db.commit()
        repo.upsert_by_ticker("NVAX", market_cap=1500.0)
        db.commit()
        fetched = repo.get_by_ticker("NVAX")
        assert fetched.market_cap == 1500.0

    def test_upsert_ticker_uppercased(self, db):
        repo = CompanyRepo(db)
        repo.upsert_by_ticker("mrna", name="Moderna", company_type="public_biotech")
        db.commit()
        assert repo.get_by_ticker("MRNA") is not None

    def test_get_by_ticker_returns_none_for_unknown(self, db):
        repo = CompanyRepo(db)
        assert repo.get_by_ticker("UNKNOWN") is None

    def test_list_all_filtered_by_type(self, db):
        repo = CompanyRepo(db)
        repo.upsert_by_ticker("PFE", name="Pfizer", company_type="big_pharma")
        repo.upsert_by_ticker("MRNA", name="Moderna", company_type="public_biotech")
        db.commit()
        pharmas = repo.list_all(company_type="big_pharma")
        assert len(pharmas) == 1
        assert pharmas[0].ticker == "PFE"

    def test_delete_company(self, db):
        repo = CompanyRepo(db)
        c = repo.upsert_by_ticker("DEL", name="DeleteMe", company_type="public_biotech")
        db.commit()
        assert repo.delete(c.id) is True
        assert repo.get_by_ticker("DEL") is None

    def test_delete_missing_returns_false(self, db):
        repo = CompanyRepo(db)
        assert repo.delete("nonexistent-id") is False

    def test_upsert_by_name(self, db):
        repo = CompanyRepo(db)
        c = repo.upsert_by_name("Private Co", company_type="private_biotech")
        db.commit()
        assert c.name == "Private Co"
        assert c.ticker is None


# ---------------------------------------------------------------------------
# Asset model + repo
# ---------------------------------------------------------------------------

class TestAssetRepo:
    def _make_company(self, db):
        repo = CompanyRepo(db)
        return repo.upsert_by_ticker("AGEN", name="Agenus", company_type="public_biotech")

    def test_upsert_creates_asset(self, db):
        company = self._make_company(db)
        db.commit()
        repo = AssetRepo(db)
        asset = repo.upsert(company.id, "botensilimab", indication="NSCLC")
        db.commit()
        assert asset.id is not None
        assert asset.name == "botensilimab"

    def test_upsert_does_not_duplicate(self, db):
        company = self._make_company(db)
        db.commit()
        repo = AssetRepo(db)
        a1 = repo.upsert(company.id, "botensilimab", indication="NSCLC")
        a2 = repo.upsert(company.id, "botensilimab", indication="NSCLC", current_phase="Phase 2")
        db.commit()
        assert a1.id == a2.id
        assert a1.current_phase == "Phase 2"

    def test_list_by_company(self, db):
        company = self._make_company(db)
        db.commit()
        repo = AssetRepo(db)
        repo.upsert(company.id, "asset-A")
        repo.upsert(company.id, "asset-B")
        db.commit()
        assets = repo.list_by_company(company.id)
        assert len(assets) == 2

    def test_list_by_phase(self, db):
        company = self._make_company(db)
        db.commit()
        repo = AssetRepo(db)
        repo.upsert(company.id, "p3-drug", current_phase="Phase 3")
        repo.upsert(company.id, "p2-drug", current_phase="Phase 2")
        db.commit()
        p3 = repo.list_by_phase("Phase 3")
        assert len(p3) == 1


# ---------------------------------------------------------------------------
# EvidenceRepo — deduplication
# ---------------------------------------------------------------------------

class TestEvidenceRepo:
    def test_store_new_item(self, db):
        repo = EvidenceRepo(db)
        item, is_new = repo.store_if_new("press_release", "Drug X achieved primary endpoint.")
        db.commit()
        assert is_new is True
        assert item.id is not None

    def test_deduplication_on_same_text(self, db):
        repo = EvidenceRepo(db)
        text = "Phase 3 trial of Drug Y met primary endpoint."
        item1, new1 = repo.store_if_new("press_release", text)
        db.commit()
        item2, new2 = repo.store_if_new("press_release", text)
        db.commit()
        assert new1 is True
        assert new2 is False
        assert item1.id == item2.id

    def test_different_texts_both_stored(self, db):
        repo = EvidenceRepo(db)
        repo.store_if_new("press_release", "Text A about drug X.")
        repo.store_if_new("press_release", "Text B about drug Y.")
        db.commit()
        items = repo.list_recent()
        assert len(items) == 2

    def test_checksum_computed_correctly(self, db):
        import hashlib
        text = "Some evidence text."
        expected = hashlib.sha256(text.encode()).hexdigest()
        assert EvidenceRepo.compute_checksum(text) == expected

    def test_list_high_materiality(self, db):
        repo = EvidenceRepo(db)
        repo.store_if_new("sec", "Low materiality text.", materiality_score=0.2)
        repo.store_if_new("press_release", "High materiality text.", materiality_score=0.9)
        db.commit()
        high = repo.list_high_materiality(threshold=0.7)
        assert len(high) == 1
        assert high[0].materiality_score == 0.9

    def test_list_recent_filtered_by_source_type(self, db):
        repo = EvidenceRepo(db)
        repo.store_if_new("sec", "SEC filing A.")
        repo.store_if_new("press_release", "PR about drug.")
        db.commit()
        sec_items = repo.list_recent(source_type="sec")
        assert len(sec_items) == 1


# ---------------------------------------------------------------------------
# Trial model
# ---------------------------------------------------------------------------

class TestTrialModel:
    def test_create_trial(self, db):
        company = Company(name="TestCo", company_type="public_biotech")
        db.add(company)
        db.flush()
        asset = Asset(company_id=company.id, name="drug-A")
        db.add(asset)
        db.flush()
        trial = Trial(
            asset_id=asset.id,
            nct_id="NCT12345678",
            phase="Phase 2",
            endpoint_primary="ORR",
            enrollment_target=120,
        )
        db.add(trial)
        db.commit()
        assert trial.id is not None
        assert trial.nct_id == "NCT12345678"


# ---------------------------------------------------------------------------
# AcquirerProfile + AcquisitionScore repos
# ---------------------------------------------------------------------------

class TestAcquisitionRepos:
    def _make_companies(self, db):
        target = Company(name="SmallBio", company_type="public_biotech", ticker="SMBIO",
                         market_cap=800.0, cash=200.0)
        acquirer = Company(name="BigPharma", company_type="big_pharma", ticker="BPHRM",
                           cash=50000.0)
        db.add_all([target, acquirer])
        db.flush()
        return target, acquirer

    def test_acquirer_profile_upsert(self, db):
        _, acquirer = self._make_companies(db)
        repo = AcquirerProfileRepo(db)
        profile = repo.upsert(
            acquirer.id,
            strategic_areas=["oncology", "immunology"],
            cash_firepower=30000.0,
        )
        db.commit()
        assert profile.id is not None
        assert profile.cash_firepower == 30000.0

    def test_acquirer_profile_update(self, db):
        _, acquirer = self._make_companies(db)
        repo = AcquirerProfileRepo(db)
        repo.upsert(acquirer.id, cash_firepower=10000.0)
        db.commit()
        repo.upsert(acquirer.id, cash_firepower=25000.0)
        db.commit()
        profile = repo.get_by_company_id(acquirer.id)
        assert profile.cash_firepower == 25000.0

    def test_acquisition_score_upsert(self, db):
        target, acquirer = self._make_companies(db)
        db.commit()
        repo = AcquisitionScoreRepo(db)
        score = repo.upsert(
            target.id, acquirer.id,
            fit_score=0.78,
            timing_bucket="6-12m",
            affordability_score=0.85,
        )
        db.commit()
        assert score.fit_score == 0.78
        assert score.timing_bucket == "6-12m"

    def test_acquisition_score_no_duplicate(self, db):
        target, acquirer = self._make_companies(db)
        db.commit()
        repo = AcquisitionScoreRepo(db)
        repo.upsert(target.id, acquirer.id, fit_score=0.60)
        repo.upsert(target.id, acquirer.id, fit_score=0.80)
        db.commit()
        scores = db.query(AcquisitionScore).all()
        assert len(scores) == 1
        assert scores[0].fit_score == 0.80

    def test_top_targets_for_acquirer(self, db):
        acquirer = Company(name="MegaPharma", company_type="big_pharma")
        t1 = Company(name="Target1", company_type="public_biotech")
        t2 = Company(name="Target2", company_type="public_biotech")
        db.add_all([acquirer, t1, t2])
        db.flush()
        repo = AcquisitionScoreRepo(db)
        repo.upsert(t1.id, acquirer.id, fit_score=0.50)
        repo.upsert(t2.id, acquirer.id, fit_score=0.85)
        db.commit()
        top = repo.top_targets_for_acquirer(acquirer.id, limit=5)
        assert top[0].fit_score == 0.85  # highest first

    def test_top_acquirers_for_target(self, db):
        target = Company(name="BioTarget", company_type="public_biotech")
        a1 = Company(name="Acquirer1", company_type="big_pharma")
        a2 = Company(name="Acquirer2", company_type="big_pharma")
        db.add_all([target, a1, a2])
        db.flush()
        repo = AcquisitionScoreRepo(db)
        repo.upsert(target.id, a1.id, fit_score=0.70)
        repo.upsert(target.id, a2.id, fit_score=0.55)
        db.commit()
        ranked = repo.top_acquirers_for_target(target.id)
        assert ranked[0].fit_score == 0.70


# ---------------------------------------------------------------------------
# Relational integrity
# ---------------------------------------------------------------------------

class TestRelationalIntegrity:
    def test_asset_cascade_from_company(self, db):
        company = Company(name="Co", company_type="public_biotech")
        db.add(company)
        db.flush()
        asset = Asset(company_id=company.id, name="drug")
        db.add(asset)
        db.commit()
        fetched = db.get(Company, company.id)
        assert len(fetched.assets) == 1

    def test_variant_thesis_links_to_asset(self, db):
        company = Company(name="BioX", company_type="public_biotech")
        db.add(company)
        db.flush()
        asset = Asset(company_id=company.id, name="BX-101")
        db.add(asset)
        db.flush()
        thesis = VariantThesis(
            asset_id=asset.id,
            market_view={"implied_pos": 0.30},
            model_view={"model_pos": 0.55},
            confidence=0.70,
            documented=True,
        )
        db.add(thesis)
        db.commit()
        fetched = db.get(Asset, asset.id)
        assert len(fetched.variant_theses) == 1

    def test_parameter_version_links_to_decision(self, db):
        company = Company(name="BioZ", company_type="public_biotech")
        db.add(company)
        db.flush()
        asset = Asset(company_id=company.id, name="BZ-202")
        db.add(asset)
        db.flush()
        pv = ParameterVersion(name="base", version="1.0", weights={"pos": 0.5}, promoted=True)
        db.add(pv)
        db.flush()
        decision = DecisionRecord(
            asset_id=asset.id,
            decision_type="trade",
            recommendation={"action": "add", "size_pct": 2.0},
            parameter_version_id=pv.id,
        )
        db.add(decision)
        db.commit()
        assert decision.parameter_version.version == "1.0"

    def test_outcome_links_to_decision(self, db):
        company = Company(name="BioQ", company_type="public_biotech")
        db.add(company)
        db.flush()
        asset = Asset(company_id=company.id, name="BQ-303")
        db.add(asset)
        db.flush()
        decision = DecisionRecord(asset_id=asset.id, decision_type="trade")
        db.add(decision)
        db.flush()
        outcome = OutcomeRecord(
            decision_record_id=decision.id,
            realized_outcome={"return_pct": 12.5, "attribution": "confirmed_thesis"},
        )
        db.add(outcome)
        db.commit()
        assert decision.outcome.realized_outcome["return_pct"] == 12.5

    def test_competition_edge_between_assets(self, db):
        company = Company(name="BioGroup", company_type="public_biotech")
        db.add(company)
        db.flush()
        a1 = Asset(company_id=company.id, name="drug-A")
        a2 = Asset(company_id=company.id, name="drug-B")
        db.add_all([a1, a2])
        db.flush()
        edge = CompetitionEdge(
            source_asset_id=a1.id,
            target_asset_id=a2.id,
            edge_type="same_target",
            similarity=0.82,
        )
        db.add(edge)
        db.commit()
        assert edge.similarity == 0.82


# ---------------------------------------------------------------------------
# Constraint tests
# ---------------------------------------------------------------------------

class TestConstraints:
    def test_evidence_checksum_unique(self, db):
        import sqlalchemy.exc
        repo = EvidenceRepo(db)
        text = "Duplicate content."
        repo.store_if_new("press_release", text)
        db.commit()
        # Second store should return existing without raising
        _, is_new = repo.store_if_new("press_release", text)
        assert is_new is False

    def test_asset_unique_company_name_indication(self, db):
        import sqlalchemy.exc
        company = Company(name="UniCo", company_type="public_biotech")
        db.add(company)
        db.flush()
        a1 = Asset(company_id=company.id, name="drug-X", indication="NSCLC")
        db.add(a1)
        db.commit()
        # Same combination must fail
        a2 = Asset(company_id=company.id, name="drug-X", indication="NSCLC")
        db.add(a2)
        with pytest.raises(Exception):
            db.commit()

    def test_acquisition_score_unique_pair(self, db):
        target = Company(name="TgtCo", company_type="public_biotech")
        acq = Company(name="AcqCo", company_type="big_pharma")
        db.add_all([target, acq])
        db.flush()
        s1 = AcquisitionScore(target_company_id=target.id, acquirer_company_id=acq.id, fit_score=0.5)
        db.add(s1)
        db.commit()
        s2 = AcquisitionScore(target_company_id=target.id, acquirer_company_id=acq.id, fit_score=0.7)
        db.add(s2)
        with pytest.raises(Exception):
            db.commit()
