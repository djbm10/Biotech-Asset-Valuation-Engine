"""A study name is not an asset, and only the source's own phrasing can tell them apart.

``LEAP-004`` and ``AMG 404`` are the same shape. Nothing in either token says which one is a
molecule, because nothing in either token *can*: pharmaceutical companies name their trials the
way they name their programs. The difference is in what the sentence does with the token -- one
is the name of a study, the other is the thing the study administers -- so that is where the
boundary has to read, and a lexical rule of any kind would have to guess.

That makes the exclusion per *occurrence*, never per token. A code framed as a study here may be
an intervention in the next document, and the second reading must survive the first.
"""

from __future__ import annotations

from bve.se.discovery.adapters import extract_observed_asset_names


class TestAStudyNameDoesNotBecomeAnAsset:
    def test_the_leap_004_title_yields_its_drugs_and_not_the_study(self) -> None:
        names = extract_observed_asset_names(
            "Phase II LEAP-004 Study of Lenvatinib Plus Pembrolizumab for Melanoma "
            "With Confirmed Progression on a PD-1 Inhibitor"
        )
        assert "LEAP-004" not in names
        assert "Lenvatinib" in names
        assert "Pembrolizumab" in names

    def test_the_keynote_024_title_yields_its_drugs_and_not_the_study(self) -> None:
        names = extract_observed_asset_names(
            "KEYNOTE-024: Phase III trial of pembrolizumab (MK-3475) vs platinum-based "
            "chemotherapy as first-line therapy"
        )
        assert "KEYNOTE-024" not in names
        assert "pembrolizumab" in names
        assert "MK-3475" in names

    def test_the_bare_definite_article_framing_is_enough(self) -> None:
        # No phase wording, no colon -- just the source calling the code a trial. This is the
        # minimal framing, and it must be sufficient on its own.
        assert "LEAP-004" in extract_observed_asset_names("Results from LEAP-004")
        assert "LEAP-004" not in extract_observed_asset_names("Results from the LEAP-004 trial")


class TestDevelopmentCodesSurvive:
    def test_an_intervention_code_beside_the_word_phase_is_still_an_asset(self) -> None:
        # The ASCO title that added AMG 404. A code near "phase" is not a study name; only a
        # code the sentence *names a study with* is, and this sentence names none.
        assert "AMG 404" in extract_observed_asset_names(
            "A phase 1b study of blinatumomab with the anti-programmed cell death (PD)-1 "
            "antibody AMG 404 in patients with relapsed leukemia"
        )

    def test_the_other_two_asco_assets_survive(self) -> None:
        names = extract_observed_asset_names(
            "BI 765179 in advanced solid tumours", "ociperlimab (BGB-A1217) plus tislelizumab"
        )
        assert "BI 765179" in names
        assert "ociperlimab" in names

    def test_the_same_token_is_an_asset_where_it_is_the_intervention(self) -> None:
        # The exclusion is a reading of one occurrence, not a verdict on a string. A source
        # that administers the code states something the study-naming source never did.
        assert "LEAP-004" in extract_observed_asset_names(
            "Patients received LEAP-004 at 20 mg daily"
        )

    def test_one_study_framing_does_not_silence_an_intervention_elsewhere(self) -> None:
        names = extract_observed_asset_names(
            "The LEAP-004 study enrolled 103 patients. Each received LEAP-004 intravenously."
        )
        assert "LEAP-004" in names


class TestStructuredTrialIdentifiersNeverMintIdentity:
    def test_a_registry_identifier_is_not_an_asset(self) -> None:
        assert extract_observed_asset_names("NCT02142738 and PMID 30000123") == []

    def test_a_ctgov_acronym_field_is_not_an_intervention(self) -> None:
        # Structured protocols mint assets from the intervention module alone, so a trial
        # acronym has no route to identity at all -- the contextual rule is for prose, where
        # no field says which token is the study.
        from bve.se.discovery.adapters import _candidate_interventions

        selected = _candidate_interventions(
            {
                "identificationModule": {
                    "briefTitle": "LEAP-004: Lenvatinib Plus Pembrolizumab in Melanoma",
                    "acronym": "LEAP-004",
                },
                "armsInterventionsModule": {
                    "interventions": [
                        {"name": "Lenvatinib", "type": "DRUG"},
                        {"name": "Pembrolizumab", "type": "DRUG"},
                    ]
                },
            },
            _StubVocabulary(),
        )
        names = {name for name, _targets, _modality in selected}
        assert "LEAP-004" not in names
        assert names == {"Lenvatinib", "Pembrolizumab"}


class _StubVocabulary:
    """The boundary under test is identity, not vocabulary: this asserts neither."""

    def targets_in(self, _text: str) -> set[str]:
        return set()

    def modality_in(self, _text: str) -> str | None:
        return None


class TestSessionCategoriesAreNotStudyNames:
    """Conferences classify abstracts with words that look like the naming construction.

    "Trials in Progress" is a session category -- the one ASCO numbers TPS#### -- and an
    abstract number sitting in front of it is not thereby the name of a trial. Two independent
    readings protect this: the naming noun is singular, and a category is not a description.
    """

    def test_a_trial_in_progress_heading_does_not_veto_the_preceding_code(self) -> None:
        names = extract_observed_asset_names(
            "PB1983: TRIAL-IN-PROGRESS: PHASE II STUDY OF PHE885, A B-CELL MATURATION "
            "ANTIGEN-DIRECTED CHIMERIC ANTIGEN RECEPTOR T-CELL THERAPY"
        )
        assert "PB1983" in names

    def test_the_plural_never_names_a_single_study(self) -> None:
        # "The LEAP-004 trial" names a study; "LEAP-004 trials" names none.
        assert "LEAP-004" in extract_observed_asset_names("LEAP-004 trials in progress")
