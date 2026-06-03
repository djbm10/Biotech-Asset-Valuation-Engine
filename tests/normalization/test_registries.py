"""Tests for canonical registries — YAML integrity and coverage."""
import pytest
from bve.normalization.registries import (
    INDICATION_ALIAS_MAP,
    INDICATION_REGISTRY,
    MOA_ALIAS_MAP,
    MOA_REGISTRY,
    TARGET_ALIAS_MAP,
    TARGET_REGISTRY,
)


class TestIndicationRegistry:
    def test_loads_non_empty(self):
        assert len(INDICATION_REGISTRY) > 20

    def test_all_ids_present_in_alias_map(self):
        for cid, entry in INDICATION_REGISTRY.items():
            # Every entry must have at least one alias in the map that points back to it
            assert any(
                v == cid for v in INDICATION_ALIAS_MAP.values()
            ), f"{cid} has no alias in alias map"

    def test_no_empty_aliases(self):
        for cid, entry in INDICATION_REGISTRY.items():
            assert entry.aliases, f"{cid} has no aliases"
            for alias in entry.aliases:
                assert alias.strip(), f"{cid} has blank alias"

    def test_no_duplicate_aliases(self):
        # Each alias must map to exactly one canonical_id (enforced during load)
        # Verify the map was built without conflicts
        seen: dict[str, str] = {}
        for alias, cid in INDICATION_ALIAS_MAP.items():
            if alias in seen:
                assert seen[alias] == cid, f"Alias '{alias}' maps to two IDs"
            seen[alias] = cid

    def test_all_have_therapeutic_area(self):
        for cid, entry in INDICATION_REGISTRY.items():
            assert entry.therapeutic_area is not None, f"{cid} missing therapeutic_area"

    def test_known_indication_id_present(self):
        assert "IND_ulcerative_colitis" in INDICATION_REGISTRY
        assert "IND_nsclc" in INDICATION_REGISTRY
        assert "IND_melanoma" in INDICATION_REGISTRY

    def test_known_aliases_in_map(self):
        assert "ulcerative colitis" in INDICATION_ALIAS_MAP
        assert "uc" in INDICATION_ALIAS_MAP
        assert "nsclc" in INDICATION_ALIAS_MAP


class TestTargetRegistry:
    def test_loads_non_empty(self):
        assert len(TARGET_REGISTRY) > 10

    def test_pd1_present(self):
        assert "TGT_pd1" in TARGET_REGISTRY
        assert "pd-1" in TARGET_ALIAS_MAP
        assert "pd1" in TARGET_ALIAS_MAP

    def test_no_empty_aliases(self):
        for cid, entry in TARGET_REGISTRY.items():
            assert entry.aliases, f"{cid} has no aliases"


class TestMOARegistry:
    def test_loads_non_empty(self):
        assert len(MOA_REGISTRY) > 10

    def test_checkpoint_inhibitor_present(self):
        assert "MOA_pd1_checkpoint_inhibitor" in MOA_REGISTRY
        assert "checkpoint inhibitor" in MOA_ALIAS_MAP

    def test_no_empty_aliases(self):
        for cid, entry in MOA_REGISTRY.items():
            assert entry.aliases, f"{cid} has no aliases"


class TestYAMLCoverageOfDealData:
    """Every indication in comparable_deals.yaml should resolve to at least MEDIUM."""

    def test_all_deal_indications_normalize(self):
        from pathlib import Path
        import yaml
        from bve.normalization.normalizer import IndicationNormalizer

        yaml_path = (
            Path(__file__).parent.parent.parent
            / "research" / "mna" / "comparable_deals.yaml"
        )
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        deals = raw.get("deals", raw) if isinstance(raw, dict) else raw

        norm = IndicationNormalizer()
        failures: list[str] = []
        for deal in deals:
            indication = deal.get("indication", "")
            result = norm.normalize(indication)
            if not result.is_trustworthy:
                failures.append(f"{indication!r} → {result.confidence} (score={result.match_score:.1f})")

        assert not failures, (
            f"{len(failures)} indication(s) failed normalization:\n"
            + "\n".join(f"  - {f}" for f in failures)
        )
