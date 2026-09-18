"""The alias index must answer exactly what the linear scan answered.

``AssetRegistry.ingest_hit`` used to find candidate matches by scanning every registered
asset and re-normalizing its whole alias list, once per hit. Replacing that with an index
is only safe if it returns the identical set for every input, including after merges and
unmerges move aliases between assets.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime

from bve.se.resolution.registry import AssetRegistry, normalize_identity_name
from bve.se.schemas.contracts import CandidateHit


def _linear_scan(registry: AssetRegistry, alias_keys: set[str]) -> set[str]:
    """The pre-index implementation, kept here as the reference answer."""

    return {
        asset_id
        for asset_id, record in registry.assets.items()
        if alias_keys
        & {
            normalized
            for normalized in (
                normalize_identity_name(value)
                for value in [record.canonical_name, *record.aliases]
            )
            if normalized
        }
    }


def _indexed(registry: AssetRegistry, alias_keys: set[str]) -> set[str]:
    return {
        asset_id
        for key in alias_keys
        for asset_id in registry._assets_by_alias_key.get(key, ())
    }


def _hit(n: int, name: str, aliases: list[str]) -> CandidateHit:
    return CandidateHit(
        hit_id=f"hit-{n}",
        asset_name=name,
        aliases=aliases,
        company_name=f"Co {n % 3}",
        trial_id=f"NCT{n:08d}",
        source="clinicaltrials_gov",
        query="q",
        applicable_as_of_date=datetime(2026, 8, 22, tzinfo=UTC).date(),
        source_document_id=f"doc-{n}",
        provisional_identity_key=f"prov-{n}",
        retrieved_at=datetime(2026, 8, 22, tzinfo=UTC),
        target_terms=["PDCD1"],
        modality_terms=["ANTIBODY"],
    )


class TestIndexMatchesTheLinearScan:
    def test_they_agree_on_every_hit_of_a_randomized_corpus(self):
        rng = random.Random(20260822)
        vocabulary = [f"drug-{i}" for i in range(40)]
        registry = AssetRegistry()

        for n in range(300):
            name = rng.choice(vocabulary)
            aliases = rng.sample(vocabulary, rng.randint(0, 3))
            hit = _hit(n, name, aliases)

            keys = {
                normalized
                for normalized in (
                    normalize_identity_name(v) for v in [hit.asset_name, *hit.aliases]
                )
                if normalized
            }
            assert _indexed(registry, keys) == _linear_scan(registry, keys), (
                f"index and scan disagree at hit {n}"
            )
            registry.ingest_hit(hit)

    def test_the_index_holds_no_key_pointing_at_a_forgotten_asset(self):
        rng = random.Random(7)
        registry = AssetRegistry()
        for n in range(60):
            registry.ingest_hit(
                _hit(n, f"drug-{rng.randint(0, 9)}", [f"alt-{rng.randint(0, 9)}"])
            )
        for key, holders in registry._assets_by_alias_key.items():
            for asset_id in holders:
                assert asset_id in registry.assets, f"{key} points at gone {asset_id}"
        # and every live asset is reachable by each of its own spellings
        for asset_id, record in registry.assets.items():
            for key in AssetRegistry._alias_keys(record):
                assert asset_id in registry._assets_by_alias_key[key]
