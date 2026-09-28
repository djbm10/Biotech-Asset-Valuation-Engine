"""An asset's modality is its own drug's, never its trial's: ``authority_modality_v1.md``."""

from __future__ import annotations

from datetime import date

from bve.se.ontology.drug_modality import (
    DrugModalityAuthority,
    ModalityMatch,
    modality_match,
)
from bve.se.ontology.records import (
    AliasType,
    EntityType,
    SourceAlias,
    SourceEntityRecord,
    SourceProvenance,
)
from bve.se.ontology.resolver import BiomedicalEntityResolver
from bve.se.ontology.snapshot import OntologySnapshot
from bve.se.reporting.shortlist import _rank_key
from bve.se.schemas.contracts import CanonicalAsset


def _drug(source_id: str, name: str, **aliases: list[str]) -> SourceEntityRecord:
    return SourceEntityRecord(
        source="chembl",
        source_id=source_id,
        entity_type=EntityType.DRUG,
        canonical_symbol=name,
        label=name,
        aliases=[
            SourceAlias(value=name, alias_type=AliasType.APPROVED_NAME),
            *(
                SourceAlias(value=value, alias_type=AliasType(alias_type))
                for alias_type, values in aliases.items()
                for value in values
            ),
        ],
        xrefs={"chembl": [source_id]},
    )


_MOLECULE_TYPES = {
    "CHEMBL1": "Gene",
    "CHEMBL2": "Cell",
    "CHEMBL3": "Small molecule",
    "CHEMBL4": "Antibody drug conjugate",
    "CHEMBL5": "Gene",
    "CHEMBL6": "Antibody",
    "CHEMBL7": "Unknown",
}


def _authority() -> DrugModalityAuthority:
    snapshot = OntologySnapshot(
        sources=[
            SourceProvenance(
                source="chembl",
                release="ChEMBL_37",
                retrieved_at=date(2026, 9, 7),
                locator="test",
                digest="d",
                record_count=7,
            )
        ],
        records=[
            _drug(
                "CHEMBL1",
                "AXICABTAGENE CILOLEUCEL",
                DEVELOPMENT_CODE=["KTE-C19"],
                TRADE_NAME=["Yescarta"],
            ),
            _drug("CHEMBL2", "TISAGENLECLEUCEL", DEVELOPMENT_CODE=["CART19"]),
            _drug("CHEMBL3", "CYCLOPHOSPHAMIDE"),
            _drug("CHEMBL4", "LONCASTUXIMAB TESIRINE"),
            _drug("CHEMBL5", "ONASEMNOGENE ABEPARVOVEC"),
            _drug("CHEMBL6", "TAFASITAMAB"),
            _drug("CHEMBL7", "MYSTERIUM"),
        ],
    )
    return DrugModalityAuthority(BiomedicalEntityResolver(snapshot), _MOLECULE_TYPES)


def _modality(*names: str) -> str | None:
    found = _authority().modality_of_names(names)
    return found.modality if found else None


class TestAuthorityModality:
    def test_cell_products_filed_as_gene_are_cell_therapies_by_their_inn(self) -> None:
        assert _modality("axicabtagene ciloleucel") == "CELL_THERAPY"
        assert _modality("KTE-C19") == "CELL_THERAPY"
        assert _modality("tisagenlecleucel") == "CELL_THERAPY"

    def test_a_vector_gene_therapy_is_not_a_cell_therapy(self) -> None:
        assert _modality("onasemnogene abeparvovec") == "GENE_THERAPY"

    def test_the_drug_decides_not_the_trial(self) -> None:
        # Whatever trial cyclophosphamide was found in, it is a small molecule.
        assert _modality("cyclophosphamide") == "SMALL_MOLECULE"
        assert _modality("loncastuximab tesirine") == "ANTIBODY_DRUG_CONJUGATE"
        assert _modality("tafasitamab") == "ANTIBODY"

    def test_no_identifier_record_is_unknown(self) -> None:
        assert _modality("CNCT19") is None
        assert _modality("R-mini-CHOP") is None
        assert _modality("mysterium") is None  # authority says Unknown
        # Trade names and class labels confer no identity, so no modality either.
        assert _modality("Yescarta") is None
        assert _modality("CART19") is None

    def test_an_asset_naming_two_drugs_is_unknown(self) -> None:
        assert _modality("tafasitamab", "cyclophosphamide") is None


class TestModalityMatch:
    def test_no_declared_modality_means_no_dimension(self) -> None:
        assert modality_match("ANTIBODY", []) is None

    def test_unknown_is_never_a_match(self) -> None:
        assert modality_match(None, ["CELL_THERAPY"]) is ModalityMatch.UNKNOWN

    def test_cell_therapy_query(self) -> None:
        assert modality_match("CELL_THERAPY", ["CELL_THERAPY"]) is ModalityMatch.MATCH
        assert modality_match("SMALL_MOLECULE", ["CELL_THERAPY"]) is ModalityMatch.MISMATCH
        assert modality_match("ANTIBODY", ["CELL_THERAPY"]) is ModalityMatch.MISMATCH

    def test_a_coarser_authority_cannot_decide_a_finer_question(self) -> None:
        assert modality_match("CELL_THERAPY", ["CAR_T"]) is ModalityMatch.UNKNOWN
        assert modality_match("ANTIBODY", ["T_CELL_ENGAGER"]) is ModalityMatch.UNKNOWN

    def test_the_best_status_across_declared_modalities_wins(self) -> None:
        assert modality_match("ANTIBODY", ["CELL_THERAPY", "MONOCLONAL_ANTIBODY"]) is (
            ModalityMatch.MATCH
        )


class TestRankKey:
    def _key(self, match: str | None, *, stage: int, poc: bool) -> tuple:
        asset = CanonicalAsset(asset_id=f"a-{match}-{stage}", canonical_name="x", modality_match=match)
        return _rank_key(
            asset,
            None,
            eligible=False,
            stage={asset.asset_id: stage},
            human_poc={asset.asset_id} if poc else set(),
        )

    def test_modality_match_precedes_poc_and_stage(self) -> None:
        match = self._key("MATCH", stage=1, poc=False)
        unknown = self._key("UNKNOWN", stage=4, poc=True)
        mismatch = self._key("MISMATCH", stage=4, poc=True)
        assert match < unknown < mismatch

    def test_without_a_declared_modality_ranking_v1_is_unchanged(self) -> None:
        assert self._key(None, stage=4, poc=True) < self._key(None, stage=1, poc=False)
        assert self._key(None, stage=1, poc=False)[1] == 0
