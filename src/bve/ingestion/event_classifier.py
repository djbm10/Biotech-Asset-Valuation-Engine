"""
Rule-based event classifier for biotech headlines.

Converts free-text headlines/summaries into structured EventClassification objects
that drive bounded score-delta updates in the M&A scoring model.

Design principles:
  1. No LLM dependency — deterministic, testable, zero API cost.
  2. Score deltas apply to M&A feature scores, NOT the final M&A probability.
     The calibrated probability is recomputed from updated features; it is never
     directly patched by a headline.
  3. Single-event caps prevent overreaction to any one headline.
  4. Confidence is reduced for hedged/ambiguous language.
  5. Source-type weights initial confidence (regulatory filing > press release > news).

Event taxonomy (24 types across 4 domains):
  Clinical: positive/negative/mixed per phase, trial start/delay/discontinuation
  Regulatory: FDA approval, CRL, BTD, Fast Track, Orphan, AdCom, PDUFA, NDA accepted
  Financial/BD: equity raise, cash low, restructuring, strategic review,
                licensing deal, partnership, asset sale
  Acquirer: BD appetite, large deal (digesting), patent cliff
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# ---------------------------------------------------------------------------
# Event type constants
# ---------------------------------------------------------------------------

CLINICAL_POSITIVE_PH3 = "clinical_positive_ph3"
CLINICAL_POSITIVE_PH2 = "clinical_positive_ph2"
CLINICAL_POSITIVE_PH1 = "clinical_positive_ph1"
CLINICAL_POSITIVE = "clinical_positive"
CLINICAL_MIXED = "clinical_mixed"
CLINICAL_NEGATIVE_PH3 = "clinical_negative_ph3"
CLINICAL_NEGATIVE_PH2 = "clinical_negative_ph2"
CLINICAL_NEGATIVE_PH1 = "clinical_negative_ph1"
CLINICAL_NEGATIVE = "clinical_negative"
TRIAL_START = "trial_start"
TRIAL_DELAY = "trial_delay"
TRIAL_DISCONTINUATION = "trial_discontinuation"
FDA_APPROVAL = "fda_approval"
CRL = "crl"
BTD = "btd"
FAST_TRACK = "fast_track"
ORPHAN = "orphan"
ADCOM_POSITIVE = "adcom_positive"
ADCOM_NEGATIVE = "adcom_negative"
PDUFA = "pdufa"
NDA_ACCEPTED = "nda_accepted"
EQUITY_RAISE = "equity_raise"
CASH_LOW = "cash_low"
RESTRUCTURING = "restructuring"
STRATEGIC_REVIEW = "strategic_review"
LICENSING_DEAL = "licensing_deal"
PARTNERSHIP = "partnership"
ASSET_SALE = "asset_sale"
ACQUIRER_BD_APPETITE = "acquirer_bd_appetite"
ACQUIRER_LARGE_DEAL = "acquirer_large_deal"
PATENT_CLIFF = "patent_cliff"
UNCLASSIFIED = "unclassified"

# ---------------------------------------------------------------------------
# Score delta map
# ---------------------------------------------------------------------------
# Feature keys: asset_quality | seller_willingness | acquirer_fit | catalyst_timing
#
# All values are base deltas applied BEFORE confidence weighting.
# Clinical deltas are additionally multiplied by confidence in classify_headline().
# Acquirer-side events (ACQUIRER_*) apply to the ACQUIRER profile, not the target.

SCORE_DELTA_MAP: dict[str, dict[str, float]] = {
    CLINICAL_POSITIVE_PH3:      {"asset_quality": +0.12, "catalyst_timing": +0.05},
    CLINICAL_POSITIVE_PH2:      {"asset_quality": +0.07, "catalyst_timing": +0.03},
    CLINICAL_POSITIVE_PH1:      {"asset_quality": +0.03},
    CLINICAL_POSITIVE:          {"asset_quality": +0.04},
    CLINICAL_MIXED:              {"asset_quality": -0.02},
    CLINICAL_NEGATIVE_PH3:      {"asset_quality": -0.25, "seller_willingness": +0.08},
    CLINICAL_NEGATIVE_PH2:      {"asset_quality": -0.15, "seller_willingness": +0.04},
    CLINICAL_NEGATIVE_PH1:      {"asset_quality": -0.06},
    CLINICAL_NEGATIVE:          {"asset_quality": -0.10},
    TRIAL_START:                 {"asset_quality": +0.01},
    TRIAL_DELAY:                 {"asset_quality": -0.03, "seller_willingness": +0.02},
    TRIAL_DISCONTINUATION:      {"asset_quality": -0.20, "seller_willingness": +0.10},
    FDA_APPROVAL:                {"asset_quality": +0.15},
    CRL:                         {"asset_quality": -0.25, "seller_willingness": +0.10},
    BTD:                         {"asset_quality": +0.08},
    FAST_TRACK:                  {"asset_quality": +0.03},
    ORPHAN:                      {"asset_quality": +0.02},
    ADCOM_POSITIVE:              {"asset_quality": +0.08},
    ADCOM_NEGATIVE:              {"asset_quality": -0.15},
    PDUFA:                       {"catalyst_timing": +0.05},
    NDA_ACCEPTED:                {"asset_quality": +0.04, "catalyst_timing": +0.08},
    EQUITY_RAISE:                {"seller_willingness": -0.08},   # more cash → less sell pressure
    CASH_LOW:                    {"seller_willingness": +0.12},
    RESTRUCTURING:               {"seller_willingness": +0.10},
    STRATEGIC_REVIEW:            {"seller_willingness": +0.20},
    LICENSING_DEAL:              {"asset_quality": +0.04, "seller_willingness": -0.05},
    PARTNERSHIP:                 {"asset_quality": +0.02},
    ASSET_SALE:                  {"seller_willingness": +0.08},
    ACQUIRER_BD_APPETITE:        {"acquirer_fit": +0.03},
    ACQUIRER_LARGE_DEAL:         {"acquirer_fit": -0.05},          # digesting, less capacity
    PATENT_CLIFF:                {"acquirer_fit": +0.06},          # creates pipeline gap
    UNCLASSIFIED:                {},
}

# Maximum absolute delta a single event may apply to any one feature.
MAX_SINGLE_EVENT_DELTA: dict[str, float] = {
    "asset_quality":      0.25,
    "seller_willingness": 0.30,
    "acquirer_fit":       0.10,
    "catalyst_timing":    0.10,
}

# Source-type multipliers applied to base confidence.
SOURCE_CONFIDENCE_WEIGHTS: dict[str, float] = {
    "clinicaltrials_gov": 0.95,
    "fda_website":        0.95,
    "sec_filing":         0.90,
    "pubmed":             0.88,
    "press_release":      0.80,
    "news_article":       0.70,
    "manual":             0.75,
}

# ---------------------------------------------------------------------------
# EventClassification output type
# ---------------------------------------------------------------------------


@dataclass
class EventClassification:
    ticker: str
    event_type: str
    direction: str                  # positive | negative | mixed | neutral | unknown
    phase_detected: Optional[str]   # "Phase 1" | "Phase 2" | "Phase 3" | None
    confidence: float               # 0.0–1.0
    score_deltas: dict[str, float]  # feature → bounded, confidence-weighted delta
    source_type: str
    raw_text: str
    classified_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    match_reasons: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pattern library
# ---------------------------------------------------------------------------

_PHASE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bphase[\s\-]?3\b", re.I), "Phase 3"),
    (re.compile(r"\bphase[\s\-]?2\b", re.I), "Phase 2"),
    (re.compile(r"\bphase[\s\-]?1\b", re.I), "Phase 1"),
    (re.compile(r"\bphase[\s\-]?[23]/[34]\b", re.I), "Phase 3"),  # 2/3 or 3/4 → Ph3
    (re.compile(r"\bpivotal\b", re.I), "Phase 3"),                 # pivotal = Ph3
]

_HEDGE_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.I)
    for p in [
        r"\bnot statistically significant\b",
        r"\bdid not\b",
        r"\bfailed\b",
        r"\btend.{0,15}not significant\b",
        r"\bnumerically (better|improved|lower|higher).{0,30}not significant\b",
        r"\bmay not\b",
        r"\bcould not\b",
    ]
]

_CLINICAL_POS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bmet\b.{0,50}\bprimary endpoint\b", re.I), "met_primary"),
    (re.compile(r"\bprimary endpoint\b.{0,60}\b(achieved|met|reached)\b", re.I), "endpoint_achieved"),
    (re.compile(r"\bpositive\b.{0,40}\bphase[\s\-]?[123]\b", re.I), "positive_phase"),
    (re.compile(r"\bphase[\s\-]?[123]\b.{0,40}\bpositive\b", re.I), "positive_phase"),
    (re.compile(r"\bstatistically significant\b.{0,60}\b(reduction|improvement|efficacy|benefit|response)\b", re.I), "statistically_significant"),
    (re.compile(r"\bdemonstrated\b.{0,50}\b(efficacy|clinical benefit|significant improvement)\b", re.I), "demonstrated_efficacy"),
    (re.compile(r"\bshowed\b.{0,40}\b(significant|meaningful)\b.{0,30}\b(reduction|improvement|response)\b", re.I), "showed_improvement"),
    (re.compile(r"\bpivotal\b.{0,30}\b(success|positive|met|met primary)\b", re.I), "pivotal_success"),
    (re.compile(r"\b(superiority|superior)\b.{0,40}\b(demonstrated|shown|achieved|over)\b", re.I), "superiority_shown"),
    (re.compile(r"\b(demonstrated|shown|achieved)\b.{0,40}\b(superiority|superior)\b", re.I), "superiority_shown"),
]

_CLINICAL_NEG: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bdid not meet\b.{0,50}\bprimary endpoint\b", re.I), "did_not_meet_primary"),
    (re.compile(r"\bfailed to meet\b", re.I), "failed_to_meet"),
    (re.compile(r"\btrial\b.{0,10}\b(failed|discontinued|terminated)\b", re.I), "trial_failed"),
    (re.compile(r"\bnegative\b.{0,40}\bphase[\s\-]?[123]\b", re.I), "negative_phase"),
    (re.compile(r"\bphase[\s\-]?[123]\b.{0,40}\bnegative\b", re.I), "negative_phase"),
    (re.compile(r"\bprimary endpoint\b.{0,60}\b(not met|failed|missed|did not)\b", re.I), "endpoint_missed"),
    (re.compile(r"\bstudy did not\b.{0,50}\bdemonstrate\b", re.I), "study_failed"),
    (re.compile(r"\bmissed\b.{0,20}\bprimary\b", re.I), "missed_primary"),
    (re.compile(r"\bdoes not meet\b", re.I), "does_not_meet"),
]

_CLINICAL_MIXED: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bmet secondary\b.{0,50}\bnot primary\b", re.I), "secondary_not_primary"),
    (re.compile(r"\bprimary\b.{0,40}\bnot met\b.{0,40}\bsecondary\b", re.I), "primary_not_met"),
    (re.compile(r"\bmixed results\b", re.I), "mixed_results"),
    (re.compile(r"\btrend\b.{0,30}\bnot statistically significant\b", re.I), "trend_not_sig"),
    (re.compile(r"\bnumerically (better|improved|lower)\b.{0,50}\bnot significant\b", re.I), "numerical_not_sig"),
    (re.compile(r"\bexploratory (endpoint|analysis)\b", re.I), "exploratory_only"),
]

_REGULATORY: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bFDA.{0,20}approv(ed|al)\b", re.I), FDA_APPROVAL),
    (re.compile(r"\bapprov(ed|al).{0,30}\bFDA\b", re.I), FDA_APPROVAL),
    (re.compile(r"\bcomplete response letter\b", re.I), CRL),
    (re.compile(r"\bCRL\b"), CRL),
    (re.compile(r"\bbreakthrough therapy designation\b", re.I), BTD),
    (re.compile(r"\bbreakthrough designation\b", re.I), BTD),
    (re.compile(r"\bBTD\b"), BTD),
    (re.compile(r"\bfast.?track designation\b", re.I), FAST_TRACK),
    (re.compile(r"\bfast.?track\b.{0,20}\bgranted\b", re.I), FAST_TRACK),
    (re.compile(r"\borphan drug designation\b", re.I), ORPHAN),
    (re.compile(r"\borphan designation\b", re.I), ORPHAN),
    (re.compile(r"\bPDUFA date\b", re.I), PDUFA),
    (re.compile(r"\b(NDA|BLA)\b.{0,20}\b(accept(ed|s|ance)|acceptance for review)\b", re.I), NDA_ACCEPTED),
    (re.compile(r"\baccept(ed|s)\b.{0,10}\b(NDA|BLA)\b", re.I), NDA_ACCEPTED),
    (re.compile(r"\badvisory committee\b.{0,60}\b(voted (for|in favor)|recommended|positive|approved|supports)\b", re.I), ADCOM_POSITIVE),
    (re.compile(r"\badvisory committee\b.{0,50}\b(against|negative|rejected|declined|voted against)\b", re.I), ADCOM_NEGATIVE),
    (re.compile(r"\badcom\b.{0,20}\b(positive|recommended)\b", re.I), ADCOM_POSITIVE),
    (re.compile(r"\badcom\b.{0,20}\b(negative|against)\b", re.I), ADCOM_NEGATIVE),
]

_FINANCIAL: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bstrategic (alternatives|review|transaction|process)\b", re.I), STRATEGIC_REVIEW),
    (re.compile(r"\bexploring (strategic|options|alternatives)\b", re.I), STRATEGIC_REVIEW),
    (re.compile(r"\bpotential (sale|merger|acquisition|transaction)\b", re.I), STRATEGIC_REVIEW),
    (re.compile(r"\breduction in force\b", re.I), RESTRUCTURING),
    (re.compile(r"\bworkforce reduction\b", re.I), RESTRUCTURING),
    (re.compile(r"\blayoffs?\b", re.I), RESTRUCTURING),
    (re.compile(r"\brestructuring\b.{0,60}\b(plan|announced|workforce|charges)\b", re.I), RESTRUCTURING),
    (re.compile(r"\b(public offering|private placement|registered direct|at.?the.?market offering)\b", re.I), EQUITY_RAISE),
    (re.compile(r"\braised?\b.{0,10}\$[0-9]+(\.[0-9]+)?\s*(M|B|million|billion)\b", re.I), EQUITY_RAISE),
    (re.compile(r"\bpricing of\b.{0,30}\boffering\b", re.I), EQUITY_RAISE),
    (re.compile(r"\bcash runway\b.{0,40}\b(less than|approximately|only|through)\b", re.I), CASH_LOW),
    (re.compile(r"\bfund.{0,30}operations.{0,30}\b(12|9|6) months\b", re.I), CASH_LOW),
    (re.compile(r"\bcash and cash equivalents\b.{0,30}\$[0-9]+", re.I), CASH_LOW),
    (re.compile(r"\blicense agreement\b", re.I), LICENSING_DEAL),
    (re.compile(r"\bcollaboration agreement\b", re.I), LICENSING_DEAL),
    (re.compile(r"\bco.?development agreement\b", re.I), PARTNERSHIP),
    (re.compile(r"\bpartnership\b.{0,40}\b(announced|entered|signed|agreement)\b", re.I), PARTNERSHIP),
    (re.compile(r"\basset sale\b", re.I), ASSET_SALE),
    (re.compile(r"\bdivestiture\b", re.I), ASSET_SALE),
    (re.compile(r"\btrial (started|initiated|began|opened enrollment)\b", re.I), TRIAL_START),
    (re.compile(r"\bfirst patient (dosed|enrolled|treated)\b", re.I), TRIAL_START),
    (re.compile(r"\b(doses|dosing|dosed|enrolled|treated)\b.{0,15}\bfirst patient\b", re.I), TRIAL_START),
    (re.compile(r"\btrial.{0,20}\bdelay(ed|s)?\b", re.I), TRIAL_DELAY),
    (re.compile(r"\bclinical hold\b", re.I), TRIAL_DELAY),
    (re.compile(r"\btrial\b.{0,20}\b(terminat(ed|es)|discontinu(ed|es|ing)|stopped early)\b", re.I), TRIAL_DISCONTINUATION),
    (re.compile(r"\b(discontinu(ed|es|ing)|terminat(ed|es))\b.{0,20}\b(phase|trial|study)\b", re.I), TRIAL_DISCONTINUATION),
]

_ACQUIRER: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bbusiness development\b.{0,40}\b(priority|focus|appetite|active|remains)\b", re.I), ACQUIRER_BD_APPETITE),
    (re.compile(r"\bbolt.?on (acquisition|deal)\b", re.I), ACQUIRER_BD_APPETITE),
    (re.compile(r"\bactively (seeking|pursuing|looking for) (acquisitions|targets|deals)\b", re.I), ACQUIRER_BD_APPETITE),
    (re.compile(r"\bstrategic transactions\b.{0,40}\b(remain|continue|priorit)\b", re.I), ACQUIRER_BD_APPETITE),
    (re.compile(r"\bcompleted acquisition of\b", re.I), ACQUIRER_LARGE_DEAL),
    (re.compile(r"\bacquired\b.{0,30}\bfor \$[0-9]+(\.[0-9]+)?\s*(B|billion)\b", re.I), ACQUIRER_LARGE_DEAL),
    (re.compile(r"\bpatent cliff\b", re.I), PATENT_CLIFF),
    (re.compile(r"\bloss of exclusivity\b", re.I), PATENT_CLIFF),
    (re.compile(r"\bLOE\b.{0,30}\b(20[0-9]{2})\b"), PATENT_CLIFF),
]

# Direction lookup for non-clinical events
_DIRECTION_MAP: dict[str, str] = {
    FDA_APPROVAL:        "positive",
    BTD:                 "positive",
    FAST_TRACK:          "positive",
    ORPHAN:              "positive",
    NDA_ACCEPTED:        "positive",
    ADCOM_POSITIVE:      "positive",
    PDUFA:               "neutral",
    CRL:                 "negative",
    ADCOM_NEGATIVE:      "negative",
    STRATEGIC_REVIEW:    "mixed",
    RESTRUCTURING:       "negative",
    EQUITY_RAISE:        "neutral",
    CASH_LOW:            "negative",
    LICENSING_DEAL:      "positive",
    PARTNERSHIP:         "positive",
    ASSET_SALE:          "mixed",
    TRIAL_START:         "positive",
    TRIAL_DELAY:         "negative",
    TRIAL_DISCONTINUATION: "negative",
    ACQUIRER_BD_APPETITE: "positive",
    ACQUIRER_LARGE_DEAL:  "negative",
    PATENT_CLIFF:         "mixed",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _detect_phase(text: str) -> Optional[str]:
    for pattern, phase in _PHASE_PATTERNS:
        if pattern.search(text):
            return phase
    return None


def _has_hedging(text: str) -> bool:
    return any(p.search(text) for p in _HEDGE_PATTERNS)


def _apply_caps(raw_deltas: dict[str, float]) -> dict[str, float]:
    """Clamp each delta to MAX_SINGLE_EVENT_DELTA."""
    result = {}
    for feature, delta in raw_deltas.items():
        cap = MAX_SINGLE_EVENT_DELTA.get(feature, 0.20)
        result[feature] = max(-cap, min(cap, delta))
    return result


def _classify_clinical(
    text: str, phase: Optional[str]
) -> tuple[str, str, list[str]]:
    """Return (event_type, direction, match_reasons)."""
    pos_hits = [label for pat, label in _CLINICAL_POS if pat.search(text)]
    neg_hits = [label for pat, label in _CLINICAL_NEG if pat.search(text)]
    mixed_hits = [label for pat, label in _CLINICAL_MIXED if pat.search(text)]

    if mixed_hits:
        return CLINICAL_MIXED, "mixed", mixed_hits

    if neg_hits:
        if phase == "Phase 3":
            return CLINICAL_NEGATIVE_PH3, "negative", neg_hits
        if phase == "Phase 2":
            return CLINICAL_NEGATIVE_PH2, "negative", neg_hits
        if phase == "Phase 1":
            return CLINICAL_NEGATIVE_PH1, "negative", neg_hits
        return CLINICAL_NEGATIVE, "negative", neg_hits

    if pos_hits:
        if phase == "Phase 3":
            return CLINICAL_POSITIVE_PH3, "positive", pos_hits
        if phase == "Phase 2":
            return CLINICAL_POSITIVE_PH2, "positive", pos_hits
        if phase == "Phase 1":
            return CLINICAL_POSITIVE_PH1, "positive", pos_hits
        return CLINICAL_POSITIVE, "positive", pos_hits

    return UNCLASSIFIED, "unknown", []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_headline(
    text: str,
    ticker: str,
    source_type: str = "news_article",
) -> EventClassification:
    """
    Classify a biotech headline or summary into a structured event.

    Priority order:
      1. Regulatory (most specific)
      2. Financial / BD
      3. Acquirer signals
      4. Clinical (most general — matched last to avoid false positives)

    Parameters
    ----------
    text:
        Headline or short summary.
    ticker:
        Company ticker for attribution.
    source_type:
        One of the SOURCE_CONFIDENCE_WEIGHTS keys.

    Returns
    -------
    EventClassification with event_type, direction, score_deltas, confidence.
    """
    text_norm = text.strip()
    phase = _detect_phase(text_norm)
    base_conf = SOURCE_CONFIDENCE_WEIGHTS.get(source_type, 0.70)
    hedge = _has_hedging(text_norm)

    # ── 1. Regulatory ──────────────────────────────────────────────────────
    for pattern, event_type in _REGULATORY:
        if pattern.search(text_norm):
            conf = round(base_conf * (0.85 if hedge else 1.0), 3)
            raw = dict(SCORE_DELTA_MAP.get(event_type, {}))
            return EventClassification(
                ticker=ticker,
                event_type=event_type,
                direction=_DIRECTION_MAP.get(event_type, "neutral"),
                phase_detected=phase,
                confidence=conf,
                score_deltas=_apply_caps(raw),
                source_type=source_type,
                raw_text=text_norm,
                match_reasons=[event_type],
            )

    # ── 2. Financial / BD ──────────────────────────────────────────────────
    for pattern, event_type in _FINANCIAL:
        if pattern.search(text_norm):
            conf = round(base_conf * (0.80 if hedge else 1.0), 3)
            raw = dict(SCORE_DELTA_MAP.get(event_type, {}))
            return EventClassification(
                ticker=ticker,
                event_type=event_type,
                direction=_DIRECTION_MAP.get(event_type, "neutral"),
                phase_detected=phase,
                confidence=conf,
                score_deltas=_apply_caps(raw),
                source_type=source_type,
                raw_text=text_norm,
                match_reasons=[event_type],
            )

    # ── 3. Acquirer signals ────────────────────────────────────────────────
    for pattern, event_type in _ACQUIRER:
        if pattern.search(text_norm):
            conf = round(base_conf * 0.80, 3)  # acquirer signals are indirect
            raw = dict(SCORE_DELTA_MAP.get(event_type, {}))
            return EventClassification(
                ticker=ticker,
                event_type=event_type,
                direction=_DIRECTION_MAP.get(event_type, "neutral"),
                phase_detected=phase,
                confidence=conf,
                score_deltas=_apply_caps(raw),
                source_type=source_type,
                raw_text=text_norm,
                match_reasons=[event_type],
            )

    # ── 4. Clinical (general) ──────────────────────────────────────────────
    event_type, direction, match_reasons = _classify_clinical(text_norm, phase)
    if event_type != UNCLASSIFIED:
        conf = base_conf
        if hedge:
            conf *= 0.75
        if len(match_reasons) >= 2:
            conf = min(1.0, conf * 1.05)
        conf = round(conf, 3)
        raw = {k: v * conf for k, v in SCORE_DELTA_MAP.get(event_type, {}).items()}
        return EventClassification(
            ticker=ticker,
            event_type=event_type,
            direction=direction,
            phase_detected=phase,
            confidence=conf,
            score_deltas=_apply_caps(raw),
            source_type=source_type,
            raw_text=text_norm,
            match_reasons=match_reasons,
        )

    # ── Unclassified ───────────────────────────────────────────────────────
    return EventClassification(
        ticker=ticker,
        event_type=UNCLASSIFIED,
        direction="unknown",
        phase_detected=phase,
        confidence=0.0,
        score_deltas={},
        source_type=source_type,
        raw_text=text_norm,
        match_reasons=[],
    )
