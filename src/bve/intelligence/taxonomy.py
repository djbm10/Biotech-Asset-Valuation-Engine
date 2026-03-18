"""
Event taxonomy for the biotech intelligence layer.

Defines the canonical set of event types observed in biotech development and
commercial markets, and the three change modes used to classify how each event
should propagate into valuation assumptions.

This module has zero imports from bve.* — it is the foundation that every other
intelligence module depends on.
"""
from __future__ import annotations

from enum import Enum


class EventType(str, Enum):
    """
    Canonical taxonomy of 20 biotech intelligence event types.

    Values are lowercase snake_case strings so they survive JSON round-trips
    and map directly to source document keywords (press releases, SEC filings).

    Clinical events
    ---------------
    TRIAL_READOUT           Primary endpoint results from a Phase 1/2/3 trial.
    INTERIM_ANALYSIS        DSMB/IDMC interim cut — early stop for efficacy,
                            futility, or safety.
    ENROLLMENT_UPDATE       Trial enrollment rate above, on, or below plan.
    ENDPOINT_CHANGE         Protocol amendment modifying the primary or a key
                            secondary endpoint.
    SAFETY_SIGNAL           Adverse event, SUSAR, DILI signal, or new/updated
                            black-box warning.
    CONFERENCE_PRESENTATION Data presented at a major medical conference
                            (ASCO, ASH, ADA, ACC, ESMO, EHA, AAN, etc.).
    PUBLICATION             Peer-reviewed publication of trial data in a major
                            journal (NEJM, Lancet, JAMA, Blood, JCO, etc.).

    Regulatory events
    -----------------
    FDA_APPROVAL            FDA grants full or accelerated NDA/BLA approval.
    FDA_REJECTION           FDA issues a Complete Response Letter (CRL).
    FDA_DESIGNATION         FDA grants or removes a designation: Breakthrough
                            Therapy (BTD), RMAT, Orphan (ODD), Fast Track,
                            or Priority Review.
    REGULATORY_HOLD         FDA places (or lifts) a full or partial clinical hold.
    LABEL_EXPANSION         FDA approves a supplemental NDA/BLA for a new
                            indication or patient population.
    PAYER_COVERAGE          CMS NCD, commercial formulary decision, ICER
                            cost-effectiveness review, or step-therapy policy.

    Business events
    ---------------
    PARTNERSHIP             License deal, collaboration, co-development pact,
                            or acquisition announced.
    FINANCING               Equity offering (follow-on, PIPE, ATM), convertible
                            note, or debt raise.
    SEC_FILING              Material SEC filing: 10-K, 10-Q, or 8-K with
                            substantive pipeline/financial disclosure.
    MANAGEMENT_CHANGE       CEO, CMO, or CSO hire or departure with potential
                            strategic implications.

    Competitive events
    ------------------
    COMPETITOR_EVENT        Trial readout, approval, or setback for a competitor
                            in the same class or indication.
    PATENT_EVENT            Patent grant, inter partes review (IPR) filing or
                            outcome, litigation settlement, or LOE extension.

    Program lifecycle
    -----------------
    PROGRAM_DISCONTINUATION Asset dropped from pipeline: failed trial, strategic
                            decision, or safety withdrawal.
    """

    # Clinical
    TRIAL_READOUT           = "trial_readout"
    INTERIM_ANALYSIS        = "interim_analysis"
    ENROLLMENT_UPDATE       = "enrollment_update"
    ENDPOINT_CHANGE         = "endpoint_change"
    SAFETY_SIGNAL           = "safety_signal"
    CONFERENCE_PRESENTATION = "conference_presentation"
    PUBLICATION             = "publication"

    # Regulatory
    FDA_APPROVAL            = "fda_approval"
    FDA_REJECTION           = "fda_rejection"
    FDA_DESIGNATION         = "fda_designation"
    REGULATORY_HOLD         = "regulatory_hold"
    LABEL_EXPANSION         = "label_expansion"
    PAYER_COVERAGE          = "payer_coverage"

    # Business
    PARTNERSHIP             = "partnership"
    FINANCING               = "financing"
    SEC_FILING              = "sec_filing"
    MANAGEMENT_CHANGE       = "management_change"

    # Competitive
    COMPETITOR_EVENT        = "competitor_event"
    PATENT_EVENT            = "patent_event"

    # Program lifecycle
    PROGRAM_DISCONTINUATION = "program_discontinuation"


class ChangeMode(str, Enum):
    """
    How a valuation assumption change may be applied after an event is observed.

    AUTO
        The system applies a bounded, rule-based delta automatically without
        requiring human confirmation.  Reserved for unambiguous binary outcomes
        (approval → set POS to 1.0; discontinuation → set to 0.0) or tightly
        bounded continuous adjustments (enrollment delay → extend duration ≤20%).

    BOUNDED
        The system proposes a specific numeric delta derived from the signal.
        A human reviewer must confirm (or override) before the change is applied.
        The proposal magnitude is capped at ``bound_pct`` to prevent wild swings.

    MANUAL
        The system flags the event as potentially material but does not propose
        a numeric delta.  A human analyst must determine any assumption change
        and enter it directly.  Used for non-scalar parameters (competition_model,
        lifecycle_events) or situations where direction and magnitude are both
        ambiguous without domain judgment.

    Examples
    --------
    >>> ChangeMode.AUTO.value
    'AUTO'
    >>> ChangeMode("BOUNDED") is ChangeMode.BOUNDED
    True
    """

    AUTO    = "AUTO"
    BOUNDED = "BOUNDED"
    MANUAL  = "MANUAL"
