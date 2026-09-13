"""Drug names have to be readable out of ordinary prose, not just development codes.

`extract_observed_asset_names` recognized development codes plus six suffixes -- mab,
cept, parib, tinib, lisib, nib. Those describe oncology biologics and kinase inhibitors
and nothing else, so for any target whose assets are small molecules the prose extractor
returned cell lines, amino-acid residues and assay constants and not one drug. In the
sealed M15 corpus it produced HEK293, LYS191, IC 50 and EC50 while 148 abstracts named
fexofenadine.

The replacement matches a suffix lexicon counted off the DRUG entities of the frozen
ontology snapshot (see `bve.se.discovery.drug_name_lexicon`). These tests are written
against that mechanism, not against any target: every recovery assertion below is paired
with the same assertion for an unrelated therapeutic area.
"""

from __future__ import annotations

import pytest

from bve.se.discovery.adapters import extract_observed_asset_names

# Two therapeutic areas that share no stem, so a fix that only reaches one of them fails
# here. None of these names is hand-registered anywhere in the engine.
ANTIHISTAMINES = ["fexofenadine", "loratadine", "azelastine", "cyproheptadine"]
CARDIOVASCULAR = ["propranolol", "atenolol", "enalapril", "amlodipine"]


@pytest.mark.parametrize("drug", ANTIHISTAMINES + CARDIOVASCULAR)
def test_a_generic_drug_name_is_extracted_from_abstract_prose(drug: str) -> None:
    abstract = f"A randomized crossover study of {drug} in adult participants."

    extracted = {name.casefold() for name in extract_observed_asset_names(abstract)}

    assert drug in extracted


def test_the_legacy_biologic_and_kinase_suffixes_still_extract() -> None:
    """The six suffixes the old regex knew are a subset, not a casualty."""

    abstract = "Pembrolizumab and osimertinib were compared with abatacept and niraparib."

    extracted = {name.casefold() for name in extract_observed_asset_names(abstract)}

    assert {"pembrolizumab", "osimertinib", "abatacept", "niraparib"} <= extracted


def test_a_development_code_is_still_extracted() -> None:
    extracted = extract_observed_asset_names("Participants received GSK-1004723 or placebo.")

    assert "GSK-1004723" in extracted


@pytest.mark.parametrize(
    "word",
    ["membrane", "cytokine", "receptor", "transcription", "phosphatase"],
)
def test_ordinary_biomedical_prose_is_not_read_as_a_molecule(word: str) -> None:
    """Several derived stems also end ordinary words; the prose vocabulary blocks them."""

    extracted = {name.casefold() for name in extract_observed_asset_names(f"the {word} was measured")}

    assert word not in extracted


@pytest.mark.parametrize("token", ["LYS191", "ASN198", "TRP428"])
def test_an_amino_acid_residue_is_not_an_asset(token: str) -> None:
    """Residue positions are code-shaped and were being reported as drugs."""

    assert token not in extract_observed_asset_names(f"binding at {token} was abolished")


@pytest.mark.parametrize("token", ["IC50", "IC 50", "EC50", "LD50"])
def test_an_assay_constant_is_not_an_asset(token: str) -> None:
    assert token not in extract_observed_asset_names(f"the {token} was 4 nM")


def test_extraction_is_not_an_identity_claim() -> None:
    """M11's rule: extracting two names from one abstract says nothing about either one.

    The extractor returns distinct mentions; it must never merge or rank them.
    """

    extracted = extract_observed_asset_names(
        "Fexofenadine was compared with propranolol in a crossover design."
    )

    assert len([n for n in extracted if n.casefold() in {"fexofenadine", "propranolol"}]) == 2
