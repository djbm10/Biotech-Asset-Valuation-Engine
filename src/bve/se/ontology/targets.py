"""Small, versioned ontology kernel for the first CD19/BCMA vertical slice."""

from __future__ import annotations

TARGET_ONTOLOGY_VERSION = "cd19_bcma_v1"
MODALITY_ONTOLOGY_VERSION = "t_cell_engager_v1"

_TARGET_ALIASES = {
    "CD19": {"cd19", "cd-19", "b-lymphocyte antigen cd19", "b4"},
    "BCMA": {
        "bcma",
        "tnfrsf17",
        "tumor necrosis factor receptor superfamily member 17",
        "cd269",
    },
}

_MODALITY_ALIASES = {
    "T_CELL_ENGAGER": {
        "t cell engager",
        "t-cell engager",
        "tce",
        "bispecific t-cell engager",
        "bite",
        "t cell redirecting bispecific",
    },
}


def _normalize(value: str, ontology: dict[str, set[str]]) -> str | None:
    candidate = " ".join(value.casefold().strip().split())
    for canonical, aliases in ontology.items():
        if candidate == canonical.casefold() or candidate in aliases:
            return canonical
    return None


def normalize_target(value: str) -> str | None:
    """Return a canonical target ID, or ``None`` for an unknown term."""

    return _normalize(value, _TARGET_ALIASES)


def normalize_modality(value: str) -> str | None:
    """Return a canonical modality ID, or ``None`` for an unknown term."""

    return _normalize(value, _MODALITY_ALIASES)
