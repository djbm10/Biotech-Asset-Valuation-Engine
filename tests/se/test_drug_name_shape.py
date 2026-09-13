"""A second, non-frequency route from prose token to asset mention.

The stem lexicon nominates a token when it ends in a suffix shared by at least 40 ontology
molecules. That threshold is what makes the rule target-agnostic, and it is frozen: it is
not lowered here. But it is structurally blind to a drug from a small class. HRH1 lost
KETOTIFEN and TRIPELENNAMINE to it; HTR2A lost EPLIVANSERIN and VOLINANSERIN. Adding
``anserin`` after reading that list would be hand-mapping.

So a token now reaches the extractor by either route:

1. it is a drug name the frozen ontology already knows, matched exactly; or
2. a classifier trained mechanically on the ontology's own molecules judges it
   drug-*shaped* at a threshold calibrated on held-out ontology data.

Route 2 never saw a benchmark molecule. Every gold, trap, sibling and target name of
PDCD1, SLC6A2, HRH1 and HTR2A was removed from its positives, its negatives, its training
set and its calibration set alike, so the molecules exercised below are recovered by
morphology the model learned somewhere else entirely.

Both routes nominate. Neither asserts a target, and neither decides identity.
"""

from __future__ import annotations

import pytest

from bve.se.discovery import drug_name_lexicon, drug_name_shape

# Recovered by shape alone. None of these was in the model's training or calibration data,
# and none ends in a stem the frozen lexicon admits.
STEM_INVISIBLE_DRUGS = [
    "eplivanserin",
    "volinanserin",
    "nelotanserin",
    "blonanserin",
    "ketotifen",
    "pyrilamine",
    "tripelennamine",
    "chlorprothixene",
]

# Ordinary biomedical prose of exactly the register the extractor runs against.
PROSE = [
    "receptor",
    "binding",
    "patients",
    "placebo",
    "expression",
    "antagonist",
    "randomized",
    "significant",
]


class TestTheStemRuleIsUnchanged:
    def test_the_frozen_threshold_is_not_lowered(self):
        """The new route is additive. If this moves, the old evidence is void."""

        assert drug_name_lexicon._lexicon()["thresholds"]["min_distinct_drug_names"] == 40

    def test_no_suffix_from_a_benchmark_was_added(self):
        for observed in ("anserin", "tifen", "cabastine", "thixene", "amine"):
            assert observed not in drug_name_lexicon.stems()


class TestShapeRecoversWhatFrequencyCannotSee:
    @pytest.mark.parametrize("name", STEM_INVISIBLE_DRUGS)
    def test_the_stem_rule_misses_it(self, name):
        assert not drug_name_lexicon.drug_name_pattern().fullmatch(name)

    @pytest.mark.parametrize("name", STEM_INVISIBLE_DRUGS)
    def test_the_shape_model_nominates_it(self, name):
        assert drug_name_shape.is_drug_shaped(name)

    @pytest.mark.parametrize("word", PROSE)
    def test_prose_is_not_nominated(self, word):
        assert not drug_name_shape.is_drug_shaped(word)


class TestTheModelIsFrozenAndArmsLength:
    def test_the_threshold_travels_inside_the_artifact(self):
        model = drug_name_shape._model()

        assert model["held_out_performance"]["threshold"] == drug_name_shape.threshold()
        assert model["declared_before_training"] is True

    def test_every_benchmark_target_was_excluded_from_training(self):
        excluded = drug_name_shape._model()["benchmark_exclusion"]["targets"]

        assert set(excluded) == {"PDCD1", "SLC6A2", "HRH1", "HTR2A"}

    def test_held_out_precision_meets_the_declared_target(self):
        performance = drug_name_shape._model()["held_out_performance"]

        assert performance["precision"] >= 0.95


class TestTheExactOntologyRouteIsSeparableFromTheLearnedOne:
    def test_a_molecule_the_model_cannot_see_is_still_known(self):
        """The residue the shape threshold leaves behind, recovered without lowering it."""

        for name in ("sarpogrelate", "iferanserin"):
            assert not drug_name_shape.is_drug_shaped(name)
            assert drug_name_shape.is_known_drug_name(name)
            assert drug_name_shape.nominates(name)

    def test_the_two_routes_are_asked_separately(self):
        """Reporting depends on being able to tell authority-seeded recovery apart."""

        assert drug_name_shape.is_drug_shaped("eplivanserin")
        assert not drug_name_shape.is_known_drug_name("notadrugatall")

    def test_the_artifact_declares_its_own_circularity(self):
        import json

        artifact = json.loads(drug_name_shape.KNOWN_NAMES_PATH.read_text())

        assert "ontology-derived" in artifact["provenance_note"].casefold()


class TestNominationIsNotIdentityAndNotATarget:
    def test_the_extractor_returns_a_bare_name(self):
        """Whatever comes back is a string. It carries no target and no asset id."""

        from bve.se.discovery.adapters import extract_observed_asset_names

        names = extract_observed_asset_names(
            "Eplivanserin was compared with placebo in patients with insomnia."
        )

        assert "Eplivanserin" in names
        assert all(isinstance(name, str) for name in names)

    def test_a_name_fragment_is_not_mined_out_of_a_longer_token(self):
        """``Dostarlimab-gxly`` is one name. Reading a shorter name out of it invents one."""

        from bve.se.discovery.adapters import extract_observed_asset_names

        names = extract_observed_asset_names("Dostarlimab-gxly was administered.")

        assert "Dostarlimab" not in names

    def test_the_alias_route_does_not_mine_words_from_a_description(self):
        """M11's rule. A structural description asserts nothing about any word inside it."""

        from bve.se.discovery.adapters import extract_observed_asset_names

        description = "Disulfide with Humanized Clone ABT1 Kappa-chain, Dimer"

        assert extract_observed_asset_names(description, shape_scan=False) == []

    def test_two_shaped_names_in_one_sentence_stay_two_mentions(self):
        from bve.se.discovery.adapters import extract_observed_asset_names

        names = extract_observed_asset_names("Ketotifen and pyrilamine were both studied.")

        assert len({n.casefold() for n in names}) == 2
