"""Shared fixtures for the S&E suite.

The ontology fixture here exists so tests can exercise the *labelling* path, which runs
before any query and therefore needs a whole-snapshot vocabulary. It is deliberately
structural rather than benchmark-tuned: two targets, real provenance fields, and no alias
invented to make an assertion pass. A test that only goes green because someone hand-seeded
a spelling is testing the seed, not the resolver.
"""

from __future__ import annotations

from datetime import date

import pytest

from bve.se.ontology.records import (
    AliasType,
    EntityType,
    SourceAlias,
    SourceEntityRecord,
    SourceProvenance,
)
from bve.se.ontology.snapshot import OntologySnapshot
from bve.se.ontology.targets import reset_resolver_cache


def _open_targets(
    source_id: str,
    symbol: str,
    *,
    synonyms: tuple[str, ...] = (),
    uniprot: str,
) -> SourceEntityRecord:
    return SourceEntityRecord(
        source="open_targets",
        source_id=source_id,
        entity_type=EntityType.TARGET,
        canonical_symbol=symbol,
        label=symbol,
        aliases=[
            SourceAlias(value=value, alias_type=AliasType.SYNONYM) for value in synonyms
        ],
        xrefs={"uniprot": [uniprot]},
    )


@pytest.fixture
def se_ontology_snapshot(tmp_path_factory, monkeypatch) -> OntologySnapshot:
    """Install a minimal but production-shaped ontology snapshot for the process.

    Two targets are enough to cover both naming cases that matter: one where the approved
    HGNC symbol is also the common name (``CD19``), and one where it is not (``TNFRSF17``,
    commonly written ``BCMA``). Consumers get real aliases from the resolver rather than a
    word list, which is the whole point of the layer under test.
    """

    snapshot = OntologySnapshot(
        sources=[
            SourceProvenance(
                source="open_targets",
                release="26.06",
                retrieved_at=date(2026, 8, 15),
                locator="ftp://ftp.ebi.ac.uk/pub/databases/opentargets/platform/26.06",
            )
        ],
        records=[
            _open_targets("ENSG00000177455", "CD19", uniprot="P15391"),
            _open_targets(
                "ENSG00000048462",
                "TNFRSF17",
                synonyms=("BCMA", "CD269"),
                uniprot="Q02223",
            ),
        ],
    )
    path = tmp_path_factory.mktemp("se_ontology") / "snapshot"
    snapshot.write(path)
    monkeypatch.setenv("BVE_SE_ONTOLOGY_SNAPSHOT", str(path))
    reset_resolver_cache()
    try:
        yield snapshot
    finally:
        # The resolver is cached per process, so a snapshot left installed would silently
        # widen every later test's vocabulary.
        reset_resolver_cache()


@pytest.fixture(autouse=True)
def _no_ncit_sidecar(monkeypatch, tmp_path_factory):
    """Tests never pick up the locally installed NCIt sidecar unless they install one.

    The sidecar is local data (``data/se/ontology/ncit``); a suite whose outcome depended
    on whether a developer had built it would not be a test of the code.
    """

    from bve.se.ontology.ncit_targets import reset_ncit_cache

    missing = tmp_path_factory.mktemp("no_ncit") / "absent.json"
    monkeypatch.setenv("BVE_SE_NCIT_SIDECAR", str(missing))
    reset_ncit_cache()
    yield
    reset_ncit_cache()


@pytest.fixture(autouse=True)
def _no_ncit_entity_types(monkeypatch, tmp_path_factory):
    """Likewise for the NCIt entity-type sidecar (candidate_qualification_v6 Q1)."""

    from bve.se.ontology.ncit_entity_types import reset_entity_types_cache

    missing = tmp_path_factory.mktemp("no_ncit_types") / "absent.json"
    monkeypatch.setenv("BVE_SE_NCIT_ENTITY_TYPES", str(missing))
    reset_entity_types_cache()
    yield
    reset_entity_types_cache()


@pytest.fixture(autouse=True)
def _no_ncit_cell_products(monkeypatch, tmp_path_factory):
    """Likewise for the NCIt Cell-typed product sidecar (ncit_modality_v1)."""

    from bve.se.ontology.ncit_cell_products import reset_cell_products_cache

    missing = tmp_path_factory.mktemp("no_ncit_cells") / "absent.json"
    monkeypatch.setenv("BVE_SE_NCIT_CELL_PRODUCTS", str(missing))
    reset_cell_products_cache()
    yield
    reset_cell_products_cache()
