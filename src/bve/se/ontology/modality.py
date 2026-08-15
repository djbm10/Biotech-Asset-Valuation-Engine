"""Controlled vocabulary for therapeutic modality.

Unlike targets, modality has no authoritative upstream register to bulk-load: Open
Targets and ChEMBL classify molecules (``Antibody``, ``Small molecule``) far more
coarsely than an S&E screen needs. This vocabulary is therefore curated in-repo and
versioned alongside the entity snapshot.

It is a *taxonomy*, not benchmark seeding: entries describe modality classes that
exist across oncology and immunology generally, and no entry may encode a specific
target, programme, or company.
"""

from __future__ import annotations

from bve.se.ontology.records import normalize_lookup_key

MODALITY_ONTOLOGY_VERSION = "modality_v2"

_MODALITY_ALIASES: dict[str, set[str]] = {
    "T_CELL_ENGAGER": {
        "t cell engager",
        "tce",
        "bispecific t cell engager",
        "bite",
        "t cell redirecting bispecific",
        "t cell redirecting antibody",
        "cd3 bispecific",
        "cd3 engager",
    },
    "MONOCLONAL_ANTIBODY": {
        "monoclonal antibody",
        "mab",
        "igg",
        "antibody",
        "fully human antibody",
        "humanized antibody",
    },
    "BISPECIFIC_ANTIBODY": {
        "bispecific antibody",
        "bispecific",
        "bsab",
        "dual specific antibody",
    },
    "MULTISPECIFIC_ANTIBODY": {
        "trispecific",
        "trispecific antibody",
        "multispecific antibody",
        "multispecific",
    },
    "ANTIBODY_DRUG_CONJUGATE": {
        "antibody drug conjugate",
        "adc",
        "immunoconjugate",
        "antibody conjugate",
    },
    "RADIOLIGAND": {
        "radioligand",
        "radioligand therapy",
        "rlt",
        "radiopharmaceutical",
        "radioconjugate",
    },
    "CAR_T": {
        "car t",
        "car t cell",
        "chimeric antigen receptor t cell",
        "car t cell therapy",
        "autologous car t",
        "allogeneic car t",
    },
    "CELL_THERAPY": {
        "cell therapy",
        "adoptive cell therapy",
        "car nk",
        "til",
        "tumor infiltrating lymphocyte",
        "tcr t",
        "engineered tcr",
    },
    "SMALL_MOLECULE": {
        "small molecule",
        "small molecule inhibitor",
        "kinase inhibitor",
        "tyrosine kinase inhibitor",
        "tki",
        "covalent inhibitor",
        "allosteric inhibitor",
    },
    "MOLECULAR_GLUE_OR_DEGRADER": {
        "molecular glue",
        "degrader",
        "protac",
        "targeted protein degrader",
        "cereblon modulator",
    },
    "GENE_THERAPY": {
        "gene therapy",
        "aav",
        "adeno associated virus",
        "lentiviral vector",
        "gene transfer",
    },
    "GENE_EDITING": {
        "gene editing",
        "crispr",
        "base editing",
        "prime editing",
        "zinc finger nuclease",
    },
    "RNA_THERAPEUTIC": {
        "rna therapeutic",
        "sirna",
        "rnai",
        "antisense oligonucleotide",
        "aso",
        "mrna",
        "oligonucleotide",
    },
    "PEPTIDE": {
        "peptide",
        "peptide agonist",
        "peptide conjugate",
        "cyclic peptide",
    },
    "VACCINE": {
        "vaccine",
        "cancer vaccine",
        "therapeutic vaccine",
        "neoantigen vaccine",
    },
    "FUSION_PROTEIN": {
        "fusion protein",
        "fc fusion",
        "trap",
        "receptor fusion",
    },
    "ONCOLYTIC_VIRUS": {
        "oncolytic virus",
        "oncolytic viral therapy",
        "oncolytic",
    },
}

#: Terms that co-occur with engager-style constructs and widen recall without
#: asserting the modality on their own.
_MODALITY_EXPANSION_TERMS: dict[str, tuple[str, ...]] = {
    "T_CELL_ENGAGER": ("CD3", "CD3E", "bispecific", "trispecific"),
    "BISPECIFIC_ANTIBODY": ("bispecific",),
    "MULTISPECIFIC_ANTIBODY": ("trispecific", "multispecific"),
    "CAR_T": ("chimeric antigen receptor",),
}

_LOOKUP: dict[str, str] = {
    normalize_lookup_key(alias): canonical
    for canonical, aliases in _MODALITY_ALIASES.items()
    for alias in (*aliases, canonical.replace("_", " "))
}


def normalize_modality(value: str) -> str | None:
    """Return a canonical modality ID, or ``None`` for an unknown term."""

    return _LOOKUP.get(normalize_lookup_key(value))


def modality_aliases(canonical_id: str) -> tuple[str, ...]:
    """Every search-usable spelling of one modality, canonical form first."""

    aliases = _MODALITY_ALIASES.get(canonical_id)
    if aliases is None:
        return ()
    return (canonical_id, *sorted(aliases))


def modality_query_terms(canonical_id: str) -> tuple[str, ...]:
    """Alias spellings plus recall-widening co-occurrence terms."""

    aliases = modality_aliases(canonical_id)
    if not aliases:
        return ()
    return tuple(dict.fromkeys([*aliases, *_MODALITY_EXPANSION_TERMS.get(canonical_id, ())]))


def known_modalities() -> tuple[str, ...]:
    return tuple(sorted(_MODALITY_ALIASES))
