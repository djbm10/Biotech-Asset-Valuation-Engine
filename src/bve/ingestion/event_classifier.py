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

from bve.ingestion.model_versions import CLASSIFIER_VERSION, DELTA_MAP_VERSION

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
DEAL_TERMINATED = "deal_terminated"
GOING_CONCERN = "going_concern"
DELISTING_NOTICE = "delisting_notice"
GUIDANCE_RAISED = "guidance_raised"
GUIDANCE_LOWERED = "guidance_lowered"
# Target-side M&A status. This is a ROUTING / EXCLUSION signal, not a ranking
# signal: a company under a definitive agreement is already spoken for and must
# not be surfaced as a fresh opportunity. The exclusions layer keys off the
# matching listing_status "pending_acquisition" (see intelligence/exclusions).
PENDING_ACQUISITION = "pending_acquisition"
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
    # Approval: positive for quality, but catalyst has passed (timing down)
    # and seller may feel less pressure to sell now (willingness slightly down).
    FDA_APPROVAL:                {"asset_quality": +0.12, "seller_willingness": -0.05, "catalyst_timing": -0.05},
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
    DEAL_TERMINATED:             {"asset_quality": -0.10, "seller_willingness": +0.06},
    # Distress signals — strong seller-willingness pressure.
    GOING_CONCERN:               {"seller_willingness": +0.18, "asset_quality": -0.04},
    DELISTING_NOTICE:            {"seller_willingness": +0.10},
    # Guidance — modest asset-quality / sell-pressure nudges.
    GUIDANCE_RAISED:             {"asset_quality": +0.03, "seller_willingness": -0.03},
    GUIDANCE_LOWERED:            {"asset_quality": -0.03, "seller_willingness": +0.04},
    # Pending acquisition is a routing/exclusion signal — no score deltas.
    # The company is already under a definitive agreement; it must not be
    # scored as a fresh opportunity. Handled by the exclusions layer instead.
    PENDING_ACQUISITION:         {},
    # Acquirer signals — split into appetite, capacity, urgency (not overloaded acquirer_fit)
    ACQUIRER_BD_APPETITE:        {"acquirer_appetite": +0.05},
    ACQUIRER_LARGE_DEAL:         {"acquirer_appetite": -0.05, "integration_capacity": -0.08},
    PATENT_CLIFF:                {"acquirer_urgency": +0.06, "acquirer_appetite": +0.03},
    UNCLASSIFIED:                {},
}

# Maximum absolute delta a single event may apply to any one feature.
MAX_SINGLE_EVENT_DELTA: dict[str, float] = {
    "asset_quality":       0.25,
    "seller_willingness":  0.30,
    "acquirer_fit":        0.10,   # legacy key — kept for backward compat
    "acquirer_appetite":   0.10,
    "integration_capacity": 0.12,
    "acquirer_urgency":    0.10,
    "catalyst_timing":     0.10,
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


# Severity ranking — higher number = this event should be the primary label.
# Clinical failures and CRLs always dominate; routine signals rank lowest.
SEVERITY_ORDER: dict[str, int] = {
    # Clinical / regulatory failures
    CLINICAL_NEGATIVE_PH3:    100,
    CRL:                       99,
    TRIAL_DISCONTINUATION:     95,
    CLINICAL_NEGATIVE_PH2:     85,
    ADCOM_NEGATIVE:            82,
    CLINICAL_NEGATIVE_PH1:     75,
    CLINICAL_NEGATIVE:         70,
    # Positive regulatory / clinical milestones
    FDA_APPROVAL:              92,
    ADCOM_POSITIVE:            83,
    CLINICAL_POSITIVE_PH3:     80,
    BTD:                       65,
    NDA_ACCEPTED:              62,
    CLINICAL_POSITIVE_PH2:     60,
    CLINICAL_POSITIVE:         55,
    CLINICAL_POSITIVE_PH1:     50,
    # Mixed
    CLINICAL_MIXED:            45,
    # Strategic / financial
    # Pending acquisition dominates everything else for the target — it is the
    # terminal deal state and must win primary-label selection so the
    # exclusions layer routes the company correctly.
    PENDING_ACQUISITION:       98,
    GOING_CONCERN:             58,
    STRATEGIC_REVIEW:          55,
    DELISTING_NOTICE:          52,
    CASH_LOW:                  50,
    TRIAL_DELAY:               48,
    RESTRUCTURING:             45,
    DEAL_TERMINATED:           44,
    ASSET_SALE:                40,
    PATENT_CLIFF:              42,
    GUIDANCE_LOWERED:          39,
    LICENSING_DEAL:            38,
    PDUFA:                     35,
    ACQUIRER_LARGE_DEAL:       35,
    GUIDANCE_RAISED:           33,
    FAST_TRACK:                32,
    PARTNERSHIP:               32,
    EQUITY_RAISE:              30,
    ORPHAN:                    30,
    ACQUIRER_BD_APPETITE:      28,
    TRIAL_START:               25,
    # Fallback
    UNCLASSIFIED:               0,
}


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
    secondary_events: list[str] = field(default_factory=list)  # non-primary event types


@dataclass
class MultiLabelClassification:
    """
    Multi-label classification result.

    primary_event is the highest-severity match.
    secondary_events are all other matched event types.
    combined_score_deltas merges deltas from all events using
    correlation-aware aggregation (not flat 0.5x secondary discount).
    """
    ticker: str
    primary_event: str
    secondary_events: list[str]
    direction: str
    phase_detected: Optional[str]
    confidence: float
    combined_score_deltas: dict[str, float]
    source_type: str
    raw_text: str
    classified_at: str
    match_reasons: list[str]
    severity_score: int
    classifier_version: str = CLASSIFIER_VERSION
    delta_map_version: str = DELTA_MAP_VERSION


# ---------------------------------------------------------------------------
# Pattern library
# ---------------------------------------------------------------------------

_PHASE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bphase[\s\-]?[23]/[34]\b", re.I), "Phase 3"),  # 2/3 or 3/4 → Ph3
    (re.compile(r"\bphase[\s\-]?1/2\b", re.I), "Phase 2"),        # 1/2 → Ph2
    (re.compile(r"\bphase[\s\-]?3\b", re.I), "Phase 3"),
    (re.compile(r"\bphase[\s\-]?2[ab]?\b", re.I), "Phase 2"),     # 2, 2a, 2b
    (re.compile(r"\bphase[\s\-]?1[ab]?\b", re.I), "Phase 1"),     # 1, 1a, 1b
    (re.compile(r"\bpivotal\b", re.I), "Phase 3"),                 # pivotal = Ph3
]

_HEDGE_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.I)
    for p in [
        r"\bnot statistically significant\b",
        # NOTE: "did not" removed — too broad; catches "did not observe toxicities" (positive safety).
        # Specific negative outcomes captured by _CLINICAL_NEG patterns instead.
        r"\btend.{0,15}not significant\b",
        r"\bnumerically (better|improved|lower|higher).{0,30}not significant\b",
        r"\bmay not\b",
        r"\bcould not\b",
    ]
]

# Negation cues — when one of these precedes a regulatory-positive trigger
# within a short window, the positive event is suppressed (e.g. "FDA declined
# to approve", "did not approve", "fails to win approval").
_NEGATION_CUES: list[re.Pattern] = [
    re.compile(p, re.I)
    for p in [
        r"\bdeclin(e|ed|es) to\b",
        r"\bdid not\b",
        r"\bdoes not\b",
        r"\bwill not\b",
        r"\brefus(e|ed|es) to\b",
        r"\breject(s|ed)?\b",
        r"\bfail(s|ed)? to (gain|win|secure|obtain|receive)\b",
        r"\bnot (be )?approv(e|ed)\b",
    ]
]

# Speculation / rumor cues — reduce confidence and block definitive-only events
# (e.g. PENDING_ACQUISITION) from firing on unconfirmed reports.
_SPECULATION_CUES: list[re.Pattern] = [
    re.compile(p, re.I)
    for p in [
        r"\breportedly\b",
        r"\brumou?red\b",
        r"\bin talks\b",
        r"\bsaid to be\b",
        r"\bsources say\b",
        r"\baccording to (sources|reports)\b",
        r"\bcould (be|explore)\b",
        r"\bmay (be|explore|consider)\b",
        r"\bweighing\b",
        r"\bmulling\b",
    ]
]

SPECULATION_CONFIDENCE_FACTOR = 0.65

# Positive safety language that should NOT be treated as hedging.
_POSITIVE_SAFETY_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.I)
    for p in [
        r"\bdid not observe\b.{0,60}\b(dose.limiting toxicities|DLTs|serious adverse|SAEs|toxicity signals)\b",
        r"\bdid not identify\b.{0,40}\b(safety concerns|toxicity signals|safety signals)\b",
        r"\bno (dose.limiting toxicities|DLTs|serious adverse events|SAEs|unexpected safety)\b",
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

# Target-side M&A status. Definitive/firm deal language only — speculative
# "in talks" / "exploring a sale" stays in STRATEGIC_REVIEW and is additionally
# discounted by the speculation guard.
_MA_STATUS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bdefinitive\b.{0,30}\bagreement\b.{0,40}\b(acquire|be acquired|merger)\b", re.I), PENDING_ACQUISITION),
    (re.compile(r"\bagree(d|s|ment)?\b.{0,20}\bto be acquired\b", re.I), PENDING_ACQUISITION),
    (re.compile(r"\bto be acquired by\b", re.I), PENDING_ACQUISITION),
    (re.compile(r"\benter(s|ed)? into\b.{0,40}\bagreement to acquire\b", re.I), PENDING_ACQUISITION),
    (re.compile(r"\b(commenc(es|ed)|launch(es|ed))\b.{0,30}\btender offer\b", re.I), PENDING_ACQUISITION),
    (re.compile(r"\bmerger agreement\b", re.I), PENDING_ACQUISITION),
    # Collaboration / license termination — a negative for the target asset.
    (re.compile(r"\bterminat(es|ed|ion of)\b.{0,40}\b(collaboration|license|licensing|partnership|agreement)\b", re.I), DEAL_TERMINATED),
    (re.compile(r"\b(collaboration|license|licensing|partnership)\b.{0,30}\bterminat(ed|es|ion)\b", re.I), DEAL_TERMINATED),
    (re.compile(r"\bopt(s|ed)? out of\b.{0,30}\b(collaboration|agreement|program)\b", re.I), DEAL_TERMINATED),
    (re.compile(r"\breturn(s|ed)?\b.{0,20}\brights\b.{0,30}\b(to|back)\b", re.I), DEAL_TERMINATED),
]

# Financing / runway distress (more severe than routine CASH_LOW).
_DISTRESS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bgoing concern\b", re.I), GOING_CONCERN),
    (re.compile(r"\bsubstantial doubt\b.{0,40}\b(continue|operations|going concern)\b", re.I), GOING_CONCERN),
    (re.compile(r"\b(Nasdaq|NYSE)\b.{0,40}\b(delisting|deficiency|non.?compliance|minimum bid)\b", re.I), DELISTING_NOTICE),
    (re.compile(r"\bdelisting (notice|notification|determination)\b", re.I), DELISTING_NOTICE),
    (re.compile(r"\bnotice of (non.?compliance|delisting)\b", re.I), DELISTING_NOTICE),
]

# Earnings / guidance signals.
_EARNINGS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(raise[sd]?|increase[sd]?|boost(s|ed)?)\b.{0,30}\b(full.?year |fy |annual |revenue |sales )?guidance\b", re.I), GUIDANCE_RAISED),
    (re.compile(r"\b(rais(es|ed|ing)|increas(es|ed|ing))\b.{0,30}\boutlook\b", re.I), GUIDANCE_RAISED),
    (re.compile(r"\b(lower[sed]?|cut[s]?|reduce[sd]?|slash(es|ed)?|trim[s]?|trimmed)\b.{0,30}\b(full.?year |fy |annual |revenue |sales )?guidance\b", re.I), GUIDANCE_LOWERED),
    (re.compile(r"\b(lower(s|ed|ing)|cut(s|ting)?|reduc(es|ed|ing))\b.{0,30}\boutlook\b", re.I), GUIDANCE_LOWERED),
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
    DEAL_TERMINATED:     "negative",
    GOING_CONCERN:       "negative",
    DELISTING_NOTICE:    "negative",
    GUIDANCE_RAISED:     "positive",
    GUIDANCE_LOWERED:    "negative",
    PENDING_ACQUISITION: "positive",
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
    """
    Return True if the text contains hedged/ambiguous language.

    Only applies to contexts where we might otherwise classify positive.
    Positive safety language (e.g. 'did not observe toxicities') is
    explicitly excluded to avoid false negatives.
    """
    if any(p.search(text) for p in _POSITIVE_SAFETY_PATTERNS):
        return False
    return any(p.search(text) for p in _HEDGE_PATTERNS)


# Window (characters) within which a negation cue preceding a trigger is
# considered to negate it. Kept tight so a distant unrelated "did not" clause
# does not suppress a genuine event.
_NEGATION_WINDOW = 25


def _has_speculation(text: str) -> bool:
    """Return True if the text reads as an unconfirmed report / rumor."""
    return any(p.search(text) for p in _SPECULATION_CUES)


def _is_negated(text: str, trigger_start: int) -> bool:
    """
    Return True if a negation cue ends within _NEGATION_WINDOW chars before
    the trigger match start (i.e. the negation modifies the trigger).
    """
    window_start = max(0, trigger_start - _NEGATION_WINDOW)
    preceding = text[window_start:trigger_start]
    return any(cue.search(preceding) for cue in _NEGATION_CUES)


# Regulatory-positive events that a negation cue should suppress.
_NEGATABLE_POSITIVE: frozenset[str] = frozenset({
    FDA_APPROVAL, NDA_ACCEPTED, BTD, FAST_TRACK, ORPHAN, ADCOM_POSITIVE,
})

# Definitive-only events that must not fire on speculative/rumored text.
_DEFINITIVE_ONLY: frozenset[str] = frozenset({PENDING_ACQUISITION})


_POSITIVE_CLINICAL_TYPES: frozenset[str] = frozenset({
    CLINICAL_POSITIVE_PH3, CLINICAL_POSITIVE_PH2, CLINICAL_POSITIVE_PH1, CLINICAL_POSITIVE,
})

_NEGATIVE_CLINICAL_TYPES: frozenset[str] = frozenset({
    CLINICAL_NEGATIVE_PH3, CLINICAL_NEGATIVE_PH2, CLINICAL_NEGATIVE_PH1, CLINICAL_NEGATIVE,
})


def _collect_all_events(
    text: str, phase: Optional[str]
) -> list[tuple[str, str, list[str]]]:
    """
    Collect ALL matching (event_type, direction, match_reasons) without priority filtering.

    Clinical events are mutually exclusive (the highest-severity clinical result wins).
    Regulatory, Financial, and Acquirer events can co-occur.
    Results are deduplicated by event_type.
    """
    matched: dict[str, tuple[str, list[str]]] = {}  # event_type → (direction, reasons)
    speculative = _has_speculation(text)

    # Clinical: pick the single highest-priority clinical match
    clin_type, clin_dir, clin_reasons = _classify_clinical(text, phase)
    if clin_type != UNCLASSIFIED:
        matched[clin_type] = (clin_dir, clin_reasons)

    def _consider(pattern: re.Pattern, event_type: str) -> None:
        if event_type in matched:
            return
        m = pattern.search(text)
        if not m:
            return
        # Speculation guard: definitive-only events do not fire on rumor.
        if speculative and event_type in _DEFINITIVE_ONLY:
            return
        # Negation guard: a negation cue just before a regulatory-positive
        # trigger suppresses it. "FDA declined to approve" → not an approval.
        if event_type in _NEGATABLE_POSITIVE and _is_negated(text, m.start()):
            # An explicitly negated approval is effectively a rejection.
            if event_type == FDA_APPROVAL and CRL not in matched:
                matched[CRL] = (_DIRECTION_MAP.get(CRL, "negative"), ["negated_approval"])
            return
        matched[event_type] = (_DIRECTION_MAP.get(event_type, "neutral"), [event_type])

    # Regulatory, M&A status, Financial/BD, distress, earnings, acquirer.
    for pattern, event_type in _REGULATORY:
        _consider(pattern, event_type)
    for pattern, event_type in _MA_STATUS:
        _consider(pattern, event_type)
    for pattern, event_type in _FINANCIAL:
        _consider(pattern, event_type)
    for pattern, event_type in _DISTRESS:
        _consider(pattern, event_type)
    for pattern, event_type in _EARNINGS:
        _consider(pattern, event_type)
    for pattern, event_type in _ACQUIRER:
        _consider(pattern, event_type)

    return [(et, dir_, reasons) for et, (dir_, reasons) in matched.items()]


# ---------------------------------------------------------------------------
# Correlation-aware delta merging
# ---------------------------------------------------------------------------

# Per-pair correlation discount for same-sign deltas on the same feature.
# Key: (event_type_a, event_type_b, feature) — order-insensitive lookup.
# Value: discount applied to the SMALLER delta before adding to the larger.
#   combined = max(|d1|, |d2|) + DISCOUNT * min(|d1|, |d2|)
# Lower discount → signals treated as more independent.
# Higher discount → signals treated as highly correlated (less additive).
CORRELATION_DISCOUNT_BY_PAIR: dict[tuple[str, str, str], float] = {
    # Phase 3 failure and strategic review are highly correlated seller signals
    (CLINICAL_NEGATIVE_PH3,  STRATEGIC_REVIEW,    "seller_willingness"): 0.25,
    (CLINICAL_NEGATIVE_PH2,  STRATEGIC_REVIEW,    "seller_willingness"): 0.25,
    (TRIAL_DISCONTINUATION,  STRATEGIC_REVIEW,    "seller_willingness"): 0.25,
    # Cash low + strategic review: moderate correlation
    (CASH_LOW,               STRATEGIC_REVIEW,    "seller_willingness"): 0.50,
    (CASH_LOW,               RESTRUCTURING,       "seller_willingness"): 0.50,
    # Equity raise partially offsets cash low — but they're genuinely different signals
    (EQUITY_RAISE,           CASH_LOW,            "seller_willingness"): 0.75,
    # Two clinical signals for the same company — distinct events, less correlated
    (CLINICAL_NEGATIVE_PH3,  TRIAL_DISCONTINUATION, "asset_quality"):   0.30,
}

DEFAULT_CORRELATION_DISCOUNT = 0.25  # applied to unlisted pairs


def _get_correlation_discount(evt_a: str, evt_b: str, feature: str) -> float:
    """Look up correlation discount for an event pair + feature (order-insensitive)."""
    key1 = (evt_a, evt_b, feature)
    key2 = (evt_b, evt_a, feature)
    return CORRELATION_DISCOUNT_BY_PAIR.get(key1, CORRELATION_DISCOUNT_BY_PAIR.get(key2, DEFAULT_CORRELATION_DISCOUNT))


def _apply_caps(raw_deltas: dict[str, float]) -> dict[str, float]:
    """Clamp each delta to MAX_SINGLE_EVENT_DELTA."""
    result = {}
    for feature, delta in raw_deltas.items():
        cap = MAX_SINGLE_EVENT_DELTA.get(feature, 0.20)
        result[feature] = max(-cap, min(cap, delta))
    return result


def _merge_feature_deltas(
    events: list[tuple[str, dict[str, float]]],  # (event_type, raw_deltas_for_this_event)
) -> dict[str, float]:
    """
    Merge feature deltas from multiple events using correlation-aware aggregation.

    For each feature, collect all (event_type, delta) contributions.
    Same-sign contributions use the formula:
        combined = max(|d|) + CORRELATION_DISCOUNT * min(|d|)

    The discount reflects that same-directional signals are often correlated.
    Opposite-sign contributions are summed directly (genuine counterforces).

    Result is passed through _apply_caps.

    Example:
        clinical_negative_ph3 + strategic_review → seller_willingness:
            d1 = +0.08 (clinical_negative_ph3)
            d2 = +0.20 (strategic_review)
            discount = 0.25 (from CORRELATION_DISCOUNT_BY_PAIR)
            combined = 0.20 + 0.25 * 0.08 = 0.22
    """
    # Gather per-feature: list of (event_type, signed_delta)
    by_feature: dict[str, list[tuple[str, float]]] = {}
    for evt_type, deltas in events:
        for feature, delta in deltas.items():
            by_feature.setdefault(feature, []).append((evt_type, delta))

    merged: dict[str, float] = {}
    for feature, contributions in by_feature.items():
        if len(contributions) == 1:
            merged[feature] = contributions[0][1]
            continue

        # Split by sign
        positives = [(et, d) for et, d in contributions if d > 0]
        negatives = [(et, d) for et, d in contributions if d < 0]

        def _combine_same_sign(contribs: list[tuple[str, float]]) -> float:
            """Combine same-sign contributions with pair-aware discount."""
            if not contribs:
                return 0.0
            if len(contribs) == 1:
                return contribs[0][1]
            # Sort by abs value descending
            sorted_c = sorted(contribs, key=lambda x: abs(x[1]), reverse=True)
            result = sorted_c[0][1]
            for i in range(1, len(sorted_c)):
                prev_et = sorted_c[i - 1][0]
                cur_et = sorted_c[i][0]
                discount = _get_correlation_discount(prev_et, cur_et, feature)
                result += sorted_c[i][1] * discount
            return result

        combined = _combine_same_sign(positives) + _combine_same_sign(negatives)
        merged[feature] = combined

    return _apply_caps(merged)


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


def classify_headline_multi(
    text: str,
    ticker: str,
    source_type: str = "news_article",
) -> MultiLabelClassification:
    """
    Classify a headline into a multi-label result.

    All matching event types are collected; the highest-severity event becomes
    primary_event. Secondary events contribute at 0.5× weight to the combined
    score deltas.

    Severity hierarchy (partial, from SEVERITY_ORDER):
      Clinical failure / CRL  >  FDA approval / Ph3 positive  >
      Strategic review / financing  >  Routine signals

    Hedging language reduces confidence ONLY for positive clinical primaries —
    not for negative events (which are clear bad outcomes) and not for phrases
    like 'did not observe toxicities' (positive safety signal).

    Parameters
    ----------
    text:       Headline or short summary.
    ticker:     Company ticker for attribution.
    source_type: One of the SOURCE_CONFIDENCE_WEIGHTS keys.
    """
    text_norm = text.strip()
    phase = _detect_phase(text_norm)
    base_conf = SOURCE_CONFIDENCE_WEIGHTS.get(source_type, 0.70)
    hedge = _has_hedging(text_norm)
    speculative = _has_speculation(text_norm)
    classified_at = datetime.now(timezone.utc).isoformat()

    all_events = _collect_all_events(text_norm, phase)

    if not all_events:
        return MultiLabelClassification(
            ticker=ticker,
            primary_event=UNCLASSIFIED,
            secondary_events=[],
            direction="unknown",
            phase_detected=phase,
            confidence=0.0,
            combined_score_deltas={},
            source_type=source_type,
            raw_text=text_norm,
            classified_at=classified_at,
            match_reasons=[],
            severity_score=0,
        )

    # Sort by severity descending — clinical failures dominate
    all_events.sort(key=lambda x: SEVERITY_ORDER.get(x[0], 0), reverse=True)

    primary_type, primary_dir, primary_reasons = all_events[0]
    secondary_types = [e[0] for e in all_events[1:]]

    # Confidence: hedge applies to positive clinical primaries AND mixed results.
    # (Negative clinical events are clear bad outcomes; hedging doesn't soften them.)
    _HEDGE_ELIGIBLE = _POSITIVE_CLINICAL_TYPES | {CLINICAL_MIXED}
    conf = base_conf
    if hedge and primary_type in _HEDGE_ELIGIBLE:
        conf *= 0.75
    # Speculation / rumor: unconfirmed reports are lower confidence regardless
    # of event type (an "in talks to be acquired" report is genuine news but
    # not a confirmed fact).
    if speculative:
        conf *= SPECULATION_CONFIDENCE_FACTOR
    # Multi-signal agreement: modest boost
    if len(all_events) >= 2:
        conf = min(1.0, conf * 1.02)
    # Multi-reason boost for clinical events
    if primary_type in _POSITIVE_CLINICAL_TYPES and len(primary_reasons) >= 2:
        conf = min(1.0, conf * 1.05)
    conf = round(conf, 3)

    # Build per-event delta contributions, scaling clinical events by confidence
    _ALL_CLINICAL = _POSITIVE_CLINICAL_TYPES | _NEGATIVE_CLINICAL_TYPES | {CLINICAL_MIXED}
    event_deltas: list[tuple[str, dict[str, float]]] = []
    for evt_type, _, _ in all_events:
        raw = SCORE_DELTA_MAP.get(evt_type, {})
        if evt_type in _ALL_CLINICAL:
            scaled = {k: v * conf for k, v in raw.items()}
        else:
            scaled = dict(raw)
        event_deltas.append((evt_type, scaled))

    # Correlation-aware merge — replaces flat 0.5x secondary discount
    combined = _merge_feature_deltas(event_deltas)

    return MultiLabelClassification(
        ticker=ticker,
        primary_event=primary_type,
        secondary_events=secondary_types,
        direction=primary_dir,
        phase_detected=phase,
        confidence=conf,
        combined_score_deltas=combined,
        source_type=source_type,
        raw_text=text_norm,
        classified_at=classified_at,
        match_reasons=primary_reasons,
        severity_score=SEVERITY_ORDER.get(primary_type, 0),
    )


def classify_headline(
    text: str,
    ticker: str,
    source_type: str = "news_article",
) -> EventClassification:
    """
    Classify a biotech headline into a structured event.

    Internally uses multi-label classification; returns the primary (highest-severity)
    event as an EventClassification for backward compatibility. Combined score deltas
    from all matched events are included in score_deltas. Secondary event types are
    available in secondary_events.

    Parameters
    ----------
    text:       Headline or short summary.
    ticker:     Company ticker for attribution.
    source_type: One of the SOURCE_CONFIDENCE_WEIGHTS keys.
    """
    multi = classify_headline_multi(text, ticker, source_type)
    return EventClassification(
        ticker=ticker,
        event_type=multi.primary_event,
        direction=multi.direction,
        phase_detected=multi.phase_detected,
        confidence=multi.confidence,
        score_deltas=multi.combined_score_deltas,
        source_type=source_type,
        raw_text=multi.raw_text,
        classified_at=multi.classified_at,
        match_reasons=multi.match_reasons,
        secondary_events=multi.secondary_events,
    )
