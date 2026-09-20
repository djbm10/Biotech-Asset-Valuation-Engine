"""A coverage area and the connector that reaches it are different claims.

The press-release wiring exposed this: `company_press_release_sec_filed` acquired four
genuine issuer releases, two of which moved a gate, and the manifest went on reporting that
no evidence from company press releases was acquired. Nothing failed, no test broke, and the
run's own provenance record was false -- which for this system is the worst available kind of
defect, because provenance is the product.

These tests pin both directions of honesty: a reached area must not be reported unreached,
and an area reached only through SEC delivery must not silently claim the private companies
and company-hosted newsrooms that channel never carries.
"""

from __future__ import annotations

from datetime import date

import pytest

from bve.se.discovery.coverage import (
    MANDATORY_COVERAGE,
    coverage_areas,
    coverage_families,
    residual_limitations,
    unreached_areas,
)
from bve.se.discovery.orchestrator import AdapterResult, DiscoveryOrchestrator
from bve.se.schemas.contracts import SearchOutcome

from test_acquisition_fail_closed import _problem

SEC_FILED = "company_press_release_sec_filed"
AREA = "company_press_release"


class _Adapter:
    """A source that answers, contributing nothing but its own status."""

    mandatory = False

    def __init__(self, source_name: str, outcome=SearchOutcome.SUCCESS) -> None:
        self.source_name = source_name
        self._outcome = outcome

    def search(self, query, *, as_of_date: date) -> AdapterResult:
        return AdapterResult(outcome=self._outcome, hits=[])


class TestTheTableSeparatesAreaFromFamily:
    def test_the_press_release_area_is_acquired_by_the_sec_filed_family(self) -> None:
        area = next(a for a in MANDATORY_COVERAGE if a.name == AREA)
        assert area.families == (SEC_FILED,)

    def test_an_ordinary_area_is_acquired_by_a_family_of_its_own_name(self) -> None:
        # The indirection is the exception, not the rule: every other area names its own
        # connector, and adding a source must not require an entry here to keep working.
        area = next(a for a in MANDATORY_COVERAGE if a.name == "clinicaltrials_gov")
        assert area.families == ("clinicaltrials_gov",)

    def test_reaching_the_area_through_the_narrower_family_counts(self) -> None:
        assert AREA not in unreached_areas([SEC_FILED])

    def test_reaching_nothing_leaves_the_area_unreached(self) -> None:
        assert AREA in unreached_areas([])

    def test_the_narrower_family_carries_its_residual_limitation(self) -> None:
        limitations = residual_limitations([SEC_FILED])
        assert len(limitations) == 1
        text = limitations[0]
        # The specific uncovered populations, named. "Partial coverage" would be true and
        # useless; a reader has to be able to tell what this run cannot speak to.
        assert "private companies" in text
        assert "8-K" in text

    def test_an_unreached_area_states_no_residual_limitation(self) -> None:
        # Nothing was acquired, so there is no partial coverage to qualify -- the blind spot
        # says it outright, and two statements about the same area would contradict.
        assert residual_limitations([]) == ()

    def test_the_declared_areas_are_unique(self) -> None:
        assert len(coverage_areas()) == len(set(coverage_areas()))


class TestTheManifestStopsContradictingItself:
    def _run(self, families, *, outcome=SearchOutcome.SUCCESS):
        adapters = [_Adapter(name, outcome) for name in families]
        return DiscoveryOrchestrator(
            adapters,
            max_passes=2,
            required_zero_growth_passes=2,
            declared_mandatory_sources=[AREA],
            declared_coverage_limitations=residual_limitations(families),
            coverage_families=coverage_families(),
            retry_backoff_seconds=0.0,
        )

    def _manifest(self, families, **kwargs):
        return self._run(families, **kwargs).run(
            _problem(),
            run_id="run:coverage",
            code_version="test",
            normalization_version="test",
        ).manifest

    def test_a_successful_sec_filed_acquisition_reports_success(self) -> None:
        manifest = self._manifest([SEC_FILED])
        assert manifest.source_status[SEC_FILED] is SearchOutcome.SUCCESS

    def test_it_is_not_also_reported_unconfigured(self) -> None:
        manifest = self._manifest([SEC_FILED])
        assert manifest.source_status[SEC_FILED] is not SearchOutcome.NOT_CONFIGURED
        assert all(SEC_FILED not in spot for spot in manifest.known_blind_spots)

    def test_the_manifest_never_says_nothing_was_acquired_when_something_was(self) -> None:
        # The exact false sentence, pinned by its meaning rather than its wording: no blind
        # spot may claim the press-release area went unacquired while a family that acquires
        # it reported SUCCESS.
        manifest = self._manifest([SEC_FILED])
        unacquired = [
            spot
            for spot in manifest.known_blind_spots
            if AREA in spot and "no evidence from it was acquired" in spot
        ]
        assert unacquired == []

    def test_the_broader_limitation_stays_visible(self) -> None:
        manifest = self._manifest([SEC_FILED])
        assert any("private companies" in spot for spot in manifest.known_blind_spots)

    def test_an_unreached_area_still_reports_as_unacquired(self) -> None:
        # The fix must not make the contract unfalsifiable: with no press-release family at
        # all, the original blind spot is the correct statement and must survive.
        manifest = self._manifest(["clinicaltrials_gov"])
        assert any(
            AREA in spot and "no evidence from it was acquired" in spot
            for spot in manifest.known_blind_spots
        )

    def test_a_reached_area_does_not_make_the_run_incomplete_for_that_reason(self) -> None:
        manifest = self._manifest([SEC_FILED])
        assert all(AREA not in reason for reason in manifest.incomplete_reasons)

    def test_a_failed_sec_filed_connector_still_reports_its_failure(self) -> None:
        # Coverage accounting must not launder a breakage. A family that broke acquired an
        # unknown share of its universe, which is a different and worse thing than a family
        # that was never configured.
        manifest = self._manifest([SEC_FILED], outcome=SearchOutcome.FAILED)
        assert manifest.source_status[SEC_FILED] is SearchOutcome.FAILED


class TestEverythingElseIsUntouched:
    @pytest.mark.parametrize(
        "family", ["clinicaltrials_gov", "sec_edgar", "conference_ash", "conference_eha"]
    )
    def test_a_family_that_names_its_own_area_is_unaffected(self, family: str) -> None:
        assert unreached_areas([family]) == tuple(
            name for name in coverage_areas() if name != family
        )
        assert residual_limitations([family]) == ()
