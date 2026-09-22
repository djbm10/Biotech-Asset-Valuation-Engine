"""Preregistered controls for multi-token drug-name identity.

Declared in ``docs/se_policies/multi_token_drug_name_identity_v1.md`` before the lexicon was
built. The name pattern matches one token at a time, so a two-word INN could only ever become
two assets -- and both halves of an ADC name are independently present in the ontology, so
nothing about either token alone reveals the split. Only the pair does.

The tests that constrain the fix are the last four: no token is banned, adjacency alone never
merges, and a half the plausibility filter already refused does not return under a longer name.
"""

from __future__ import annotations

from bve.se.discovery.adapters import extract_observed_asset_names
from bve.se.discovery.drug_name_shape import is_known_multi_token_drug_name


class TestATwoWordNameIsOneAsset:
    def test_an_antibody_drug_conjugate_is_not_split_into_antibody_and_payload(self) -> None:
        assert extract_observed_asset_names("Patients received belantamab mafodotin.") == [
            "belantamab mafodotin"
        ]

    def test_a_second_conjugate_behaves_the_same(self) -> None:
        assert extract_observed_asset_names("Responses were seen with loncastuximab tesirine.") == [
            "loncastuximab tesirine"
        ]

    def test_a_third_conjugate_behaves_the_same(self) -> None:
        assert extract_observed_asset_names("Patients received inotuzumab ozogamicin.") == [
            "inotuzumab ozogamicin"
        ]

    def test_a_cell_therapy_name_stays_whole(self) -> None:
        """`idecabtagene` is nominated by no route, which is why `Vicleucel` reached the
        shortlist alone. One half being a mention has to be enough to look."""
        assert extract_observed_asset_names("Patients received idecabtagene vicleucel.") == [
            "idecabtagene vicleucel"
        ]


class TestWhatTheRuleMustNotDo:
    def test_a_payload_token_is_not_banned_globally(self) -> None:
        """Suppressed where it is the tail of a name, a mention everywhere else."""
        assert extract_observed_asset_names(
            "The vedotin payload was released intracellularly."
        ) == ["vedotin"]

    def test_adjacent_but_genuinely_separate_drugs_do_not_merge(self) -> None:
        assert extract_observed_asset_names(
            "Patients received rituximab cyclophosphamide vincristine."
        ) == ["rituximab", "cyclophosphamide", "vincristine"]

    def test_a_single_token_name_is_untouched(self) -> None:
        assert extract_observed_asset_names("Patients received blinatumomab.") == ["blinatumomab"]

    def test_joining_does_not_revive_a_half_the_filter_refused(self) -> None:
        """`gonadorelin` is refused as prose -- it is a TARGET label -- and `gonadorelin
        acetate` is in no prose list, so without a guard the pair walks back in."""
        assert extract_observed_asset_names("Patients received gonadorelin acetate.") == []


class TestTheAuthorityBehindTheJoin:
    def test_the_ontology_knows_the_full_names(self) -> None:
        for name in (
            "belantamab mafodotin",
            "loncastuximab tesirine",
            "inotuzumab ozogamicin",
            "idecabtagene vicleucel",
            "brentuximab vedotin",
            "gemtuzumab ozogamicin",
        ):
            assert is_known_multi_token_drug_name(name)

    def test_two_separate_drugs_are_not_one_record(self) -> None:
        assert not is_known_multi_token_drug_name("rituximab cyclophosphamide")


class TestTheSeparatorIsWhitespaceNotTheAsciiSpace:
    """Amendment 6c. Every case here was found in the `frag_live` corpus, not invented.

    The first fix-on live run left `vicleucel`, `tesirine`, `ozogamicin` and `ciloleucel` as
    assets with zero standalone occurrences. One root cause with two faces: a publisher's
    non-breaking space, and this function's own `\\n` between concatenated texts.
    """

    def test_a_non_breaking_space_joins(self) -> None:
        """Publisher formatting alone must not recreate the fragmentation."""
        assert extract_observed_asset_names("Received loncastuximab tesirine.") == [
            "loncastuximab tesirine"
        ]

    def test_a_tab_joins(self) -> None:
        assert "belantamab mafodotin" in extract_observed_asset_names(
            "Received belantamab\tmafodotin today."
        )

    def test_two_texts_do_not_mint_the_fragment_one_text_would_not(self) -> None:
        """`extract_observed_asset_names(title, abstract)` joins with a newline. Each text
        alone merged correctly; passing both minted `vicleucel`."""
        title = "Idecabtagene vicleucel manufacturing and out-of-spec product"
        abstract = "Idecabtagene vicleucel (ide-cel) induces deep responses."
        for texts in ((title,), (abstract,), (title, abstract)):
            assert extract_observed_asset_names(*texts) == ["Idecabtagene vicleucel"]

    def test_a_newline_is_not_a_separator(self) -> None:
        """The seam between a title and an abstract is not a space. Joining across it would
        marry the tail of one field to the head of the next."""
        assert extract_observed_asset_names("Trials of belantamab\nmafodotin binds BCMA.") == [
            "belantamab",
            "mafodotin",
        ]

    def test_punctuation_still_separates(self) -> None:
        """A source that comma-separates a drug's own halves has written two list items.
        Merging there is the adjacency-only merge the policy forbids."""
        assert extract_observed_asset_names(
            "Tafasitamab, loncastuximab, tesirine, polatuzumab and selinexor."
        ) == ["Tafasitamab", "loncastuximab", "tesirine", "polatuzumab", "selinexor"]
