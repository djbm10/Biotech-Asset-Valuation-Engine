"""The preregistered controls for `human_poc_abbreviations_and_mixed_sentences_v1`.

Every sentence here is corpus text, read before it was used. The predecessor milestone's
mandatory negative control was chosen from a keyword survey, never read, and turned out to
report a 91% ORR -- so it tested nothing. Two of the four candidates considered for this
milestone's negative control failed the same way and were rejected for the same reason.

The negative controls matter more than the positives. Change C weakens a veto that the
module's own comment calls load-bearing, and `CT023-neg` is refused *by that veto* before
the change. If it starts passing, the veto's replacement is not doing the veto's job.
"""

from __future__ import annotations

from bve.se.evidence.human_poc import efficacy_statements

ASSET = "CTL019"


def _passes(sentence: str, asset: str = ASSET) -> bool:
    return bool(efficacy_statements(sentence, asset_names=[asset], document_id="doc"))


class TestAbbreviationsOfTermsTheStandardAlreadyAccepts:
    """`CR` is `complete response`, and `pts` is `patients`. Neither is a new standard."""

    def test_bare_cr_reports_efficacy(self) -> None:
        # AACR abstract PR06. Refused before this milestone at NO_EFFICACY_TERM.
        assert _passes(
            "13 patients (81%) achieved a CR on CTL019, including the patient with "
            "CD19+ T ALL, 3 did not respond."
        )

    def test_abbreviated_patients_are_people(self) -> None:
        # AACR abstract PR06, the second refusal. Needs `CR` *and* `pts` together.
        assert _passes(
            "10/16 evaluable pts treated with CTL019 have ongoing BM CR with median "
            "follow up 3.4 mo."
        )

    def test_cr_does_not_match_inside_a_longer_token(self) -> None:
        # CRS and CRP are a toxicity and an inflammatory marker. `\bCR\b` is what keeps
        # them out, and a casefolded substring test -- how every other term here is
        # matched -- would admit all three plus "across" and "increase".
        for sentence in (
            "CRS and CRP increased across all CTL019 cohorts of patients (40%).",
            "CTL019 CRi was reported in 3 of 12 patients.",
        ):
            assert not _passes(sentence), sentence

    def test_lowercase_cr_in_prose_is_not_an_endpoint(self) -> None:
        assert not _passes("The cr value for CTL019 was 40% in 20 patients.")

    def test_pr_is_not_an_efficacy_abbreviation(self) -> None:
        # AACR numbers abstracts PR06. This pipeline has already minted a bibliographic
        # identifier as a molecule once; `PR` stays out even though it is a real endpoint.
        assert not _passes(
            "Abstract PR06: CTL019 was given to 20 patients (50%) at the stated dose."
        )


class TestASafetyTermDoesNotEraseAnEfficacyResult:
    def test_a_result_survives_an_adverse_event_in_the_same_sentence(self) -> None:
        assert _passes(
            "Safety was evaluated in 40 patients and the CTL019 overall response rate was 62%."
        )

    def test_an_account_of_what_was_measured_is_still_refused(self) -> None:
        # The case the module's own comment gives for why the veto exists. It survives
        # change C only because the clean clause must carry the value too -- the first
        # draft of this milestone admitted it, which is why that requirement was added.
        assert not _passes(
            "Among 20 patients (50%), we measured CTL019 response to treatment and "
            "incidence of cytokine release syndrome."
        )

    def test_a_safety_only_sentence_is_still_refused(self) -> None:
        assert not _passes(
            "CTL019 was well tolerated with grade 3 adverse events in 5 of 20 patients."
        )


class TestThePreregisteredNegativeControls:
    """Corpus sentences that must stay refused. Each was read in full first."""

    def test_ct023_planned_endpoints_are_refused_without_the_safety_veto(self) -> None:
        # Load-bearing: refused at NON_EFFICACY:safety *before* change C. After it, only
        # the planned-endpoint clause stands between this sentence and a false PASS.
        assert not _passes(
            "The primary endpoint was safety and the secondary endpoints were ORR, "
            "progression free survival (PFS), overall survival (OS), and CTL019 "
            "transgene persistence.",
        )

    def test_5389_future_tense_evaluation_is_refused(self) -> None:
        assert not _passes(
            "Safety, pharmacokinetic profiles and primary efficacy parameters for CTL019 "
            "in 10 patients will be evaluated over 48 weeks."
        )

    def test_5389_named_endpoint_is_refused(self) -> None:
        assert not _passes(
            "Primary efficacy endpoint is SLE Responder Index 4 (SRI-4) criteria for "
            "CTL019 in 10 patients."
        )

    def test_ct071_stated_objectives_are_refused(self) -> None:
        assert not _passes(
            "This primary objective is to determine the maximum tolerated dose of CTL019 "
            "in 5 patients, and the key secondary objective is to investigate the "
            "anti-myeloma activity."
        )


class TestTheRequirementsThisMilestoneDidNotTouch:
    """The four clauses declared out of scope. A milestone that quietly relaxed one of
    these would look exactly like a milestone that worked."""

    def test_a_result_with_no_number_is_still_refused(self) -> None:
        # AACR LB-138, predicted in the preregistration to remain refused. Changes B and C
        # both move it down the ladder and it fails anyway, because `_VALUE` was not
        # relaxed to make a named positive pass.
        assert not _passes(
            "Pt 1 achieved a complete response (CR) on CTL019 and experienced Gr 3 fever "
            "and Gr 2 hypotension consistent with mild cytokine release syndrome (CRS)."
        )

    def test_a_result_in_another_sentence_is_still_not_attributed(self) -> None:
        assert not _passes(
            "Patients were treated with CTL019. The overall response rate was 62%."
        )

    def test_an_animal_result_is_still_refused(self) -> None:
        assert not _passes(
            "CTL019 produced a CR in 8 of 10 xenograft-bearing mice and in treated patients."
        )

    def test_eligibility_prose_is_still_refused(self) -> None:
        assert not _passes(
            "Patients must have had an inadequate response to CTL019 in at least 2 of 3 "
            "prior lines to be eligible."
        )
