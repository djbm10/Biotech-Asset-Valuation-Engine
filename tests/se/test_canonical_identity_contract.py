"""One identity key space, published on the contract rather than re-derived by callers.

M16 exposed the defect. ``SB-773812`` received a CONFIRMED_TARGET assertion to HTR2A --
the engine found the molecule, resolved it, and attributed it correctly -- while the same
run's identification measurement recorded it as a miss. Nothing was wrong with either
subsystem on its own. They simply spoke different name spaces:

* ``IdentityMention.normalized_asset_name`` is ``normalize_identity_name(raw)``, so the
  mention reads ``sb773812``;
* ``CanonicalAsset.canonical_name`` is the display string ``SB-773812``.

Any consumer that joins an asset to a mention by name is therefore comparing a normalized
string to an unnormalized one, and silently loses every asset whose name contains
punctuation -- which is every development code. The registry already computes the right
keys internally in ``_alias_keys`` to drive its own alias index; they were simply never
published, so each caller had to guess the convention and the scorer guessed wrong.

The fix is a contract, not a special case: an asset carries ``identity_keys`` in exactly
the space mentions are normalized into, produced by the same function. These tests pin
that the two sides agree, for development codes and ordinary generic names alike, on
targets unrelated to any benchmark.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from bve.se.resolution.registry import AssetRegistry, normalize_identity_name
from bve.se.schemas.contracts import CandidateHit

# Neither molecule belongs to any benchmark: a hepatitis C polymerase inhibitor and an
# antifungal. If a fix reached only the drawn targets these would not move.
UNRELATED_CODE = "GS-9190"
UNRELATED_GENERIC = "Anidulafungin"


def _hit(name: str, *, hit_id: str = "hit:1", trial: str = "NCT1") -> CandidateHit:
    return CandidateHit(
        hit_id=hit_id,
        source="clinicaltrials_gov",
        source_document_id="doc:1",
        query="q",
        asset_name=name,
        trial_id=trial,
        aliases=[],
        provisional_identity_key=f"|{name}|{trial}",
        retrieved_at=datetime.now(timezone.utc),
        applicable_as_of_date=date(2026, 8, 24),
    )


def _ingest(name: str) -> tuple[AssetRegistry, object]:
    registry = AssetRegistry()
    asset = registry.ingest_hit(_hit(name))
    return registry, asset


class TestAnAssetPublishesItsIdentityKeys:
    def test_a_development_code_asset_carries_the_mention_key(self):
        """The exact SB-773812 shape: punctuation survives display, not the key."""

        registry, asset = _ingest(UNRELATED_CODE)
        mention = next(iter(registry.mentions.values()))

        assert asset.canonical_name == UNRELATED_CODE
        assert mention.normalized_asset_name in asset.identity_keys

    def test_a_generic_name_asset_carries_the_mention_key(self):
        registry, asset = _ingest(UNRELATED_GENERIC)
        mention = next(iter(registry.mentions.values()))

        assert mention.normalized_asset_name in asset.identity_keys

    def test_every_key_is_in_the_normalized_space(self):
        _, asset = _ingest(UNRELATED_CODE)

        assert asset.identity_keys
        for key in asset.identity_keys:
            assert normalize_identity_name(key) == key

    def test_published_keys_are_the_keys_the_registry_indexes_on(self):
        """One derivation. A second copy of this logic is the defect coming back."""

        registry, asset = _ingest(UNRELATED_CODE)

        assert set(asset.identity_keys) == set(registry._alias_keys(asset))


class TestJoiningAMentionToAnAssetByNameNowSucceeds:
    def test_the_display_name_alone_would_still_have_missed(self):
        """Records why the contract is needed rather than a tidier comparison."""

        _, asset = _ingest(UNRELATED_CODE)
        mention_key = normalize_identity_name(UNRELATED_CODE)

        assert mention_key not in {asset.canonical_name, *asset.aliases}
        assert mention_key in asset.identity_keys

    def test_separator_spellings_of_one_code_share_one_key(self):
        for spelling in (UNRELATED_CODE, "GS 9190", "GS9190"):
            _, asset = _ingest(spelling)
            assert normalize_identity_name(UNRELATED_CODE) in asset.identity_keys


class TestTheContractDoesNotDecideIdentity:
    def test_two_distinct_molecules_do_not_share_a_key(self):
        """Publishing keys must not merge anything. M11's rule is untouched."""

        _, code = _ingest(UNRELATED_CODE)
        _, generic = _ingest(UNRELATED_GENERIC)

        assert not set(code.identity_keys) & set(generic.identity_keys)

    def test_keys_carry_no_target_claim(self):
        _, asset = _ingest(UNRELATED_CODE)

        assert asset.target_ids == []
        assert asset.target_assertions == []
