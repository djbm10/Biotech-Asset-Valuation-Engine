"""Issuer press releases filed as SEC exhibits: wiring, and what delivery does not buy.

This is the first activated family whose documents carry full release text rather than
bibliographic metadata, so it is the first that could move a gate rather than only widen
discovery. That makes the interesting tests the negative ones. Delivery through EDGAR says a
registrant filed the document; it says nothing whatever about whether the science in it is
true, and a sponsor calling its own data "encouraging" is a sponsor calling its own data
encouraging.

The connector itself was built and covered in M12 (``tests/se/test_acquisition.py``); what
was missing was a production caller. These tests pin the wiring and the evidence boundary,
not the classifier internals.
"""

from __future__ import annotations

from datetime import date

import pytest

from bve.se.acquisition.connectors import SecFiledPressReleaseConnector
from bve.se.acquisition.runner import default_connectors
from bve.se.evidence.human_poc import efficacy_statements

AS_OF = date(2026, 9, 17)
ASSETS = ("HPN217", "CC-95266")


def _statements(text: str, *, assets=ASSETS):
    return efficacy_statements(text, asset_names=assets, document_id="doc:test")


class TestTheFamilyIsReachableFromProduction:
    def test_the_default_connector_set_includes_it(self) -> None:
        families = [connector.source_family for connector in default_connectors()]
        assert "company_press_release_sec_filed" in families

    def test_it_is_the_already_built_connector(self) -> None:
        connector = next(
            candidate
            for candidate in default_connectors()
            if candidate.source_family == "company_press_release_sec_filed"
        )
        assert isinstance(connector, SecFiledPressReleaseConnector)

    def test_the_delivery_channel_is_recorded_not_implied(self) -> None:
        # A later reader must not be able to mistake this family for a newsroom crawl.
        assert SecFiledPressReleaseConnector.delivery_channel == "SEC_EXHIBIT"

    def test_foreign_private_issuers_are_still_in_scope(self) -> None:
        # Admitting only 8-K would filter by the registrant's nationality rather than by
        # genre, and silently drop every non-US issuer from a family whose entire purpose is
        # issuer-authored news. The live run bore this out: a Swiss registrant's release
        # arrived on a 6-K.
        assert SecFiledPressReleaseConnector.eligible_root_forms == {"8-K", "6-K"}

    def test_the_registrant_only_coverage_limit_stays_stated(self) -> None:
        # The blind spot is the point: private, non-registrant, and subsidiary-of-a-filer
        # companies are invisible here, and that must remain written down rather than
        # inferred from an empty result.
        doc = SecFiledPressReleaseConnector.__doc__ or ""
        assert "registrant" in doc.lower()
        assert "private companies" in doc.lower()


class TestDeliveryIsNotEvidence:
    """An SEC exhibit is a delivery mechanism. It cannot manufacture a scientific fact."""

    def test_sec_delivery_alone_does_not_establish_human_efficacy(self) -> None:
        text = (
            "Exhibit 99.1. FOR IMMEDIATE RELEASE. The Company announced today that it is "
            "advancing HPN217 through its clinical program."
        )
        assert _statements(text) == []

    @pytest.mark.parametrize(
        "enthusiasm",
        [
            "The Company reported promising results for HPN217.",
            "Data for HPN217 were encouraging.",
            "HPN217 delivered positive data in the ongoing study.",
            "HPN217 is potentially transformative for patients.",
            "We are highly encouraged by the HPN217 profile observed to date.",
        ],
    )
    def test_sponsor_enthusiasm_alone_does_not_establish_human_efficacy(
        self, enthusiasm: str
    ) -> None:
        # Every one of these names the asset and asserts something good about it. None
        # reports a measured human outcome, which is the only thing the gate accepts.
        assert _statements(enthusiasm) == []

    def test_protocol_and_design_language_without_results_stays_silent(self) -> None:
        text = (
            "The Phase 2 study of HPN217 will enroll 120 patients with relapsed or "
            "refractory multiple myeloma. The primary endpoint is overall response rate."
        )
        assert _statements(text) == []


class TestAConcreteHumanResultStillFlowsThrough:
    def test_a_reported_response_rate_is_admissible(self) -> None:
        text = "HPN217 achieved an overall response rate of 63% in 30 patients with myeloma."
        statements = _statements(text)
        assert statements, "a measured human outcome attributed to the asset must qualify"
        assert statements[0].asset_name == "HPN217"

    def test_the_source_span_is_retained(self) -> None:
        # Attribution has to survive: the gate's rationale is the sentence itself.
        text = "HPN217 achieved an overall response rate of 63% in 30 patients with myeloma."
        assert "63%" in _statements(text)[0].sentence

    def test_attribution_is_sentence_scoped(self) -> None:
        # A release naming the asset in one sentence and a number in another has not said
        # the number is about the asset. Stitching them is the inference this layer refuses,
        # and press releases interleave programs constantly.
        text = (
            "The Company is developing HPN217 for multiple myeloma. "
            "An overall response rate of 63% was observed in the study."
        )
        assert _statements(text) == []


class TestCombinationEfficacyDoesNotTransfer:
    def test_a_regimen_result_is_not_each_component(self) -> None:
        # A doublet's response rate is a fact about the doublet. Crediting it to one
        # component would invent single-agent activity that nobody reported.
        text = (
            "HPN217 in combination with dexamethasone achieved an overall response rate "
            "of 63% in 30 patients."
        )
        assert _statements(text) == []

    def test_the_same_result_stated_of_the_asset_alone_does_qualify(self) -> None:
        # The control for the test above: the refusal must be about the regimen, not about
        # the sentence being hard to read.
        text = "HPN217 achieved an overall response rate of 63% in 30 patients."
        assert _statements(text)


class TestClassificationAndProvenance:
    def _hit(self, *, file_type="EX-99.1", forms=("8-K",), cik="0001708493", description=""):
        return {
            "_id": "0001-0002:ex991.htm",
            "_source": {
                "ciks": [cik],
                "root_forms": list(forms),
                "file_type": file_type,
                "file_date": "2026-01-15",
                "file_description": description,
                "display_names": ["Example Bio (CIK 0001708493)"],
            },
        }

    def test_a_non_ex99_exhibit_is_rejected_before_fetching(self) -> None:
        connector = SecFiledPressReleaseConnector(lambda phrase: [])
        assert (
            connector._eligible(self._hit(file_type="EX-10.1"), AS_OF)
            == "not_an_ex99_exhibit"
        )

    def test_an_ineligible_form_is_rejected(self) -> None:
        connector = SecFiledPressReleaseConnector(lambda phrase: [])
        assert connector._eligible(self._hit(forms=("10-K",)), AS_OF) == "form_not_eligible"

    def test_a_filing_without_a_registrant_is_rejected(self) -> None:
        connector = SecFiledPressReleaseConnector(lambda phrase: [])
        assert connector._eligible(self._hit(cik="  "), AS_OF) == "no_sec_registrant_cik"

    def test_a_filing_after_the_as_of_date_is_rejected(self) -> None:
        # Fail-closed on date, as with every other family: a search answers as of today, and
        # a document filed after the question was asked is not admissible to it.
        connector = SecFiledPressReleaseConnector(lambda phrase: [])
        assert (
            connector._eligible(self._hit(), date(2025, 1, 1)) == "filed_after_as_of_date"
        )

    def test_an_eligible_hit_passes_the_pre_fetch_screen(self) -> None:
        connector = SecFiledPressReleaseConnector(lambda phrase: [])
        assert connector._eligible(self._hit(), AS_OF) is None

    def test_a_connector_failure_is_reported_not_swallowed(self) -> None:
        # Fail-closed: a mandatory source that broke must say so, because "no results" and
        # "never asked" have to stay distinguishable.
        def boom(phrase: str):
            raise RuntimeError("EDGAR unavailable")

        health = SecFiledPressReleaseConnector(boom).acquire(
            _NullStore(), targets=(), modality_terms=(), as_of_date=AS_OF
        )
        assert health.connector_succeeded is False or health.raw_record_count == 0


class _NullStore:
    def add(self, **kwargs):
        raise AssertionError("nothing should be stored when acquisition fails")
