"""Screen an imported landscape with the existing S&E gate engine.

DealScreen does not have its own eligibility logic: :class:`GateEngine` decides PASS /
FAIL / UNKNOWN per requirement and ELIGIBLE / EXCLUDED / UNRESOLVED per asset. This module
only supplies the facts, orders candidates by the buyer's declared preferences, and
attaches the separate commercial assessment.
"""

from __future__ import annotations

import dataclasses
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from bve.dealscreen.buyer import BuyerSpec
from bve.dealscreen.commercial import CommercialAssessment, assess
from bve.dealscreen.facts import (
    AssetFacts,
    FactBuilder,
    ReviewInputs,
    assertion_claim,
    finding_claim,
)
from bve.dealscreen.models import IdentityFlag, LandscapeAsset
from bve.dealscreen.transaction import assess_transaction, transaction_ranks
from bve.se.gates.engine import GateEngine
from bve.se.ontology.therapeutic_areas import UNSPECIFIED, canonical_therapeutic_area
from bve.se.schemas.contracts import GateStatus, OverallDisposition

SCREENING_VERSION = "dealscreen_screening_v1"

#: The declared order, most important first. Written into every output.
RANKING_RULE = (
    "Lexicographic over preferences only, within a disposition: (1) reaches the preferred "
    "minimum phase, (2) active development, (3) higher development stage, (4) more "
    "registered trial IDs, (5) modality within the buyer's declared capabilities, then "
    "program name. Ranking never changes a gate decision or a disposition."
)


@dataclass
class AssetScreen:
    asset_id: str
    program_name: str
    company: str | None
    disposition: str
    decisions: list[dict[str, Any]]
    review_reasons: list[str]
    facts: list[dict[str, Any]]
    unreadable_claims: list[dict[str, str]]
    stage_order: int | None
    activity: str
    modality: str | None
    target_symbols: list[str]
    n_trials: int
    preference_key: list[Any]
    rank: int | None
    machine_recommendation: str
    commercial: CommercialAssessment
    identity_flag_ids: list[str] = field(default_factory=list)
    #: Buyer-declared transaction view (cycle C1 X5): tier, reasons, notes. Never read by a gate.
    transaction: dict[str, Any] = field(default_factory=dict)
    #: Rank among ELIGIBLE programs by transaction tier, then scientific rank (None if not declared).
    transaction_rank: int | None = None
    #: Isoform target names read as their gene (cycle C1 X1), shown to the analyst.
    target_readings: list[dict[str, str]] = field(default_factory=list)
    #: Display-only market status (cycle A5 K1); never read by a gate.
    market_status: str | None = None
    #: Qualified indication names read as their NCIt parent (cycle A1 F2), shown to the analyst.
    indication_readings: list[dict[str, str]] = field(default_factory=list)
    #: Active analyst assertions on this asset, with citations.
    analyst_assertions: list[dict[str, Any]] = field(default_factory=list)
    #: Assertions that replaced a readable, different source value.
    overrides: list[dict[str, Any]] = field(default_factory=list)
    #: Every gate whose status differs from the same screen without analyst assertions.
    #: Empty with active assertions means they changed no decision.
    assertion_effects: list[dict[str, Any]] = field(default_factory=list)

    def gate_status(self, requirement_id: str) -> str | None:
        for decision in self.decisions:
            if decision["requirement_id"] == requirement_id:
                return decision["analyst_override"] or decision["status"]
        return None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["commercial"]["display"] = self.commercial.display
        data["commercial"]["holder_display"] = self.commercial.holder_display
        return data


@dataclass
class ScreeningResult:
    problem_id: str
    screens: list[AssetScreen]
    funnel: dict[str, Any]
    ranking_rule: str = RANKING_RULE
    version: str = SCREENING_VERSION

    def by_id(self) -> dict[str, AssetScreen]:
        return {s.asset_id: s for s in self.screens}

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "problem_id": self.problem_id,
            "ranking_rule": self.ranking_rule,
            "funnel": self.funnel,
            "screens": [s.to_dict() for s in self.screens],
        }


def _preference_key(spec: BuyerSpec, facts: AssetFacts, n_trials: int) -> list[Any]:
    prefs = spec.preferences
    preferred = prefs.preferred_stage_order
    stage = facts.stage_order if facts.stage_order is not None else -1
    return [
        int(preferred is not None and stage >= preferred),
        int(prefs.prefer_active_development and facts.activity == "ACTIVE"),
        stage,
        n_trials if prefs.prefer_more_registered_trials else 0,
        int(bool(facts.modality) and facts.modality in prefs.buyer_capability_modalities),
    ]


def explain_preference_key(spec: BuyerSpec, key: list[Any], activity: str) -> str:
    """The ranking key in words (cycle A3 H2). Ranks compare these in order, left to right."""
    prefs = spec.preferences
    meets, active, stage, trials, capability = (list(key) + [0, 0, -1, 0, 0])[:5]
    parts = []
    if prefs.preferred_stage_order is not None:
        parts.append(f"meets preferred phase: {'yes' if meets else 'no'}")
    if prefs.prefer_active_development:
        parts.append(f"counts as active development: {'yes' if active else 'no'} (activity {activity})")
    parts.append(f"stage order {stage if stage >= 0 else 'unknown'}")
    if prefs.prefer_more_registered_trials:
        parts.append(f"{trials} registered trial(s)")
    if prefs.buyer_capability_modalities:
        parts.append(f"buyer-capability modality: {'yes' if capability else 'no'}")
    return "; ".join(parts)


def screen_landscape(
    assets: list[LandscapeAsset],
    spec: BuyerSpec,
    builder: FactBuilder,
    *,
    review: ReviewInputs | None = None,
    identity_flags: list[IdentityFlag] | None = None,
) -> ScreeningResult:
    review = review or ReviewInputs()
    engine = GateEngine()
    flags_by_asset: dict[str, list[str]] = {}
    for flag in identity_flags or []:
        for asset_id in flag.asset_ids:
            flags_by_asset.setdefault(asset_id, []).append(flag.flag_id)

    # Canonical names on both sides; the "no area requirement" sentinel means no requirement (review A1-1).
    requested_areas = frozenset(
        canonical_therapeutic_area(str(getattr(a, "value", a)))
        for a in spec.problem.strategic_gap.therapeutic_areas) - {UNSPECIFIED}
    expression = spec.problem.strategic_gap.target_expression
    # A partial target set is a positive witness only; never for an exact combination (cycle C1 X6).
    witness = (None if expression.operator.value == "EXACT_COMBINATION" else
               frozenset(t.canonical_id for t in expression.targets))
    witness_all = expression.operator.value == "ALL"  # ALL needs every requested target (review C1-1)
    screens: list[AssetScreen] = []
    for asset in sorted(assets, key=lambda a: a.asset_id):
        facts = builder.build(asset, review, requested_areas, witness, witness_all)
        evaluation = engine.evaluate(spec.problem, subject_id=asset.asset_id, facts=facts.facts)
        effects: list[dict[str, Any]] = []
        if any(a.asset_id == asset.asset_id for a in review.assertions):
            without = dataclasses.replace(
                review, assertions=tuple(a for a in review.assertions if a.asset_id != asset.asset_id))
            base = engine.evaluate(spec.problem, subject_id=asset.asset_id,
                                   facts=builder.build(asset, without, requested_areas, witness, witness_all).facts)
            before = {d.requirement_id: (d.analyst_override or d.status).value for d in base.decisions}
            for d in evaluation.decisions:
                now = (d.analyst_override or d.status).value
                if before.get(d.requirement_id) != now:
                    effects.append({"requirement_id": d.requirement_id, "without_assertions": before.get(d.requirement_id),
                                    "with_assertions": now,
                                    "overturns_source_fail": before.get(d.requirement_id) == "FAIL"})
            if base.disposition != evaluation.disposition:
                effects.append({"requirement_id": "DISPOSITION", "without_assertions": base.disposition.value,
                                "with_assertions": evaluation.disposition.value,
                                "overturns_source_fail": base.disposition.value == "EXCLUDED"})
        trial_ids = {
            t for c in asset.claims_for("trial_ids")
            for t in c.value_as_written.replace(",", ";").split(";") if t.strip()
        }
        reasons = [
            f"{d.requirement_id}: {d.rationale}"
            for d in evaluation.decisions
            if (d.analyst_override or d.status) != GateStatus.PASS
        ]
        if asset.asset_id in flags_by_asset:
            reasons.append("identity: shares a name/code with another source record (review)")
        screens.append(
            AssetScreen(
                asset_id=asset.asset_id,
                program_name=asset.program_name,
                company=asset.company,
                disposition=evaluation.disposition.value,
                decisions=[d.model_dump(mode="json") for d in evaluation.decisions],
                review_reasons=reasons,
                facts=[f.model_dump(mode="json") for f in facts.facts],
                unreadable_claims=facts.unreadable,
                indication_readings=facts.indication_readings,
                market_status=facts.market_status,
                target_readings=facts.target_readings,
                stage_order=facts.stage_order,
                activity=facts.activity,
                modality=facts.modality,
                target_symbols=facts.target_symbols,
                n_trials=len(trial_ids),
                preference_key=_preference_key(spec, facts, len(trial_ids)),
                rank=None,
                machine_recommendation="NOT_RECOMMENDED",
                commercial=assess(
                    asset,
                    questions=spec.commercial.questions,
                    rejected_claim_ids=review.rejected_claim_ids,
                    confirmed_claim_ids=review.confirmed_claim_ids,
                    confirmed_findings=(
                        *(finding_claim(f) for f in review.confirmed_findings),
                        *(assertion_claim(a) for a in review.assertions),
                    ),
                ),
                identity_flag_ids=sorted(flags_by_asset.get(asset.asset_id, [])),
                analyst_assertions=[a.model_dump(mode="json") for a in review.assertions
                                    if a.asset_id == asset.asset_id],
                overrides=facts.overrides,
                assertion_effects=effects,
            )
        )

    _rank(screens)
    _transaction(screens, spec, flags_by_asset)
    return ScreeningResult(
        problem_id=spec.problem.problem_id, screens=screens, funnel=funnel(screens, assets)
    )


def _transaction(screens: list[AssetScreen], spec: BuyerSpec, flags_by_asset: dict[str, list[str]]) -> None:
    names = {s.asset_id: s.program_name for s in screens}
    for screen in screens:
        twins = sorted({names[o] for o, f in flags_by_asset.items()
                        if o != screen.asset_id and set(f) & set(flags_by_asset.get(screen.asset_id, []))})
        view = assess_transaction(
            spec.transaction, market_status=screen.market_status,
            rights_status=screen.commercial.us_rights_status, rights_holder=screen.commercial.us_rights_holder,
            company=screen.company, identity_twins=twins)
        screen.transaction = {"tier": view.tier, "reasons": view.reasons, "notes": view.notes}
    ranks = transaction_ranks([{"asset_id": s.asset_id, "disposition": s.disposition, "rank": s.rank,
                                "transaction": s.transaction} for s in screens])
    for screen in screens:
        screen.transaction_rank = ranks.get(screen.asset_id)


def _rank(screens: list[AssetScreen]) -> None:
    for disposition, recommendation in (
        (OverallDisposition.ELIGIBLE.value, "CANDIDATE_FOR_ANALYST_REVIEW"),
        (OverallDisposition.UNRESOLVED.value, "NEEDS_DILIGENCE"),
    ):
        group = [s for s in screens if s.disposition == disposition]
        group.sort(key=lambda s: ([-v for v in s.preference_key], s.program_name.casefold(), s.asset_id))
        for position, screen in enumerate(group, start=1):
            screen.rank = position
            screen.machine_recommendation = recommendation


def funnel(screens: list[AssetScreen], assets: list[LandscapeAsset]) -> dict[str, Any]:
    dispositions = Counter(s.disposition for s in screens)
    first_failure: Counter[str] = Counter()
    unknown_by_gate: Counter[str] = Counter()
    for screen in screens:
        failed = [d["requirement_id"] for d in screen.decisions if (d["analyst_override"] or d["status"]) == "FAIL"]
        if failed:
            first_failure[failed[0]] += 1
        for decision in screen.decisions:
            if (decision["analyst_override"] or decision["status"]) == "UNKNOWN":
                unknown_by_gate[decision["requirement_id"]] += 1
    rights = Counter(
        s.commercial.us_rights_status for s in screens if s.disposition == OverallDisposition.ELIGIBLE.value
    )
    total = len(assets)
    counted = sum(dispositions.values())
    if counted != total:  # pragma: no cover - invariant
        raise AssertionError(f"funnel does not reconcile: {counted} screened vs {total} assets")
    return {
        "assets_screened": total,
        "eligible": dispositions.get("ELIGIBLE", 0),
        "unresolved": dispositions.get("UNRESOLVED", 0),
        "excluded": dispositions.get("EXCLUDED", 0),
        "excluded_by_first_failed_requirement": dict(sorted(first_failure.items())),
        "unknown_decisions_by_requirement": dict(sorted(unknown_by_gate.items())),
        "eligible_by_us_rights_status": dict(sorted(rights.items())),
    }
