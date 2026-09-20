"""Acquisition orchestration: BuyerProblem -> generic connectors -> populated corpus.

The runner derives target/modality query vocabulary from the buyer's strategic gap and the shared
ontology, then runs each configured connector into a single :class:`CorpusStore`. It never reads
the benchmark reference universe -- coverage is measured afterwards and separately.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import yaml  # type: ignore[import-untyped]

from bve.se.acquisition.connectors import (
    CONFERENCE_VENUES,
    ClinicalTrialsGovConnector,
    CrossrefConferenceConnector,
    FdaLabelConnector,
    PubMedConnector,
    SecEdgarConnector,
    SecFiledPressReleaseConnector,
    TargetQuery,
    DeclaredUrlConnector,
)
from bve.se.acquisition.corpus_store import CorpusStore
from bve.se.acquisition.policy import DeclaredSourceEntry, LiveSourcePolicy
from bve.se.acquisition.source_health import SourceHealth, SourceHealthReport
from bve.se.ontology.modality import modality_aliases
from bve.se.ontology.targets import target_aliases
from bve.se.schemas.contracts import BuyerProblemV2


class Connector(Protocol):
    source_family: str

    def acquire(
        self,
        store: CorpusStore,
        *,
        targets: Sequence[TargetQuery],
        modality_terms: Sequence[str],
        as_of_date,
    ) -> SourceHealth: ...


def target_queries_for(problem: BuyerProblemV2) -> list[TargetQuery]:
    """Build generic per-target alias groups from the buyer gap + ontology (no asset names)."""

    queries: list[TargetQuery] = []
    for target in problem.strategic_gap.target_expression.targets:
        aliases = list(
            dict.fromkeys(
                [target.label, *target.aliases, *target_aliases(target.canonical_id)]
            )
        )
        queries.append(TargetQuery(canonical_id=target.canonical_id, aliases=aliases))
    return queries


def modality_terms_for(problem: BuyerProblemV2) -> list[str]:
    terms: list[str] = []
    for modality in problem.strategic_gap.modalities:
        terms.extend([modality, *modality_aliases(modality)])
    return list(dict.fromkeys(terms))


#: Conference venues active in the default set, by source family. A venue is listed here only
#: once it has been validated against the live source, so the shared ``CONFERENCE_VENUES``
#: table can describe every venue the connector supports while production activates them one
#: at a time. Adding a venue is an entry here, never another branch in the runner.
ACTIVE_CONFERENCE_FAMILIES: tuple[str, ...] = ("conference_ash", "conference_eha")


def conference_connectors() -> list[Connector]:
    """The validated conference venues, built from the shared venue table."""

    by_family = {venue.source_family: venue for venue in CONFERENCE_VENUES}
    return [
        CrossrefConferenceConnector(by_family[family])
        for family in ACTIVE_CONFERENCE_FAMILIES
    ]


def default_connectors() -> list[Connector]:
    """The live API-driven connector set.

    CT.gov, FDA label, PubMed, SEC EDGAR, the validated conference venues, and issuer press
    releases filed as SEC exhibits. The last is the first family here carrying full release
    text rather than bibliographic metadata, so it is the first that can contribute evidence
    a gate may act on -- subject, as always, to that evidence satisfying its own producer's
    rules. Delivery by SEC does not make a sponsor's scientific claim true.
    """

    return [
        ClinicalTrialsGovConnector(page_size=1000),
        FdaLabelConnector(limit=50),
        PubMedConnector(limit=300),
        SecEdgarConnector(max_documents=25),
        SecFiledPressReleaseConnector(max_documents=25),
        *conference_connectors(),
    ]


def declared_connectors(manifest_path: Path) -> list[Connector]:
    """Build declared source-location connectors from a versioned URL manifest.

    The manifest contains only publisher/source locations. It is deliberately independent of
    benchmark identities and therefore cannot add asset names to generic acquisition queries.
    """

    payload = yaml.safe_load(manifest_path.read_text()) or {}
    entries = [DeclaredSourceEntry.model_validate(entry) for entry in payload.get("sources", [])]
    families = [entry.source_family for entry in entries]
    if len(families) != len(set(families)):
        raise ValueError("declared source manifest contains duplicate source families")
    return [
        DeclaredUrlConnector(entry.source_family, list(entry.urls))
        for entry in entries
    ]


def connectors_for_policy(policy: LiveSourcePolicy) -> list[Connector]:
    """Construct exactly the built-in and declared connectors allowed by ``policy``."""

    requested = [
        *policy.required_source_families,
        *policy.optional_source_families,
    ]
    built_ins = {connector.source_family: connector for connector in default_connectors()}
    declared = {
        entry.source_family: DeclaredUrlConnector(entry.source_family, list(entry.urls))
        for entry in policy.declared_sources
    }
    available = {**built_ins, **declared}
    missing = sorted(set(policy.required_source_families) - set(available))
    if missing:
        raise ValueError(
            "required source families have no connector configuration: " + ", ".join(missing)
        )
    return [available[family] for family in requested if family in available]


def run_acquisition(
    problem: BuyerProblemV2,
    corpus_dir: Path,
    *,
    connectors: Sequence[Connector] | None = None,
    declared_source_manifest: Path | None = None,
    policy: LiveSourcePolicy | None = None,
) -> SourceHealthReport:
    """Run every connector into the corpus at ``corpus_dir`` and return the health report."""

    store = CorpusStore(Path(corpus_dir))
    if policy is not None:
        policy.validate_problem(problem)
    if policy is not None and declared_source_manifest is not None:
        raise ValueError("use either policy-declared sources or a legacy declared manifest")
    if policy is not None and connectors is not None:
        raise ValueError("policy-controlled acquisition cannot accept ad hoc connectors")
    targets = target_queries_for(problem)
    modality_terms = modality_terms_for(problem)
    active = (
        list(connectors)
        if connectors is not None
        else connectors_for_policy(policy)
        if policy is not None
        else default_connectors()
    )
    if declared_source_manifest is not None:
        active.extend(declared_connectors(declared_source_manifest))
    if not active:
        raise ValueError("at least one acquisition connector is required")
    families = [connector.source_family for connector in active]
    if len(families) != len(set(families)):
        raise ValueError("acquisition connector source families must be unique")
    report = SourceHealthReport()
    for connector in active:
        health = connector.acquire(
            store,
            targets=targets,
            modality_terms=modality_terms,
            as_of_date=problem.buyer.as_of_date,
        )
        report.sources.append(health)
    return report
