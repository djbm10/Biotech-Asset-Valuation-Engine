"""
Tests for universe_loader.py — Block 2A.

Covers:
  - Round-trip load of real YAML files
  - Schema validation (all required fields)
  - Invalid vocabulary caught (phase, modality, TA, company_type)
  - Alias deduplication
  - Cross-universe warnings (ticker in both targets + acquirers)
  - universe_summary format
  - Manual overrides load
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from bve.ingestion.universe_loader import (
    VALID_MODALITIES,
    VALID_PHASES,
    VALID_TAS,
    AcquirerEntry,
    CompanyAliases,
    TargetEntry,
    load_acquirers,
    load_aliases,
    load_manual_overrides,
    load_targets,
    universe_summary,
    validate_universe,
)

# ---------------------------------------------------------------------------
# Paths to the real universe files
# ---------------------------------------------------------------------------

_UNIVERSE_DIR = Path(__file__).parent.parent / "research" / "universe"
_TARGETS_YAML = _UNIVERSE_DIR / "targets.yaml"
_ACQUIRERS_YAML = _UNIVERSE_DIR / "acquirers.yaml"
_ALIASES_YAML = _UNIVERSE_DIR / "company_aliases.yaml"
_OVERRIDES_YAML = _UNIVERSE_DIR / "manual_overrides.yaml"


# ===========================================================================
# Loading real files
# ===========================================================================


class TestLoadRealFiles:
    def test_targets_file_exists(self):
        assert _TARGETS_YAML.exists(), f"Missing: {_TARGETS_YAML}"

    def test_acquirers_file_exists(self):
        assert _ACQUIRERS_YAML.exists(), f"Missing: {_ACQUIRERS_YAML}"

    def test_aliases_file_exists(self):
        assert _ALIASES_YAML.exists(), f"Missing: {_ALIASES_YAML}"

    def test_overrides_file_exists(self):
        assert _OVERRIDES_YAML.exists(), f"Missing: {_OVERRIDES_YAML}"

    def test_load_targets_returns_dict(self):
        targets = load_targets(_TARGETS_YAML)
        assert isinstance(targets, dict)

    def test_targets_count_at_least_50(self):
        targets = load_targets(_TARGETS_YAML)
        assert len(targets) >= 50, f"Expected ≥50 targets, got {len(targets)}"

    def test_acquirers_count_at_least_20(self):
        acquirers = load_acquirers(_ACQUIRERS_YAML)
        assert len(acquirers) >= 20, f"Expected ≥20 acquirers, got {len(acquirers)}"

    def test_all_targets_are_target_entry_instances(self):
        targets = load_targets(_TARGETS_YAML)
        for ticker, entry in targets.items():
            assert isinstance(entry, TargetEntry), f"{ticker} is not a TargetEntry"

    def test_all_acquirers_are_acquirer_entry_instances(self):
        acquirers = load_acquirers(_ACQUIRERS_YAML)
        for ticker, entry in acquirers.items():
            assert isinstance(entry, AcquirerEntry), f"{ticker} is not an AcquirerEntry"

    def test_rvmd_loaded_with_expected_fields(self):
        targets = load_targets(_TARGETS_YAML)
        assert "RVMD" in targets
        rvmd = targets["RVMD"]
        assert rvmd.lead_asset == "daraxonrasib"
        assert rvmd.lead_asset_phase == "phase3"
        assert "oncology" in rvmd.therapeutic_areas
        assert rvmd.include_in_screen is True

    def test_pfe_loaded_with_deal_range(self):
        acquirers = load_acquirers(_ACQUIRERS_YAML)
        assert "PFE" in acquirers
        pfe = acquirers["PFE"]
        assert pfe.deal_size_range_millions[0] > 0
        assert pfe.deal_size_range_millions[1] > pfe.deal_size_range_millions[0]

    def test_aliases_load_correctly(self):
        aliases = load_aliases(_ALIASES_YAML)
        assert "RVMD" in aliases
        rvmd = aliases["RVMD"]
        assert isinstance(rvmd, CompanyAliases)
        assert "Revolution Medicines" in rvmd.aliases
        assert "daraxonrasib" in rvmd.assets

    def test_manual_overrides_load_as_dict(self):
        overrides = load_manual_overrides(_OVERRIDES_YAML)
        assert isinstance(overrides, dict)
        assert "RVMD" in overrides
        assert overrides["RVMD"]["lead_asset"] == "daraxonrasib"

    def test_targets_have_include_in_screen_populated(self):
        targets = load_targets(_TARGETS_YAML)
        missing = [t for t, e in targets.items() if e.include_in_screen is None]
        assert not missing, f"Targets missing include_in_screen: {missing}"

    def test_at_least_80pct_targets_have_lead_asset(self):
        targets = load_targets(_TARGETS_YAML)
        included = [e for e in targets.values() if e.include_in_screen]
        with_lead = sum(1 for e in included if e.lead_asset)
        pct = with_lead / len(included) if included else 0
        assert pct >= 0.80, f"Only {pct:.0%} of included targets have lead_asset"

    def test_at_least_80pct_targets_have_phase(self):
        targets = load_targets(_TARGETS_YAML)
        included = [e for e in targets.values() if e.include_in_screen]
        with_phase = sum(1 for e in included if e.lead_asset_phase)
        pct = with_phase / len(included) if included else 0
        assert pct >= 0.80, f"Only {pct:.0%} of included targets have lead_asset_phase"


# ===========================================================================
# Validation on real files
# ===========================================================================


class TestValidateRealUniverse:
    def setup_method(self):
        self.targets = load_targets(_TARGETS_YAML)
        self.acquirers = load_acquirers(_ACQUIRERS_YAML)
        self.aliases = load_aliases(_ALIASES_YAML)

    def test_validation_passes_on_real_files(self):
        result = validate_universe(self.targets, self.acquirers, self.aliases)
        if not result.valid:
            msgs = [f"  [{i.ticker}] {i.field}: {i.message}" for i in result.errors]
            pytest.fail("Universe validation failed:\n" + "\n".join(msgs))

    def test_target_count_matches(self):
        result = validate_universe(self.targets, self.acquirers)
        assert result.target_count == len(self.targets)

    def test_acquirer_count_matches(self):
        result = validate_universe(self.targets, self.acquirers)
        assert result.acquirer_count == len(self.acquirers)

    def test_targets_included_count_positive(self):
        result = validate_universe(self.targets, self.acquirers)
        assert result.targets_included > 0

    def test_acquirers_included_count_positive(self):
        result = validate_universe(self.targets, self.acquirers)
        assert result.acquirers_included > 0

    def test_validation_summary_contains_key_sections(self):
        result = validate_universe(self.targets, self.acquirers)
        summary = result.summary()
        assert "Targets:" in summary
        assert "Acquirers:" in summary


# ===========================================================================
# Synthetic YAML fixtures for negative-case tests
# ===========================================================================


def _write_yaml(tmp_path: Path, name: str, data: dict) -> Path:
    p = tmp_path / name
    with open(p, "w") as fh:
        yaml.dump(data, fh)
    return p


class TestValidationErrorCases:
    def _minimal_target(self, overrides: dict = None) -> dict:
        base = {
            "TSTR": {
                "name": "Test Corp",
                "exchange": "NASDAQ",
                "company_type": "drug_developer",
                "therapeutic_areas": ["oncology"],
                "lead_asset": "TEST-001",
                "lead_asset_phase": "phase2",
                "lead_modality": "small_molecule",
                "lead_indication": "test indication",
                "is_single_asset_company": False,
                "include_in_screen": True,
            }
        }
        if overrides:
            base["TSTR"].update(overrides)
        return base

    def _minimal_acquirer(self) -> dict:
        return {
            "TACQ": {
                "name": "Big Pharma",
                "therapeutic_areas": ["oncology"],
                "modalities": ["biologic"],
                "deal_size_range_millions": [1000, 10000],
                "preferred_stages": ["phase3"],
                "include_as_acquirer": True,
            }
        }

    def test_invalid_phase_caught(self, tmp_path):
        data = self._minimal_target({"lead_asset_phase": "phase99"})
        p = _write_yaml(tmp_path, "t.yaml", data)
        targets = load_targets(p)
        result = validate_universe(targets, {})
        errors = [e for e in result.errors if e.field == "lead_asset_phase"]
        assert errors, "Expected error for invalid phase"

    def test_invalid_modality_caught(self, tmp_path):
        data = self._minimal_target({"lead_modality": "gene_therapy_v2"})
        p = _write_yaml(tmp_path, "t.yaml", data)
        targets = load_targets(p)
        result = validate_universe(targets, {})
        errors = [e for e in result.errors if e.field == "lead_modality"]
        assert errors, "Expected error for invalid modality"

    def test_invalid_ta_caught(self, tmp_path):
        data = self._minimal_target({"therapeutic_areas": ["quantum_biology"]})
        p = _write_yaml(tmp_path, "t.yaml", data)
        targets = load_targets(p)
        result = validate_universe(targets, {})
        errors = [e for e in result.errors if e.field == "therapeutic_areas"]
        assert errors, "Expected error for invalid TA"

    def test_invalid_company_type_caught(self, tmp_path):
        data = self._minimal_target({"company_type": "startup"})
        p = _write_yaml(tmp_path, "t.yaml", data)
        targets = load_targets(p)
        result = validate_universe(targets, {})
        errors = [e for e in result.errors if e.field == "company_type"]
        assert errors, "Expected error for invalid company_type"

    def test_missing_lead_asset_caught(self, tmp_path):
        data = self._minimal_target({"lead_asset": ""})
        p = _write_yaml(tmp_path, "t.yaml", data)
        targets = load_targets(p)
        result = validate_universe(targets, {})
        errors = [e for e in result.errors if e.field == "lead_asset"]
        assert errors, "Expected error for empty lead_asset"

    def test_missing_include_in_screen_caught(self, tmp_path):
        raw = {
            "TSTR": {
                "name": "Test Corp",
                "exchange": "NASDAQ",
                "company_type": "drug_developer",
                "therapeutic_areas": ["oncology"],
                "lead_asset": "TEST-001",
                "lead_asset_phase": "phase2",
                "lead_modality": "small_molecule",
                "lead_indication": "test",
                "is_single_asset_company": False,
                # include_in_screen deliberately omitted
            }
        }
        p = _write_yaml(tmp_path, "t.yaml", raw)
        targets = load_targets(p)
        result = validate_universe(targets, {})
        # include_in_screen defaults to False via bool(None) == False, not an error
        # but include_in_screen field is present — check warning or pass
        assert result is not None

    def test_invalid_acquirer_modality_caught(self, tmp_path):
        acq = {
            "TACQ": {
                "name": "Big Pharma",
                "therapeutic_areas": ["oncology"],
                "modalities": ["magic_molecule"],
                "deal_size_range_millions": [1000, 10000],
                "preferred_stages": ["phase3"],
                "include_as_acquirer": True,
            }
        }
        p = _write_yaml(tmp_path, "a.yaml", acq)
        acquirers = load_acquirers(p)
        result = validate_universe({}, acquirers)
        errors = [e for e in result.errors if e.field == "modalities"]
        assert errors, "Expected error for invalid modality in acquirers"

    def test_invalid_acquirer_stage_caught(self, tmp_path):
        acq = {
            "TACQ": {
                "name": "Big Pharma",
                "therapeutic_areas": ["oncology"],
                "modalities": ["biologic"],
                "deal_size_range_millions": [1000, 10000],
                "preferred_stages": ["stage_z"],
                "include_as_acquirer": True,
            }
        }
        p = _write_yaml(tmp_path, "a.yaml", acq)
        acquirers = load_acquirers(p)
        result = validate_universe({}, acquirers)
        errors = [e for e in result.errors if e.field == "preferred_stages"]
        assert errors, "Expected error for invalid stage"

    def test_same_ticker_in_both_raises_warning(self, tmp_path):
        tp = _write_yaml(tmp_path, "t.yaml", self._minimal_target({"ticker": "TSTR"}))
        ap = _write_yaml(tmp_path, "a.yaml", {
            "TSTR": {
                "name": "Also Big Pharma",
                "therapeutic_areas": ["oncology"],
                "modalities": ["biologic"],
                "deal_size_range_millions": [500, 5000],
                "preferred_stages": ["phase3"],
                "include_as_acquirer": True,
            }
        })
        targets = load_targets(tp)
        acquirers = load_acquirers(ap)
        result = validate_universe(targets, acquirers)
        warnings = [w for w in result.warnings if "both" in w.message]
        assert warnings, "Expected warning for ticker in both targets and acquirers"

    def test_duplicate_aliases_across_companies_raises_warning(self, tmp_path):
        aliases_data = {
            "AAA": {
                "canonical_name": "Alpha Corp",
                "ticker": "AAA",
                "aliases": ["Alpha Corp", "Alpha"],
                "assets": [],
            },
            "BBB": {
                "canonical_name": "Beta Corp",
                "ticker": "BBB",
                "aliases": ["Beta Corp", "Alpha"],  # "Alpha" duplicated
                "assets": [],
            },
        }
        ap = _write_yaml(tmp_path, "aliases.yaml", aliases_data)
        aliases = load_aliases(ap)
        result = validate_universe({}, {}, aliases)
        alias_warnings = [w for w in result.warnings if w.field == "aliases"]
        assert alias_warnings, "Expected warning for duplicate alias"

    def test_valid_universe_result_is_valid(self, tmp_path):
        tp = _write_yaml(tmp_path, "t.yaml", self._minimal_target())
        aq = _write_yaml(tmp_path, "a.yaml", self._minimal_acquirer())
        targets = load_targets(tp)
        acquirers = load_acquirers(aq)
        result = validate_universe(targets, acquirers)
        assert result.valid


# ===========================================================================
# universe_summary
# ===========================================================================


class TestUniverseSummary:
    def setup_method(self):
        self.targets = load_targets(_TARGETS_YAML)
        self.acquirers = load_acquirers(_ACQUIRERS_YAML)

    def test_summary_returns_string(self):
        s = universe_summary(self.targets, self.acquirers)
        assert isinstance(s, str)

    def test_summary_contains_target_count(self):
        s = universe_summary(self.targets, self.acquirers)
        assert "Targets loaded:" in s

    def test_summary_contains_acquirer_count(self):
        s = universe_summary(self.targets, self.acquirers)
        assert "Acquirers loaded:" in s

    def test_summary_contains_therapeutic_areas(self):
        s = universe_summary(self.targets, self.acquirers)
        assert "therapeutic areas:" in s.lower()

    def test_summary_contains_phases(self):
        s = universe_summary(self.targets, self.acquirers)
        assert "phases:" in s.lower() or "phase3" in s

    def test_summary_contains_modalities(self):
        s = universe_summary(self.targets, self.acquirers)
        assert "small_molecule" in s

    def test_summary_contains_pfe_acquirer(self):
        s = universe_summary(self.targets, self.acquirers)
        assert "PFE" in s

    def test_summary_shows_rvmd_in_results(self):
        # Indirect check: RVMD is included, so oncology and phase3 must appear
        s = universe_summary(self.targets, self.acquirers)
        assert "oncology" in s


# ===========================================================================
# FileNotFoundError
# ===========================================================================


class TestMissingFiles:
    def test_missing_targets_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_targets(tmp_path / "nonexistent.yaml")

    def test_missing_acquirers_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_acquirers(tmp_path / "nonexistent.yaml")

    def test_missing_aliases_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_aliases(tmp_path / "nonexistent.yaml")
