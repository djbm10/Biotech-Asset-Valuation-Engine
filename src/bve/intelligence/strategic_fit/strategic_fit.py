"""
Strategic fit scoring — acquirer pipeline gap analysis (Sprint 13).

Matches a universe asset (from universe_params.yaml) against an acquirer profile
(from acquirer_profiles.yaml) to produce a deterministic, interpretable fit score.

Scoring formula
---------------
total = ta_match × 0.35 + stage × 0.20 + mechanism_novelty × 0.30 + commercial × 0.15
avoid_penalty: if triggered, total is reduced by 0.40 (floor at 0.0)

Usage
-----
    from bve.intelligence.strategic_fit.strategic_fit import score_fit, load_acquirer_profiles

    profiles = load_acquirer_profiles()
    asset = {
        "ticker": "VKTX",
        "ta": "other",          # from universe_params.yaml — maps via TA_ALIAS_MAP
        "phase": "phase_3",
        "program_label": "VK2735 — obesity (oral + subcutaneous)",
        "peak_sales_millions": 4500,
        "modality": "small_molecule",
    }
    result = score_fit(asset, profiles["lilly"])
    print(result.total, result.rationale)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

_PROFILES_PATH = Path(__file__).parent / "acquirer_profiles.yaml"

# Map universe_params.yaml `ta` values to acquirer profile TA priority keys.
# Keys are universe_params ta values; values are lists of matching profile keys.
_TA_MAP: dict[str, list[str]] = {
    "oncology": ["oncology_solid_tumor", "oncology"],
    "cardiovascular": ["cardiovascular"],
    "immunology": ["immunology", "inflammation"],
    "rare_disease": ["rare_disease", "rare_blood_disease", "rare_endocrine"],
    "neurology": ["neurodegeneration"],
    "metabolic": ["metabolic"],
    "gene_therapy": ["rare_disease"],   # gene therapy often targets rare disease
    "other": [],                         # no direct TA mapping; score via program_label text
}

# Stage ordering for min_phase enforcement
_STAGE_ORDER = {
    "preclinical": 0,
    "phase_1": 1,
    "phase_2": 2,
    "phase_3": 3,
    "nda_bla": 4,
    "approved": 5,
    "commercial": 5,
}


@dataclass
class StrategicFitScore:
    """Fit between one universe asset and one acquirer."""

    ticker: str
    acquirer: str                          # acquirer key (e.g. "pfizer")
    acquirer_name: str                     # human-readable name
    ta_match_score: float                  # 0-1: TA priority match
    stage_score: float                     # 0-1: stage preference match
    mechanism_novelty_score: float         # 0-1: fills a mechanism gap
    commercial_fit_score: float            # 0-1: deal size in range × market overlap
    avoid_penalty: float                   # 0 or 0.40: triggered if in avoid list
    total: float                           # weighted sum after penalty
    rationale: list[str] = field(default_factory=list)


def load_acquirer_profiles(path: Optional[Path] = None) -> dict[str, dict]:
    """Load acquirer_profiles.yaml and return as {key: profile_dict}."""
    p = path or _PROFILES_PATH
    with open(p) as fh:
        data = yaml.safe_load(fh)
    # Top-level keys are acquirer IDs (pfizer, lilly, novo_nordisk)
    return {k: v for k, v in data.items()}


def score_fit(
    asset_profile: dict,
    acquirer_profile: dict,
) -> StrategicFitScore:
    """
    Score the strategic fit between one asset and one acquirer.

    Parameters
    ----------
    asset_profile   : dict with keys: ticker, ta, phase, program_label,
                      peak_sales_millions, modality (all from universe_params.yaml)
    acquirer_profile: one entry from acquirer_profiles.yaml (already loaded dict)

    Returns
    -------
    StrategicFitScore with component scores, total, and rationale list.
    """
    ticker = asset_profile.get("ticker", "UNKNOWN")
    acquirer_name = acquirer_profile.get("name", "Unknown")
    rationale: list[str] = []

    ta_score = _score_ta(asset_profile, acquirer_profile, rationale)
    stage_score = _score_stage(asset_profile, acquirer_profile, rationale)
    mechanism_score = _score_mechanism(asset_profile, acquirer_profile, rationale)
    commercial_score = _score_commercial(asset_profile, acquirer_profile, rationale)
    avoid_penalty = _score_avoid(asset_profile, acquirer_profile, rationale)

    raw = (
        ta_score * 0.35
        + stage_score * 0.20
        + mechanism_score * 0.30
        + commercial_score * 0.15
    )
    total = max(0.0, round(raw - avoid_penalty, 4))

    return StrategicFitScore(
        ticker=ticker,
        acquirer=_acquirer_key(acquirer_profile),
        acquirer_name=acquirer_name,
        ta_match_score=round(ta_score, 4),
        stage_score=round(stage_score, 4),
        mechanism_novelty_score=round(mechanism_score, 4),
        commercial_fit_score=round(commercial_score, 4),
        avoid_penalty=round(avoid_penalty, 4),
        total=total,
        rationale=rationale,
    )


def score_all_acquirers(
    asset_profile: dict,
    profiles: dict[str, dict],
) -> list[StrategicFitScore]:
    """
    Score one asset against all loaded acquirer profiles.

    Returns list sorted by total descending.
    """
    scores = [score_fit(asset_profile, profile) for profile in profiles.values()]
    scores.sort(key=lambda s: s.total, reverse=True)
    return scores


def best_fit(
    asset_profile: dict,
    profiles: dict[str, dict],
) -> StrategicFitScore:
    """Return the single highest-scoring acquirer for this asset."""
    return score_all_acquirers(asset_profile, profiles)[0]


# ---------------------------------------------------------------------------
# Component scorers
# ---------------------------------------------------------------------------

def _score_ta(asset: dict, profile: dict, rationale: list[str]) -> float:
    """TA priority score: highest weight among matching TA keys."""
    ta_priorities: dict = profile.get("ta_priorities", {})
    if not ta_priorities:
        rationale.append("TA: no priorities defined — neutral 0.50")
        return 0.50

    asset_ta = (asset.get("ta") or "other").lower()
    candidate_keys = _TA_MAP.get(asset_ta, [])

    # Also scan program_label text for TA keywords
    label_tokens = _tokens(asset.get("program_label", ""))

    best_weight = 0.0
    best_key = None
    for ta_key, weight in ta_priorities.items():
        if ta_key in candidate_keys:
            if weight > best_weight:
                best_weight = weight
                best_key = ta_key
        # fuzzy: check if ta_key words appear in label
        elif any(word in label_tokens for word in ta_key.lower().replace("_", " ").split()):
            if weight > best_weight:
                best_weight = weight
                best_key = ta_key + " (label-match)"

    if best_key is not None:
        rationale.append(f"TA: matched '{best_key}' priority weight={best_weight:.2f}")
        return best_weight
    else:
        rationale.append(f"TA: no match for asset_ta='{asset_ta}' — score 0.0")
        return 0.0


def _score_stage(asset: dict, profile: dict, rationale: list[str]) -> float:
    """Stage preference score based on acquirer's weight_by_stage table."""
    stage_pref: dict = profile.get("stage_preference", {})
    asset_stage = (asset.get("phase") or "").lower()

    weight_by_stage: dict = stage_pref.get("weight_by_stage", {})
    if not weight_by_stage:
        rationale.append("Stage: no stage preference — neutral 0.50")
        return 0.50

    # Enforce min_phase
    min_phase = stage_pref.get("min_phase")
    if min_phase is not None:
        min_stage_str = f"phase_{min_phase}" if isinstance(min_phase, int) else str(min_phase)
        asset_order = _STAGE_ORDER.get(asset_stage, -1)
        min_order = _STAGE_ORDER.get(min_stage_str, 0)
        if asset_order < min_order:
            rationale.append(
                f"Stage: {asset_stage} below min_phase '{min_stage_str}' — score 0.0"
            )
            return 0.0

    score = weight_by_stage.get(asset_stage, 0.0)
    if score > 0:
        rationale.append(f"Stage: '{asset_stage}' weight={score:.2f}")
    else:
        # Stage not in table but above min — give partial credit
        score = 0.40
        rationale.append(
            f"Stage: '{asset_stage}' not in weight table, above min — partial 0.40"
        )
    return score


def _score_mechanism(asset: dict, profile: dict, rationale: list[str]) -> float:
    """
    Mechanism novelty score: does the asset fill a mechanism gap?

    Uses substring/token matching between mechanism_gaps list and
    (program_label + modality + ta) tokens.
    """
    mechanism_gaps: list[str] = profile.get("mechanism_gaps", [])
    if not mechanism_gaps:
        rationale.append("Mechanism: no gaps defined — neutral 0.50")
        return 0.50

    search_text = " ".join([
        asset.get("program_label", ""),
        asset.get("modality", ""),
        asset.get("ta", ""),
    ]).lower()

    matched_gaps = []
    for gap in mechanism_gaps:
        gap_tokens = _tokens(gap)
        if all(tok in search_text for tok in gap_tokens):
            matched_gaps.append(gap)

    if matched_gaps:
        score = min(1.0, 0.60 + 0.20 * len(matched_gaps))
        rationale.append(f"Mechanism: fills gaps {matched_gaps} — score {score:.2f}")
        return score
    else:
        rationale.append("Mechanism: no gap match — score 0.0")
        return 0.0


def _score_commercial(asset: dict, profile: dict, rationale: list[str]) -> float:
    """
    Commercial fit score: peak_sales_millions within acquirer's deal_size_range.

    We use peak_sales as a proxy for deal value (typically ~3–6× peak sales
    for Phase 3 assets). Score is 1.0 if the implied deal range overlaps the
    acquirer's sweet spot, 0.50 if borderline, 0.0 if clearly outside.
    """
    deal_range = profile.get("deal_size_range_m")
    peak_sales = asset.get("peak_sales_millions", 0)

    if not deal_range or not peak_sales:
        rationale.append("Commercial: insufficient data — neutral 0.50")
        return 0.50

    lo, hi = float(deal_range[0]), float(deal_range[1])
    # Implied deal value range: 2× – 5× peak sales (acquisition premium + pipeline)
    implied_lo = peak_sales * 2.0
    implied_hi = peak_sales * 5.0

    # Full overlap
    if implied_lo <= hi and implied_hi >= lo:
        overlap = min(implied_hi, hi) - max(implied_lo, lo)
        total_span = implied_hi - implied_lo
        score = round(min(1.0, overlap / max(total_span, 1.0)), 3)
        rationale.append(
            f"Commercial: implied deal ${implied_lo:.0f}M–${implied_hi:.0f}M "
            f"vs acquirer range ${lo:.0f}M–${hi:.0f}M — overlap score {score:.2f}"
        )
        return max(0.20, score)  # floor at 0.20 for any overlap
    else:
        if implied_hi < lo:
            rationale.append(
                f"Commercial: implied deal ${implied_hi:.0f}M below acquirer min "
                f"${lo:.0f}M — score 0.10"
            )
        else:
            rationale.append(
                f"Commercial: implied deal ${implied_lo:.0f}M above acquirer max "
                f"${hi:.0f}M — score 0.10"
            )
        return 0.10


def _score_avoid(asset: dict, profile: dict, rationale: list[str]) -> float:
    """Return 0.40 penalty if any avoid keyword matches asset profile."""
    avoid_list: list[str] = profile.get("avoid", [])
    if not avoid_list:
        return 0.0

    search_text = " ".join([
        asset.get("program_label", ""),
        asset.get("modality", ""),
        asset.get("ta", ""),
    ]).lower()

    for avoid_term in avoid_list:
        avoid_tokens = _tokens(avoid_term)
        if all(tok in search_text for tok in avoid_tokens):
            rationale.append(
                f"AVOID: '{avoid_term}' triggered — penalty 0.40"
            )
            return 0.40
    return 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tokens(text: str) -> set[str]:
    """Return set of lowercase word tokens, stripping punctuation."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _acquirer_key(profile: dict) -> str:
    """Derive the YAML key (acquirer_id) from the profile dict's name field."""
    name = profile.get("name", "unknown")
    return name.lower().replace(" ", "_").replace(".", "")
