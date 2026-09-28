"""An asset's own modality, from an authority's record of its drug.

``CanonicalAsset.modality_id`` is discovery context: the modality of the trial or query an
asset surfaced through, which is how cyclophosphamide came to read ``CAR_T``. This module
answers the different question of what the asset *is*, from ChEMBL's ``molecule_type`` for
the one drug the asset's own identifier names reach, and nothing else. No record means
UNKNOWN; the trial's modality is never borrowed. See ``authority_modality_v1.md``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from bve.se.ontology.records import AliasType, EntityType
from bve.se.ontology.resolver import BiomedicalEntityResolver

_ENV_VAR = "BVE_SE_MODALITY_AUTHORITY"
_DEFAULT_PATH = Path("data/se/ontology/modality/chembl_37_molecule_type.json")

#: ChEMBL ``molecule_type`` -> authority modality (§2.2). ``Gene`` is decided per drug.
_MOLECULE_TYPES: dict[str, str] = {
    "Small molecule": "SMALL_MOLECULE",
    "Antibody": "ANTIBODY",
    "Antibody drug conjugate": "ANTIBODY_DRUG_CONJUGATE",
    "Cell": "CELL_THERAPY",
    "Oligonucleotide": "RNA_THERAPEUTIC",
    "Protein": "PROTEIN",
    "Enzyme": "PROTEIN",
    "Oligosaccharide": "OLIGOSACCHARIDE",
    "Vaccine component": "VACCINE",
}
_GENE = "Gene"
#: WHO INN suffix for cell-based products (``-leucel``, ``-temcel``); vectors are ``-vec``.
_CELL_INN_SUFFIX = "cel"

#: Query modality -> (authority modalities that MATCH, authority modalities too coarse to
#: decide). Anything else known is a MISMATCH (§3).
_EVERYTHING = frozenset({*_MOLECULE_TYPES.values(), "GENE_THERAPY"})
_COMPATIBILITY: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "CELL_THERAPY": (frozenset({"CELL_THERAPY"}), frozenset()),
    "CAR_T": (frozenset(), frozenset({"CELL_THERAPY"})),
    "MONOCLONAL_ANTIBODY": (frozenset({"ANTIBODY"}), frozenset()),
    "BISPECIFIC_ANTIBODY": (frozenset(), frozenset({"ANTIBODY"})),
    "MULTISPECIFIC_ANTIBODY": (frozenset(), frozenset({"ANTIBODY"})),
    "T_CELL_ENGAGER": (frozenset(), frozenset({"ANTIBODY"})),
    "ANTIBODY_DRUG_CONJUGATE": (frozenset({"ANTIBODY_DRUG_CONJUGATE"}), frozenset()),
    "SMALL_MOLECULE": (frozenset({"SMALL_MOLECULE"}), frozenset()),
    "MOLECULAR_GLUE_OR_DEGRADER": (frozenset(), frozenset({"SMALL_MOLECULE"})),
    "GENE_THERAPY": (frozenset({"GENE_THERAPY"}), frozenset()),
    "GENE_EDITING": (frozenset(), frozenset({"GENE_THERAPY", "CELL_THERAPY"})),
    "RNA_THERAPEUTIC": (frozenset({"RNA_THERAPEUTIC"}), frozenset()),
    "VACCINE": (frozenset({"VACCINE"}), frozenset()),
    "PEPTIDE": (frozenset(), frozenset({"PROTEIN", "SMALL_MOLECULE"})),
    "FUSION_PROTEIN": (frozenset(), frozenset({"PROTEIN", "SMALL_MOLECULE"})),
    "RADIOLIGAND": (frozenset(), _EVERYTHING),
    "ONCOLYTIC_VIRUS": (frozenset(), _EVERYTHING),
}


class ModalityMatch(str, Enum):
    """Declared in rank order: an unknown modality never passes as a match."""

    MATCH = "MATCH"
    UNKNOWN = "UNKNOWN"
    MISMATCH = "MISMATCH"


@dataclass(frozen=True)
class AuthorityModality:
    modality: str
    drug_id: str
    chembl_ids: tuple[str, ...]
    molecule_type: str

    @property
    def basis(self) -> str:
        return f"{self.drug_id} ({', '.join(self.chembl_ids)}: {self.molecule_type})"


def default_modality_path() -> Path:
    override = os.environ.get(_ENV_VAR)
    return Path(override) if override else _DEFAULT_PATH


@lru_cache(maxsize=4)
def load_molecule_types(path: str) -> dict[str, str] | None:
    """The pinned ChEMBL id -> ``molecule_type`` sidecar, or ``None`` when not installed."""

    try:
        payload = json.loads(Path(path).read_text())
    except FileNotFoundError:
        return None
    return dict(payload["molecule_types"])


class DrugModalityAuthority:
    """Answers an asset's modality from its one authority drug, or not at all."""

    def __init__(
        self, resolver: BiomedicalEntityResolver, molecule_types: dict[str, str]
    ) -> None:
        self._resolver = resolver
        self._molecule_types = molecule_types

    def identifies_drug(self, name: str) -> str | None:
        # The identity rule authority_identity_merge_v1 adopted, and no other.
        from bve.se.discovery.class_terms import is_class_term

        if not name or not name.strip() or is_class_term(name):
            return None
        return self._resolver.resolve_identifier(name, EntityType.DRUG)

    def modality_of_names(self, names: Iterable[str]) -> AuthorityModality | None:
        drugs = {drug for name in names if (drug := self.identifies_drug(name))}
        if len(drugs) != 1:
            return None
        return self.modality_of_drug(next(iter(drugs)))

    def modality_of_drug(self, drug_id: str) -> AuthorityModality | None:
        entity = self._resolver.get(drug_id, EntityType.DRUG)
        if entity is None:
            return None
        chembl_ids = sorted(
            {cid for record in entity.source_records for cid in record.xrefs.get("chembl", [])}
        )
        types = {self._molecule_types.get(cid) for cid in chembl_ids}
        if len(types) != 1 or None in types:
            return None
        molecule_type = types.pop()
        assert molecule_type is not None
        if molecule_type == _GENE:
            approved = [
                alias.value for alias in entity.aliases if alias.alias_type is AliasType.APPROVED_NAME
            ]
            is_cell = any(
                name.split()[-1].casefold().endswith(_CELL_INN_SUFFIX)
                for name in approved
                if name.split()
            )
            modality = "CELL_THERAPY" if is_cell else "GENE_THERAPY"
        else:
            modality = _MOLECULE_TYPES.get(molecule_type)
            if modality is None:
                return None
        return AuthorityModality(modality, drug_id, tuple(chembl_ids), molecule_type)


def modality_match(
    authority_modality: str | None, query_modalities: Iterable[str]
) -> ModalityMatch | None:
    """The best status across the declared modalities; ``None`` when none are declared."""

    declared = [modality.strip().upper() for modality in query_modalities]
    if not declared:
        return None
    if authority_modality is None:
        return ModalityMatch.UNKNOWN
    statuses = []
    for query in declared:
        matches, coarse = _COMPATIBILITY.get(query, (frozenset(), _EVERYTHING))
        if authority_modality in matches:
            statuses.append(ModalityMatch.MATCH)
        elif authority_modality in coarse:
            statuses.append(ModalityMatch.UNKNOWN)
        else:
            statuses.append(ModalityMatch.MISMATCH)
    order = list(ModalityMatch)
    return min(statuses, key=order.index)


def modality_authority() -> DrugModalityAuthority | None:
    """The installed authority, or ``None``: every asset is then UNKNOWN, never guessed."""

    from bve.se.ontology.targets import get_resolver

    resolver = get_resolver()
    molecule_types = load_molecule_types(str(default_modality_path()))
    if resolver is None or molecule_types is None:
        return None
    return DrugModalityAuthority(resolver, molecule_types)
