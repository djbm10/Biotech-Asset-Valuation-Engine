"""Preregistered controls for the trial-design register.

Declared in ``docs/se_policies/human_poc_trial_design_register_v1.md`` before the code changed.

The `INDIGO` sentence clears every other rung of the ladder honestly -- efficacy term, values,
patients, one named asset, no safety term, no future tense -- and is still not a result. It says
how the trial was *built*: how many enrolled, and how small an effect the design could have
detected. The tests that matter most here are the two that must keep passing, because the
sentences INDIGO resembles are real results in the same vocabulary.
"""

from __future__ import annotations

from bve.se.evidence.human_poc import efficacy_statements

INDIGO = (
    "The INDIGO trial achieved its global enrollment goal with 194 patients, making it the "
    "largest phase 3 trial in IgG4-RD to date and providing 90% power to detect a clinically "
    "meaningful reduction in flare risk."
)


def _passes(sentence: str, asset: str) -> bool:
    return bool(efficacy_statements(sentence, asset_names=[asset], document_id="doc"))


class TestADesignStatementIsNotAResult:
    def test_the_indigo_sentence_is_refused(self) -> None:
        assert not _passes(INDIGO, "INDIGO")

    def test_statistical_power_alone_is_refused(self) -> None:
        """The power clause without the enrollment phrase, so each term is tested on its own."""
        assert not _passes(
            "The study enrolled 194 patients and had 90% power to detect a 30% reduction in "
            "flare risk with drugx.",
            "drugx",
        )

    def test_a_recruitment_target_alone_is_refused(self) -> None:
        assert not _passes(
            "drugx reached its enrollment goal of 194 patients, 40% of whom were in remission "
            "at baseline.",
            "drugx",
        )


class TestTheResultsThisVocabularyBelongsTo:
    """If these fail, the rule refused the register instead of the design statement."""

    def test_achieving_a_primary_endpoint_is_still_a_result(self) -> None:
        """`achieved its` was rejected during preregistration and must not slip in sideways."""
        assert _passes(
            "drugx achieved its primary endpoint, with a 62% response rate in 40 patients.",
            "drugx",
        )

    def test_an_observed_reduction_in_flare_risk_is_still_a_result(self) -> None:
        """The exact outcome INDIGO describes the *power to detect*, actually observed."""
        assert _passes(
            "Treatment with drugx produced a 30% reduction in flare risk, observed in 194 "
            "patients.",
            "drugx",
        )


class TestTheLivePassesThisMustNotDisturb:
    def test_obexelimab_still_passes(self) -> None:
        assert _passes(
            "flares were reported in 26 patients (26.8%) in the obexelimab group and in 53 "
            "patients (54.6%) in the placebo group.",
            "obexelimab",
        )

    def test_cevostamab_still_passes(self) -> None:
        assert _passes(
            "Cevostamab (FcRH5xCD3) demonstrated a 30.2% overall response rate in patients who "
            "underwent BCMA-targeted treatment and 60.6% in BCMA-targeted naive patients;the "
            "triple-step dosing strategy reduced cytokine release syndrome.",
            "Cevostamab",
        )
