"""What a run is required to have looked at, and what may satisfy that requirement.

A *coverage area* is a part of the evidence universe a complete run must have reached --
company press releases, say. A *source family* is a connector that actually acquires
documents. The two are not the same thing, and conflating them produces a manifest that
lies in one of two directions.

Name the area after the family and an area reached by a narrower connector reports as
unreached: `company_press_release_sec_filed` acquired four issuer releases and the manifest
still said no press-release evidence was acquired. Name the family after the area and the
opposite lie appears: a run that reached only SEC-delivered releases would claim the whole
press-release universe, and the private companies, non-filers and subsidiary releases that
never pass through an eligible 8-K or 6-K would vanish from the record.

So an area declares the families that can acquire it, plus the limitation that survives when
only those families did. Reaching the area through a narrower family satisfies the
completeness contract and states what remains uncovered -- both, not either.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class MandatoryCoverage:
    """A coverage area a run must have reached."""

    #: The area, as the completeness contract names it.
    name: str

    #: The connector families that count as reaching it. Empty means the area is acquired by
    #: a family of its own name, which is the ordinary case.
    acquired_by: tuple[str, ...] = ()

    #: What remains uncovered when the area was reached only through ``acquired_by``. Stated
    #: as a limitation, never as a failure: nothing broke, and evidence *was* acquired.
    residual_limitation: str = ""

    @property
    def families(self) -> tuple[str, ...]:
        return self.acquired_by or (self.name,)


#: The completeness contract. Order is the reading order of the manifest, nothing more.
MANDATORY_COVERAGE: tuple[MandatoryCoverage, ...] = (
    MandatoryCoverage("clinicaltrials_gov"),
    MandatoryCoverage("company_pipeline_or_presentation"),
    MandatoryCoverage(
        "company_press_release",
        acquired_by=("company_press_release_sec_filed",),
        residual_limitation=(
            "company press releases were acquired only where a registrant filed them as an "
            "eligible 8-K or 6-K exhibit; releases from private companies, non-registrants, "
            "subsidiaries whose parent filing does not carry them, and company-hosted "
            "newsrooms were not reached"
        ),
    ),
    MandatoryCoverage("sec_edgar"),
    MandatoryCoverage("conference_ash"),
    MandatoryCoverage("conference_asco"),
    MandatoryCoverage("conference_aacr"),
    MandatoryCoverage("conference_eha"),
)


def coverage_areas() -> tuple[str, ...]:
    return tuple(area.name for area in MANDATORY_COVERAGE)


def coverage_families() -> dict[str, tuple[str, ...]]:
    """Area name -> the families that reach it, for callers that only know names."""

    return {area.name: area.families for area in MANDATORY_COVERAGE}


def unreached_areas(configured_families: Sequence[str]) -> tuple[str, ...]:
    """Areas no configured family reaches. These are genuine blind spots."""

    available = set(configured_families)
    return tuple(
        area.name
        for area in MANDATORY_COVERAGE
        if not available.intersection(area.families)
    )


def residual_limitations(configured_families: Sequence[str]) -> tuple[str, ...]:
    """Limitations of the areas that *were* reached, but only by a narrower family.

    An area reached by a family of its own name has nothing to add here; the declaration
    covers what it says it covers.
    """

    available = set(configured_families)
    return tuple(
        area.residual_limitation
        for area in MANDATORY_COVERAGE
        if area.residual_limitation
        and available.intersection(area.families)
        and area.name not in available
    )
