"""
Structured scientific similarity scorer.

Scores two Asset objects across five dimensions and returns an
AssetSimilarityScore with per-dimension explanations and a weighted composite.

Dimension weights (configurable via constructor):
    indication   0.35   — primary driver of deal and scientific relevance
    target       0.25   — shared biology
    moa          0.20   — mechanism-level overlap
    modality     0.10   — drug class similarity
    stage        0.10   — development proximity

Normalization is performed on-the-fly when canonical_indication / canonical_target
/ canonical_moa fields are absent from the Asset.  Pre-populating those fields
avoids re-normalization on repeated calls.
"""
from __future__ import annotations

from typing import Optional

from bve.entities.asset import Asset, Modality
from bve.normalization.normalizer import IndicationNormalizer, MOANormalizer, TargetNormalizer
from bve.normalization.registries import INDICATION_REGISTRY
from bve.normalization.types import NormalizationConfidence, NormalizationResult
from bve.similarity.stage_proximity import stage_proximity_score
from bve.similarity.types import AssetSimilarityScore, DimensionScore

# Modalities that are broadly "biologics-adjacent"
_BIOLOGIC_ADJACENT: set[Modality] = {
    Modality.BIOLOGIC,
    Modality.ADC,
    Modality.GENE_THERAPY,
    Modality.CELL_THERAPY,
}

_DEFAULT_WEIGHTS: dict[str, float] = {
    "indication": 0.35,
    "target": 0.25,
    "moa": 0.20,
    "modality": 0.10,
    "stage": 0.10,
}


class SimilarityScorer:
    """
    Score the scientific similarity between two Asset objects.

    Parameters
    ----------
    weights: dict with keys indication/target/moa/modality/stage
        Must sum to 1.0.  Defaults to the canonical 5-dimension weights.
    """

    def __init__(self, weights: Optional[dict[str, float]] = None) -> None:
        self._weights = weights or _DEFAULT_WEIGHTS
        self._ind_norm = IndicationNormalizer()
        self._tgt_norm = TargetNormalizer()
        self._moa_norm = MOANormalizer()

    # ── Public entry point ────────────────────────────────────────────────────

    def score(self, a: Asset, b: Asset) -> AssetSimilarityScore:
        """Compute and return AssetSimilarityScore for assets *a* and *b*."""
        flags: list[str] = []

        ind_dim = self._score_indication(a, b, flags)
        tgt_dim = self._score_target(a, b, flags)
        moa_dim = self._score_moa(a, b, flags)
        mod_dim = self._score_modality(a, b)
        stg_dim = self._score_stage(a, b)

        w = self._weights
        composite = (
            ind_dim.score * w["indication"]
            + tgt_dim.score * w["target"]
            + moa_dim.score * w["moa"]
            + mod_dim.score * w["modality"]
            + stg_dim.score * w["stage"]
        )

        return AssetSimilarityScore(
            asset_a_id=a.id,
            asset_b_id=b.id,
            indication_overlap=ind_dim,
            target_overlap=tgt_dim,
            moa_overlap=moa_dim,
            modality_overlap=mod_dim,
            stage_proximity=stg_dim,
            composite_score=round(min(max(composite, 0.0), 1.0), 4),
            confidence_flags=flags,
        )

    # ── Dimension scorers ─────────────────────────────────────────────────────

    def _resolve_indication(self, asset: Asset) -> Optional[NormalizationResult]:
        """Return NormalizationResult for asset's indication (canonical field or on-the-fly)."""
        if getattr(asset, "canonical_indication", None):
            # Already pre-computed; synthesize a HIGH result
            cid = asset.canonical_indication
            return NormalizationResult(
                raw_input=asset.indication,
                canonical_id=cid,
                canonical_name=INDICATION_REGISTRY[cid].name if cid in INDICATION_REGISTRY else cid,
                confidence=NormalizationConfidence.HIGH,
                match_score=100.0,
                method="exact",
            )
        return self._ind_norm.normalize(asset.indication)

    def _score_indication(
        self, a: Asset, b: Asset, flags: list[str]
    ) -> DimensionScore:
        w = self._weights["indication"]
        res_a = self._resolve_indication(a)
        res_b = self._resolve_indication(b)

        if res_a is None or res_b is None:
            return DimensionScore(score=0.0, reason="indication unavailable", weight=w)

        # Flag low-confidence normalizations
        for label, res in [("indication_a", res_a), ("indication_b", res_b)]:
            if not res.is_trustworthy:
                flags.append(f"{label}_low_confidence")

        cid_a = res_a.canonical_id
        cid_b = res_b.canonical_id

        if cid_a and cid_b and cid_a == cid_b:
            return DimensionScore(score=1.0, reason="exact canonical match", weight=w)

        # Same therapeutic area → partial credit
        ta_a = None
        ta_b = None
        if cid_a and cid_a in INDICATION_REGISTRY:
            ta_a = INDICATION_REGISTRY[cid_a].therapeutic_area
        if cid_b and cid_b in INDICATION_REGISTRY:
            ta_b = INDICATION_REGISTRY[cid_b].therapeutic_area
        if ta_a and ta_b and ta_a == ta_b:
            return DimensionScore(
                score=0.7,
                reason=f"same therapeutic area ({ta_a}), different indication",
                weight=w,
            )

        # Asset has matching TherapeuticArea enum
        if str(a.therapeutic_area.value) == str(b.therapeutic_area.value):
            return DimensionScore(
                score=0.5,
                reason=f"same therapeutic_area enum ({a.therapeutic_area.value})",
                weight=w,
            )

        return DimensionScore(score=0.0, reason="no indication overlap", weight=w)

    def _score_target(
        self, a: Asset, b: Asset, flags: list[str]
    ) -> DimensionScore:
        w = self._weights["target"]
        raw_a = getattr(a, "biological_target", None)
        raw_b = getattr(b, "biological_target", None)

        if not raw_a or not raw_b:
            return DimensionScore(score=0.0, reason="biological_target not set on one or both assets", weight=w)

        # Check pre-populated canonical
        cid_a = getattr(a, "canonical_target", None) or self._tgt_norm.normalize(raw_a).canonical_id
        cid_b = getattr(b, "canonical_target", None) or self._tgt_norm.normalize(raw_b).canonical_id

        res_a = self._tgt_norm.normalize(raw_a)
        res_b = self._tgt_norm.normalize(raw_b)

        for label, res in [("target_a", res_a), ("target_b", res_b)]:
            if not res.is_trustworthy:
                flags.append(f"{label}_low_confidence")

        if cid_a and cid_b and cid_a == cid_b:
            return DimensionScore(score=1.0, reason="same canonical target", weight=w)

        # Fuzzy partial match on raw strings (same gene family, different isoform)
        from rapidfuzz import fuzz
        raw_score = fuzz.token_sort_ratio(
            " ".join(raw_a.strip().lower().split()),
            " ".join(raw_b.strip().lower().split()),
        )
        if raw_score >= 80:
            return DimensionScore(
                score=0.5,
                reason=f"similar target strings (fuzzy score {raw_score})",
                weight=w,
            )

        return DimensionScore(score=0.0, reason="different targets", weight=w)

    def _score_moa(
        self, a: Asset, b: Asset, flags: list[str]
    ) -> DimensionScore:
        w = self._weights["moa"]
        raw_a = a.mechanism_of_action
        raw_b = b.mechanism_of_action

        if not raw_a or not raw_b:
            return DimensionScore(score=0.0, reason="mechanism_of_action not set on one or both assets", weight=w)

        cid_a = getattr(a, "canonical_moa", None) or self._moa_norm.normalize(raw_a).canonical_id
        cid_b = getattr(b, "canonical_moa", None) or self._moa_norm.normalize(raw_b).canonical_id

        res_a = self._moa_norm.normalize(raw_a)
        res_b = self._moa_norm.normalize(raw_b)

        for label, res in [("moa_a", res_a), ("moa_b", res_b)]:
            if not res.is_trustworthy:
                flags.append(f"{label}_low_confidence")

        if cid_a and cid_b and cid_a == cid_b:
            return DimensionScore(score=1.0, reason="same canonical MOA", weight=w)

        # Same target but different MOA → partial overlap
        tgt_a = getattr(a, "canonical_target", None)
        tgt_b = getattr(b, "canonical_target", None)
        if tgt_a and tgt_b and tgt_a == tgt_b:
            return DimensionScore(score=0.5, reason="same target, different MOA", weight=w)

        return DimensionScore(score=0.0, reason="different MOA", weight=w)

    def _score_modality(self, a: Asset, b: Asset) -> DimensionScore:
        w = self._weights["modality"]
        if a.modality == b.modality:
            return DimensionScore(score=1.0, reason=f"same modality ({a.modality.value})", weight=w)
        if a.modality in _BIOLOGIC_ADJACENT and b.modality in _BIOLOGIC_ADJACENT:
            return DimensionScore(
                score=0.3,
                reason=f"both biologic-adjacent ({a.modality.value} vs {b.modality.value})",
                weight=w,
            )
        return DimensionScore(
            score=0.0,
            reason=f"different modality ({a.modality.value} vs {b.modality.value})",
            weight=w,
        )

    def _score_stage(self, a: Asset, b: Asset) -> DimensionScore:
        w = self._weights["stage"]
        prox = stage_proximity_score(a.stage, b.stage)
        if prox == 1.0:
            reason = f"same stage ({a.stage.value})"
        else:
            reason = f"stage proximity {prox:.2f} ({a.stage.value} vs {b.stage.value})"
        return DimensionScore(score=prox, reason=reason, weight=w)
