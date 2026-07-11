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
    ClinicalTrialsGovConnector,
    FdaLabelConnector,
    PubMedConnector,
    SecEdgarConnector,
    TargetQuery,
    DeclaredUrlConnector,
)
from bve.se.acquisition.corpus_store import CorpusStore
from bve.se.acquisition.source_health import SourceHealth, SourceHealthReport
from bve.se.ontology.targets import _MODALITY_ALIASES, _TARGET_ALIASES
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
                [target.label, *target.aliases, *sorted(_TARGET_ALIASES.get(target.canonical_id, set()))]
            )
        )
        queries.append(TargetQuery(canonical_id=target.canonical_id, aliases=aliases))
    return queries


def modality_terms_for(problem: BuyerProblemV2) -> list[str]:
    terms: list[str] = []
    for modality in problem.strategic_gap.modalities:
        terms.extend([modality, *sorted(_MODALITY_ALIASES.get(modality, set()))])
    return list(dict.fromkeys(terms))


def default_connectors() -> list[Connector]:
    """The live API-driven connector set (CT.gov, FDA label, PubMed, SEC EDGAR)."""

    return [
        ClinicalTrialsGovConnector(page_size=1000),
        FdaLabelConnector(limit=50),
        PubMedConnector(limit=300),
        SecEdgarConnector(max_documents=25),
    ]


def declared_connectors(manifest_path: Path) -> list[Connector]:
    """Build declared source-location connectors from a versioned URL manifest.

    The manifest contains only publisher/source locations. It is deliberately independent of
    benchmark identities and therefore cannot add asset names to generic acquisition queries.
    """

    payload = yaml.safe_load(manifest_path.read_text()) or {}
    return [
        DeclaredUrlConnector(
            str(entry["source_family"]),
            [str(url) for url in entry.get("urls", [])],
        )
        for entry in payload.get("sources", [])
    ]


def run_acquisition(
    problem: BuyerProblemV2,
    corpus_dir: Path,
    *,
    connectors: Sequence[Connector] | None = None,
    declared_source_manifest: Path | None = None,
) -> SourceHealthReport:
    """Run every connector into the corpus at ``corpus_dir`` and return the health report."""

    store = CorpusStore(Path(corpus_dir))
    targets = target_queries_for(problem)
    modality_terms = modality_terms_for(problem)
    active = list(connectors) if connectors is not None else default_connectors()
    if declared_source_manifest is not None:
        active.extend(declared_connectors(declared_source_manifest))
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
