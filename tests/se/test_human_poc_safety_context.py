"""Preregistered controls for adverse-event framing in the human-PoC veto.

Declared in ``docs/se_policies/human_poc_safety_context_v1.md`` before the code changed.

The predecessor milestone clause-scoped the non-efficacy veto, which found one real result
(``Cevostamab``) and one false positive (``tabelecleucel``): *tumor flare reaction* is an
adverse event that borrows a word from ``_EFFICACY_TERMS``, where it means an autoimmune
disease flare. Both readings are live in this corpus, so the registers are separated rather
than the term deleted -- and the tests that matter most here are the ones asserting the
efficacy reading survived.
"""

from __future__ import annotations

from bve.se.evidence.human_poc import efficacy_statements


def _passes(sentence: str, asset: str) -> bool:
    return bool(efficacy_statements(sentence, asset_names=[asset], document_id="doc"))


class TestTheFalsePositiveThisMilestoneExistsToRefuse:
    def test_a_tumor_flare_reaction_among_complications_is_not_an_efficacy_flare(self) -> None:
        assert not _passes(
            "For VSTs, the principal early complications are tumor flare reaction (in "
            "approximately 20% of tabelecleucel recipients), GVHD (below 5% with enriched "
            "products), acute infusion reactions, and low-grade CRS-like cytokine release.",
            "tabelecleucel",
        )

    def test_a_tumor_flare_reaction_is_refused_with_no_complications_word_present(self) -> None:
        """Rule 2 alone. Without this, the sentence reads as a quantified efficacy result."""
        assert not _passes(
            "Tumor flare reaction occurred in 20% of patients treated with drugx.", "drugx"
        )

    def test_complications_framing_refuses_whatever_the_finding_is_called(self) -> None:
        assert not _passes(
            "The principal complications of drugx were infusion reactions in 8 of 20 patients.",
            "drugx",
        )


class TestTheEfficacyReadingOfFlareSurvives:
    """If these fail, rule 2 deleted an endpoint instead of disambiguating it."""

    def test_a_disease_flare_count_against_placebo_is_a_result(self) -> None:
        assert _passes(
            "flares were reported in 26 patients (26.8%) in the obexelimab group and in 53 "
            "patients (54.6%) in the placebo group.",
            "obexelimab",
        )

    def test_flared_is_not_caught_by_flare_reaction(self) -> None:
        assert _passes(
            "Although 14 of 15 patients flared, disease activity remained lower, and "
            "responsiveness lasting >3 months to previously failed drugs (Janus kinase "
            "inhibitors, abatacept, tumour necrosis factor inhibitors) observed in 7 of 15 "
            "patients.",
            "abatacept",
        )


class TestTheResultThePredecessorWasBuiltToFind:
    def test_a_response_rate_still_passes_beside_a_safety_clause(self) -> None:
        assert _passes(
            "Cevostamab (FcRH5xCD3) demonstrated a 30.2% overall response rate in patients who "
            "underwent BCMA-targeted treatment and 60.6% in BCMA-targeted naive patients;the "
            "triple-step dosing strategy reduced cytokine release syndrome.",
            "Cevostamab",
        )

    def test_a_complications_clause_does_not_veto_a_clean_quantified_clause(self) -> None:
        """Rule 3: existing behaviour, pinned so rules 1 and 2 cannot quietly remove it."""
        assert _passes(
            "The drugx overall response rate was 62% in 40 patients, and the principal early "
            "complications were infusion reactions.",
            "drugx",
        )


class TestTheConservatismThisMilestoneDidNotRelax:
    def test_tolerability_alone_is_still_not_efficacy(self) -> None:
        assert not _passes(
            "drugx was well tolerated with grade 3 adverse events in 5 of 20 patients.", "drugx"
        )
