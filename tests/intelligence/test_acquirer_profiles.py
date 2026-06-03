from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from bve.intelligence.acquirer_profiles import (
    AcquirerProfileLoader,
    BudgetSnapshot,
    CuratedAcquirerProfile,
    ExistingPartnership,
    RecentDeal,
)


def test_acquirer_profile_loader_parses_repository_yaml():
    path = Path("research/mna/pipeline_gaps.yaml")

    dataset = AcquirerProfileLoader.load(path)
    regeneron = AcquirerProfileLoader.get_acquirer(dataset, "ReGeNeRoN")

    assert dataset.as_of_date.isoformat() == "2026-05-08"
    assert len(dataset.acquirers) >= 4
    assert regeneron.company_name == "Regeneron Pharmaceuticals"
    assert regeneron.budget.net_cash_millions == pytest.approx(16553.7, abs=1e-9)
    assert len(regeneron.therapeutic_area_gaps) >= 4
    assert regeneron.recent_deal_history[0].deal_name == (
        "Telix Pharmaceuticals radiopharmaceutical collaboration"
    )


def test_acquirer_profile_loader_parses_curated_pfizer_profile():
    path = Path("examples/research/acquirer_profiles/pfizer.yaml")

    dataset = AcquirerProfileLoader.load(path)
    pfizer = AcquirerProfileLoader.get_acquirer(dataset, "pfizer")

    assert pfizer.company_name == "Pfizer"
    assert pfizer.ticker == "PFE"
    assert pfizer.market_cap_billions == pytest.approx(145.0, abs=1e-9)
    assert pfizer.cash_billions == pytest.approx(12.5, abs=1e-9)
    assert pfizer.therapeutic_area_gaps[0].sub_area == "breast_cancer"
    assert pfizer.therapeutic_area_gaps[0].preferred_modality == ["small_molecule", "ADC"]
    assert pfizer.therapeutic_area_gaps[0].budget_ceiling_millions == pytest.approx(15000.0, abs=1e-9)
    assert pfizer.recent_deal_history[0].deal_name == "Seagen"


def test_acquirer_profile_loader_supports_curated_profile_directories():
    dataset = AcquirerProfileLoader.load(Path("examples/research/acquirer_profiles"))
    pfizer = AcquirerProfileLoader.get_acquirer(dataset, "pfizer")
    lilly = AcquirerProfileLoader.get_acquirer(dataset, "eli_lilly")
    novo = AcquirerProfileLoader.get_acquirer(dataset, "novo_nordisk")

    assert len(dataset.acquirers) >= 3
    assert pfizer.company_name == "Pfizer"
    assert lilly.company_name == "Eli Lilly"
    assert novo.company_name == "Novo Nordisk"


def test_curated_profile_can_omit_balance_sheet_fields_and_derives_budget_from_gap_ceiling():
    dataset = AcquirerProfileLoader.load(Path("examples/research/acquirer_profiles/lilly.yaml"))
    lilly = AcquirerProfileLoader.get_acquirer(dataset, "eli_lilly")

    assert lilly.market_cap_billions is None
    assert lilly.cash_billions is None
    assert lilly.budget.net_cash_millions == pytest.approx(30000.0, abs=1e-9)
    assert "largest per-gap budget ceiling" in lilly.budget.capacity_notes


def test_acquirer_profile_loader_rejects_duplicate_acquirer_ids(tmp_path: Path):
    path = tmp_path / "pipeline_gaps.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "as_of_date": "2026-03-24",
                "acquirers": [
                    _profile("regeneron"),
                    _profile("REGENERON"),
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        AcquirerProfileLoader.load(path)


def test_budget_snapshot_requires_consistent_net_cash():
    with pytest.raises(ValidationError):
        BudgetSnapshot.model_validate(
            {
                "as_of_date": "2025-12-31",
                "cash_and_marketable_securities_millions": 100.0,
                "long_term_debt_millions": 30.0,
                "net_cash_millions": 80.0,
                "capacity_notes": "Example",
                "source_refs": [_source_ref()],
            }
        )


def test_recent_deal_rejects_inverted_value_band():
    with pytest.raises(ValidationError):
        RecentDeal.model_validate(
            {
                "deal_name": "Example deal",
                "status": "announced",
                "announcement_date": "2025-05-01",
                "deal_type": "license",
                "therapeutic_area": "oncology",
                "modality": "antibody",
                "stage_context": "phase_2",
                "implied_value_band_millions_low": 500.0,
                "implied_value_band_millions_high": 400.0,
                "source_url": "https://example.com/deal",
            }
        )


def test_get_acquirer_raises_for_unknown_id(tmp_path: Path):
    path = tmp_path / "pipeline_gaps.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "as_of_date": "2026-03-24",
                "acquirers": [_profile("regeneron")],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(KeyError):
        AcquirerProfileLoader.get_acquirer(path, "unknown")


def _profile(acquirer_id: str) -> dict[str, object]:
    return {
        "acquirer_id": acquirer_id,
        "company_name": "Regeneron Pharmaceuticals",
        "ticker": "REGN",
        "profile_as_of": "2026-03-24",
        "source_notes": "Example profile",
        "therapeutic_area_gaps": [
            {
                "therapeutic_area": "ophthalmology",
                "exposure_type": "loe_and_franchise_defense",
                "exposure_level": "high",
                "rationale": "Example rationale",
                "source_refs": [_source_ref()],
            }
        ],
        "preferred_modalities": [
            {
                "modality": "fully_human_antibody",
                "preference_strength": "high",
                "rationale": "Example rationale",
                "source_refs": [_source_ref()],
            }
        ],
        "strategic_priorities": [
            {
                "priority": "Complementary BD only",
                "priority_strength": "high",
                "source_refs": [_source_ref()],
            }
        ],
        "recent_deal_history": [
            {
                "deal_name": "Example deal",
                "status": "completed",
                "announcement_date": "2025-05-01",
                "deal_type": "license",
                "therapeutic_area": "ophthalmology",
                "modality": "antibody",
                "stage_context": "phase_2",
                "upfront_millions": 100.0,
                "implied_value_band_millions_low": 100.0,
                "implied_value_band_millions_high": 200.0,
                "source_url": "https://example.com/deal",
            }
        ],
        "budget": {
            "as_of_date": "2025-12-31",
            "cash_and_marketable_securities_millions": 100.0,
            "long_term_debt_millions": 20.0,
            "net_cash_millions": 80.0,
            "capacity_notes": "Example capacity notes",
            "source_refs": [_source_ref()],
        },
    }


def _source_ref() -> dict[str, str]:
    return {
        "source_date": "2026-01-30",
        "source_type": "earnings_release",
        "source_title": "Example source",
        "source_url": "https://example.com/source",
        "note": "Example note",
    }


# ---------------------------------------------------------------------------
# Step 6: existing_partnerships + acquisition_capacity_millions
# ---------------------------------------------------------------------------

def test_existing_partnerships_parsed_from_takeda_profile():
    dataset = AcquirerProfileLoader.load(
        Path("examples/research/acquirer_profiles/takeda.yaml")
    )
    takeda = AcquirerProfileLoader.get_acquirer(dataset, "takeda_pharmaceutical")
    # Takeda profile has 3 partnerships and explicit acquisition capacity.
    assert takeda.company_name == "Takeda Pharmaceutical"
    assert takeda.ticker == "TAK"
    assert len(takeda.existing_partnerships) == 3
    assert takeda.acquisition_capacity_millions == pytest.approx(15000.0)


def test_daiichi_sankyo_profile_parses():
    dataset = AcquirerProfileLoader.load(
        Path("examples/research/acquirer_profiles/daiichi_sankyo.yaml")
    )
    dss = AcquirerProfileLoader.get_acquirer(dataset, "daiichi_sankyo")
    assert dss.company_name == "Daiichi Sankyo"
    assert dss.ticker == "DSNKY"
    assert len(dss.therapeutic_area_gaps) >= 3


def test_curated_profile_existing_partnerships_field_is_optional():
    """Profiles without existing_partnerships load cleanly (field defaults to [])."""
    dataset = AcquirerProfileLoader.load(
        Path("examples/research/acquirer_profiles/abbvie.yaml")
    )
    # AbbVie profile has no existing_partnerships — should load without error
    abbvie = AcquirerProfileLoader.get_acquirer(dataset, "abbvie")
    assert abbvie.company_name == "AbbVie"


def test_curated_profile_acquisition_capacity_field():
    """acquisition_capacity_millions is stored and accessible on CuratedAcquirerProfile."""
    profile = CuratedAcquirerProfile(
        company="Test Corp",
        ticker="TEST",
        market_cap_billions=50.0,
        cash_billions=5.0,
        acquisition_capacity_millions=8000.0,
        pipeline_gaps=[
            {
                "therapeutic_area": "oncology",
                "sub_area": "solid_tumor",
                "gap_type": "franchise_extension",
                "urgency": "high",
                "preferred_modality": ["small_molecule"],
                "budget_ceiling_millions": 8000.0,
                "notes": "test",
            }
        ],
        stated_priorities=["Grow oncology portfolio"],
    )
    assert profile.acquisition_capacity_millions == pytest.approx(8000.0)


def test_existing_partnership_model_validates():
    """ExistingPartnership Pydantic model validates required fields."""
    p = ExistingPartnership(
        target="KYMR",
        partnership_type="co_development",
        therapeutic_area="immunology",
        description="KT-474 co-development for atopic dermatitis",
        year_initiated=2022,
        acquisition_option=True,
    )
    assert p.target == "KYMR"
    assert p.acquisition_option is True


def test_existing_partnership_acquisition_option_defaults_to_false():
    p = ExistingPartnership(
        target="ARVN",
        partnership_type="licensing_in",
        therapeutic_area="oncology",
        description="ARV-471 co-commercialization",
    )
    assert p.acquisition_option is False


def test_curated_profile_existing_partnerships_accessible():
    """CuratedAcquirerProfile stores and returns existing_partnerships list."""
    profile = CuratedAcquirerProfile(
        company="TestPharma",
        ticker="TP",
        pipeline_gaps=[
            {
                "therapeutic_area": "oncology",
                "sub_area": "adc",
                "gap_type": "franchise_extension",
                "urgency": "high",
                "preferred_modality": ["ADC"],
                "budget_ceiling_millions": 5000.0,
            }
        ],
        existing_partnerships=[
            {
                "target": "SRRK",
                "partnership_type": "option_to_acquire",
                "therapeutic_area": "neuromuscular",
                "description": "Apitegromab option agreement",
                "year_initiated": 2024,
                "acquisition_option": True,
            }
        ],
    )
    assert len(profile.existing_partnerships) == 1
    assert profile.existing_partnerships[0].target == "SRRK"
    assert profile.existing_partnerships[0].acquisition_option is True


def test_takeda_existing_partnerships_loaded_from_curated_yaml():
    """Takeda profile has existing_partnerships in YAML — verify they parse via the raw loader."""
    import yaml
    with open("examples/research/acquirer_profiles/takeda.yaml") as f:
        raw = yaml.safe_load(f)
    profile = CuratedAcquirerProfile(**raw)
    # Takeda has Protagonist + Ovid + Galapagos partnerships
    assert len(profile.existing_partnerships) == 3
    partners = {p.target for p in profile.existing_partnerships}
    assert "Ovid Therapeutics" in partners


def test_daiichi_sankyo_partnerships_all_have_descriptions():
    import yaml
    with open("examples/research/acquirer_profiles/daiichi_sankyo.yaml") as f:
        raw = yaml.safe_load(f)
    profile = CuratedAcquirerProfile(**raw)
    assert len(profile.existing_partnerships) >= 2
    for p in profile.existing_partnerships:
        assert len(p.description.strip()) > 10


def test_directory_load_includes_new_profiles():
    """Loading full directory includes Takeda and Daiichi Sankyo."""
    dataset = AcquirerProfileLoader.load(Path("examples/research/acquirer_profiles"))
    acquirer_ids = {a.acquirer_id for a in dataset.acquirers}
    assert "takeda_pharmaceutical" in acquirer_ids
    assert "daiichi_sankyo" in acquirer_ids
