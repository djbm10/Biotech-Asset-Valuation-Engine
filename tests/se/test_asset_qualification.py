"""What earns a prose token the right to be called an asset and carry a decision.

The human proof-of-concept stage was the first to hand a nominated name a decisive PASS,
and doing so exposed what the identity layer had been willing to call an asset: `although`,
`before`, `baseline`, `months`, `Euroflow`, `IQR`. Each of those really does appear in a
sentence reporting efficacy -- because the "name" is an ordinary English word, and ordinary
English words appear in every sentence. Attribution was correct; the identity was not.

Frequency cannot be the qualification, because the commonest words are the most frequent
things in any corpus. Shape cannot be it either: the drug-shape model scores `although`,
`baseline` and `benzhexol` alike, and it is right to, since it was built for recall over a
space where real molecules are unevenly spelled. What distinguishes a molecule from a word
is that documents *treat it as a drug* -- patients receive it, it inhibits something, it is
given at a dose. That is positive asset evidence, and it is what an unknown token has to
show.

The test that matters is the second class below. A rule that rejects the six observed bad
words is worth nothing if it also rejects `benzhexol`, which is a real drug the ontology
simply does not carry.
"""

from __future__ import annotations

import pytest

from bve.se.discovery.asset_qualification import (
    AssetEvidence,
    document_frequencies,
    has_pharmacologic_context,
    is_development_code,
    qualifies_as_asset,
)
from bve.se.discovery.mention_support import (
    MentionDisposition,
    classify_mention_support,
)

#: Ordinary prose the engine promoted to decision-bearing assets on the sealed corpus.
OBSERVED_JUNK = ["although", "before", "baseline", "Euroflow", "IQR"]

#: Real molecules the ontology does not carry. These are the reason a blacklist is not an
#: answer and a support threshold is not an answer.
ONTOLOGY_MISSING_DRUGS = ["benzhexol", "ibritumomab", "lestaurinib"]


class TestFrequencyIsNotEvidence:
    @pytest.mark.parametrize("name", OBSERVED_JUNK)
    def test_a_common_word_cannot_qualify_on_repetition_alone(self, name) -> None:
        # Appearing in a hundred documents is what common words do.
        assert not qualifies_as_asset(AssetEvidence(name=name, support=100))

    @pytest.mark.parametrize("name", OBSERVED_JUNK)
    def test_a_common_word_stays_off_the_default_path(self, name) -> None:
        disposition = classify_mention_support(name, support=100)
        assert disposition is MentionDisposition.LOW_SUPPORT_UNKNOWN

    @pytest.mark.parametrize("name", OBSERVED_JUNK)
    def test_sitting_in_an_efficacy_sentence_is_not_asset_evidence(self, name) -> None:
        # The exact failure: the sentence reports a real result, about something else.
        text = f"Overall response rate was 75% at {name} assessment in 9 of 12 patients."
        assert not has_pharmacologic_context(text, name)


class TestRealMoleculesSurviveWithoutTheOntology:
    @pytest.mark.parametrize("name", ONTOLOGY_MISSING_DRUGS)
    def test_a_drug_the_ontology_lacks_qualifies_on_pharmacologic_context(self, name) -> None:
        text = f"Patients were treated with {name} for 12 weeks."
        assert has_pharmacologic_context(text, name)
        assert qualifies_as_asset(AssetEvidence(name=name, support=1, pharmacologic_context=True))

    @pytest.mark.parametrize("name", ONTOLOGY_MISSING_DRUGS)
    def test_it_reaches_the_default_path(self, name) -> None:
        disposition = classify_mention_support(name, support=1, pharmacologic_context=True)
        assert disposition is not MentionDisposition.LOW_SUPPORT_UNKNOWN

    @pytest.mark.parametrize(
        "template",
        [
            "Patients received {name} at 10 mg daily.",
            "{name} is a selective inhibitor of the pathway.",
            "The {name} antibody was administered intravenously.",
            "Treatment with {name} continued until progression.",
            "Administration of {name} began at week 4.",
            "Twelve patients on {name} were evaluable.",
            "{name}-treated patients had fewer flares.",
            "A single dose of {name} was given.",
        ],
    )
    def test_the_ways_a_document_says_something_is_a_drug(self, template) -> None:
        assert has_pharmacologic_context(template.format(name="benzhexol"), "benzhexol")


class TestTheRuleIsNotAListOfTheObservedMistakes:
    def test_no_observed_bad_word_appears_in_the_source(self) -> None:
        import ast
        import inspect

        from bve.se.discovery import asset_qualification

        tree = ast.parse(inspect.getsource(asset_qualification))
        for node in ast.walk(tree):
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                node.value.value = ""
        source = ast.unparse(tree).casefold()
        for token in ("although", "euroflow", "iqr", "baseline", "months", "before"):
            assert token not in source

    def test_an_unseen_common_word_is_rejected_the_same_way(self) -> None:
        # Not in the observed set; the rule has to generalize or it is a blacklist.
        assert not qualifies_as_asset(AssetEvidence(name="furthermore", support=50))
        assert not qualifies_as_asset(AssetEvidence(name="median", support=50))


class TestADevelopmentCodeIsAShapeNotADigit:
    @pytest.mark.parametrize("code", ["CCS1477", "ICG318", "SB-773812", "MK-3475A", "AZD0120"])
    def test_a_development_code_qualifies_on_its_own(self, code) -> None:
        assert is_development_code(code)
        assert qualifies_as_asset(AssetEvidence(name=code, support=1))

    @pytest.mark.parametrize("name", ["IQR 72", "PET 30", "week 12", "10 mg"])
    def test_a_number_next_to_a_word_is_not_a_development_code(self, name) -> None:
        # The old rule was "contains a digit anywhere", which protected a statistic.
        assert not is_development_code(name)
        assert not qualifies_as_asset(AssetEvidence(name=name, support=100))


class TestTheExistingRoutesStillHold:
    def test_an_ontology_known_drug_still_qualifies(self) -> None:
        assert qualifies_as_asset(AssetEvidence(name="obexelimab", support=1))
        assert (
            classify_mention_support("obexelimab", support=1)
            is MentionDisposition.PROTECTED
        )

    def test_a_structurally_typed_drug_is_still_protected(self) -> None:
        # M18: a source declaring DRUG in its own schema is evidence from outside the
        # corpus, and one document is enough. Unchanged by this layer.
        assert qualifies_as_asset(
            AssetEvidence(name="furthermore", support=1, structurally_typed_drug=True)
        )
        assert (
            classify_mention_support(
                "furthermore", support=1, structurally_typed_drug=True
            )
            is MentionDisposition.PROTECTED
        )

    def test_low_support_unknown_remains_recoverable_not_deleted(self) -> None:
        # M18's contract: a disposition routes, it never deletes. A name that fails
        # qualification today must be promotable by evidence arriving later.
        assert (
            classify_mention_support("furthermore", support=1)
            is MentionDisposition.LOW_SUPPORT_UNKNOWN
        )
        assert (
            classify_mention_support("furthermore", support=1, pharmacologic_context=True)
            is not MentionDisposition.LOW_SUPPORT_UNKNOWN
        )


class TestContextMustBeAboutThisName:
    def test_a_drug_context_elsewhere_in_the_document_does_not_transfer(self) -> None:
        text = "Patients were treated with benzhexol. Response was assessed at baseline."
        assert has_pharmacologic_context(text, "benzhexol")
        assert not has_pharmacologic_context(text, "baseline")

    def test_a_name_absent_from_the_text_has_no_context(self) -> None:
        assert not has_pharmacologic_context("Patients were treated with benzhexol.", "lestaurinib")


class TestAWordCanOccupyADrugsSlotByAccident:
    """The patterns match ordinary sentences, because ordinary sentences have that shape.

    "received before", "although antibody", "drugs therapy" -- each is a real fragment from
    the acceptance corpus, and each is syntactically indistinguishable from "received
    benzhexol". The sentence cannot settle it. How much of the corpus the token occupies
    can: a function word is everywhere, and a molecule the ontology lacks is not.
    """

    @pytest.mark.parametrize("name", OBSERVED_JUNK)
    def test_context_does_not_save_a_token_that_saturates_the_corpus(self, name) -> None:
        assert not qualifies_as_asset(
            AssetEvidence(
                name=name,
                document_frequency=3000,
                pharmacologic_context=True,
                corpus_documents=15032,
            )
        )

    @pytest.mark.parametrize("name", ONTOLOGY_MISSING_DRUGS)
    def test_a_rare_molecule_still_qualifies_on_context(self, name) -> None:
        assert qualifies_as_asset(
            AssetEvidence(
                name=name,
                document_frequency=4,
                pharmacologic_context=True,
                corpus_documents=15032,
            )
        )

    def test_the_ceiling_never_vetoes_an_authority(self) -> None:
        # Saturation is a veto on prose context alone. A name the ontology knows, a
        # development code, or a structured DRUG declaration is vouched for from outside
        # the corpus, and the corpus does not get to overrule that.
        saturating = dict(document_frequency=9999, corpus_documents=15032)
        assert qualifies_as_asset(AssetEvidence(name="rituximab", **saturating))
        assert qualifies_as_asset(AssetEvidence(name="CCS1477", **saturating))
        assert qualifies_as_asset(
            AssetEvidence(name="anything", structurally_typed_drug=True, **saturating)
        )

    def test_an_unsized_corpus_does_not_veto(self) -> None:
        # A caller that does not know the corpus size gets no ceiling rather than a
        # ceiling of zero, which would silently reject every unknown name.
        assert qualifies_as_asset(
            AssetEvidence(
                name="benzhexol", document_frequency=9999, pharmacologic_context=True
            )
        )


class TestTheCorpusStandsInForADictionary:
    def test_document_frequency_counts_documents_not_occurrences(self) -> None:
        texts = ["before before before benzhexol", "before that", "unrelated"]
        frequencies = document_frequencies(texts)
        assert frequencies["before"] == 2
        assert frequencies["benzhexol"] == 1

    def test_the_measure_is_the_language_not_the_extractor(self) -> None:
        # The mention count says how often the extractor nominated a name. A common word
        # can be nominated twice and still be a common word, which is why the ceiling
        # reads document frequency and the earlier support-based attempt did not work.
        common = AssetEvidence(
            name="before",
            support=2,
            document_frequency=6000,
            pharmacologic_context=True,
            corpus_documents=15032,
        )
        assert not qualifies_as_asset(common)

    def test_a_phrase_is_not_judged_by_this_ceiling(self) -> None:
        assert qualifies_as_asset(
            AssetEvidence(
                name="CD19/BCMA dual CAR-T",
                document_frequency=9999,
                pharmacologic_context=True,
                corpus_documents=15032,
            )
        )


class TestADescribedConstructIsAnAuthority:
    def test_a_construct_description_qualifies_a_multiword_name(self) -> None:
        # "BCMA/CD19 CAR T cells" is a real dual construct and nothing else vouches for
        # it: no ontology entry, no development code, no drug shape. What it has is a
        # registry that described it as a construct and named its targets.
        assert qualifies_as_asset(
            AssetEvidence(name="BCMA/CD19 CAR T cells", identity_authority=True)
        )
        assert not qualifies_as_asset(AssetEvidence(name="BCMA/CD19 CAR T cells"))

    def test_the_authority_is_not_available_to_a_word(self) -> None:
        # The guarantee is that the route is earned, not that the word is named: an
        # ordinary token never acquires a construct description, so this is the shape of
        # the evidence rather than an exception for the names that need it.
        assert not qualifies_as_asset(AssetEvidence(name="although", support=200))
