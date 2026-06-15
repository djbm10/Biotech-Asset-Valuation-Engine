"""Normalized comparison of a predicted lead against a known seed (truth).

Each field has its own matcher because each fails differently:
- drug: no canonical registry exists, so a token/substring matcher with an
  explicit "near-miss" signal (so formatting differences aren't scored as wrong).
- indication: reuse ``IndicationNormalizer`` (canonical id when trustworthy).
- stage: CT.gov max phase → registry stage vocab; ``nda_bla``/``approved`` seeds
  cannot be expressed by CT.gov phases and are flagged separately, not as errors.
- modality: heuristic class from the drug name; the weakest field, reported honestly.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

from bve.discovery.drug_identity import share_identity

# ── Drug matching ───────────────────────────────────────────────────────────────

_DRUG_NOISE_RE = re.compile(
    r"\b(hydrochloride|hcl|sodium|sulfate|mesylate|tablet|tablets|capsule|"
    r"capsules|injection|oral|iv|for injection)\b",
    re.I,
)


def _drug_tokens(name: str) -> set[str]:
    text = _DRUG_NOISE_RE.sub(" ", name.lower())
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return {tok for tok in text.split() if len(tok) > 2}


def match_drug(predicted: str, truth: str) -> tuple[bool, bool]:
    """Return (is_match, is_near).

    ``is_match`` — confident same-asset match: shared code name (BEAM-201 ==
    "anti-CD7 CAR-T (BEAM-201)"), exact/substring, or shared distinctive token
    (handles combos like "VX-121/tezacaftor/deutivacaftor").
    ``is_near`` — token Jaccard in a gray zone (reported, not counted as correct).
    """
    if not predicted or not truth:
        return False, False
    if share_identity([predicted], [truth]):
        return True, False
    p, t = predicted.lower().strip(), truth.lower().strip()
    if p == t or p in t or t in p:
        return True, False
    pt, tt = _drug_tokens(predicted), _drug_tokens(truth)
    if not pt or not tt:
        return False, False
    if pt & tt:
        return True, False
    jacc = len(pt & tt) / len(pt | tt)
    return False, 0.0 < jacc < 0.5


# ── Indication matching ─────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _indication_normalizer():
    from bve.normalization.normalizer import IndicationNormalizer

    return IndicationNormalizer()


def _norm_indication(text: str) -> Optional[str]:
    try:
        res = _indication_normalizer().normalize(text)
    except Exception:
        return None
    return res.canonical_id if res.is_trustworthy else None


def match_indication(predicted_conditions: list[str], truth_indication: str) -> bool:
    """Match the truth indication against any of the predicted trial conditions."""
    if not truth_indication or not predicted_conditions:
        return False
    truth_cid = _norm_indication(truth_indication)
    truth_tokens = {w for w in re.split(r"[^a-z0-9]+", truth_indication.lower()) if len(w) > 3}
    for cond in predicted_conditions:
        if truth_cid is not None and _norm_indication(cond) == truth_cid:
            return True
        cond_tokens = {w for w in re.split(r"[^a-z0-9]+", cond.lower()) if len(w) > 3}
        if truth_tokens and cond_tokens and (truth_tokens & cond_tokens):
            return True
    return False


# ── Stage matching ──────────────────────────────────────────────────────────────

# Registry stages CT.gov phases cannot express (post-pivotal / post-approval).
_POST_CTGOV_STAGES = {"nda_bla", "approved", "filed", "commercial"}


def map_phase_to_stage(phase: Optional[str]) -> Optional[str]:
    """CT.gov canonical phase string → registry stage vocab (identity for phase_*)."""
    return phase  # phase_1 | phase_2 | phase_3 already match the registry vocab


def match_stage(predicted_phase: Optional[str], truth_stage: str) -> tuple[bool, bool]:
    """Return (is_match, understated_no_ctgov).

    ``understated_no_ctgov`` is True when the seed is at a stage CT.gov phases
    cannot represent (e.g. ``nda_bla``) — an expected gap, not a ranker error.
    """
    truth = (truth_stage or "").lower().strip()
    if truth in _POST_CTGOV_STAGES:
        return False, True
    return map_phase_to_stage(predicted_phase) == truth, False


# ── Modality inference + matching ────────────────────────────────────────────────

# Ordered: first matching pattern wins. Values are registry modality vocab.
# Matched against the drug name AND its synonyms/title (more text = better recall).
_MODALITY_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(vedotin|deruxtecan|govitecan|emtansine|tirumotecan|\badc\b|drug conjugate|antibody[- ]drug)", re.I), "adc"),
    (re.compile(r"(\bcar[- ]?t\b|\bcar\b|\btcr\b|\btil\b|\bnk\b|nk[- ]cell|cell therapy|autologous|allogeneic|leucel|cabtagene|\bbagene)", re.I), "cell_gene"),
    (re.compile(r"(\baav\b|gene therapy|\blenti|gene transfer|gene editing|crispr|zinc finger|-gene\b|\b-vec\b|valoctocogene|etranacogene)", re.I), "gene_therapy"),
    (re.compile(r"(sirna|\bsi[- ]?rna\b|antisense|\baso\b|oligonucleotide|\bmrna\b|\b-sen\b|\b-rsen\b|\b-siran\b|\b-nersen\b|-mersen|-rsiran)", re.I), "rna_therapy"),
    (re.compile(r"(\b-mab\b|mab$|monoclonal|antibody|\b-cept\b|fusion protein|\b-zumab|\b-ximab|\b-umab|bispecific|\b-bart\b|\b-tug\b)", re.I), "biologic"),
    (re.compile(r"(\b-tide\b|tide$|peptide|glp-?1|gip\b|incretin|insulin|\b-glutide\b|\b-tatide\b)", re.I), "peptide"),
]

# CT.gov intervention type → modality, used when the name has no decisive cue.
_TYPE_TO_MODALITY: dict[str, str] = {
    "BIOLOGICAL": "biologic",
    "GENETIC": "cell_gene",
    "DRUG": "small_molecule",
}


def infer_modality(
    drug_name: str,
    conditions: Optional[list[str]] = None,
    *,
    intervention_type: Optional[str] = None,
    aliases: Optional[list[str]] = None,
) -> str:
    """Best-effort modality class.

    Order: a decisive name/synonym pattern wins first (CAR-T, -mab, AAV, siRNA,
    peptide); otherwise CT.gov's intervention type decides (BIOLOGICAL→biologic,
    GENETIC→cell_gene, DRUG→small_molecule). When neither gives a signal the
    answer is ``unknown`` — better an honest gap (flagged for review) than a
    confident wrong ``small_molecule``.
    """
    text = " ".join([drug_name or "", *(aliases or [])])
    if not text.strip():
        return "unknown"
    for pattern, modality in _MODALITY_PATTERNS:
        if pattern.search(text):
            return modality
    itype = (intervention_type or "").upper()
    if itype in _TYPE_TO_MODALITY:
        return _TYPE_TO_MODALITY[itype]
    return "unknown"


# Truth modalities that the coarse inference legitimately collapses together.
_MODALITY_EQUIV: dict[str, set[str]] = {
    "small_molecule": {"small_molecule", "peptide"},
    "biologic": {"biologic", "adc", "peptide"},
    "cell_gene": {"cell_gene", "gene_therapy"},
    "gene_therapy": {"gene_therapy", "cell_gene"},
    "rna_therapy": {"rna_therapy", "biologic"},
}


def match_modality(predicted: str, truth: str) -> bool:
    """Match inferred modality to truth, allowing coarse-class equivalences."""
    p, t = (predicted or "").lower(), (truth or "").lower()
    if not p or not t:
        return False
    if p == t:
        return True
    return p in _MODALITY_EQUIV.get(t, {t})
