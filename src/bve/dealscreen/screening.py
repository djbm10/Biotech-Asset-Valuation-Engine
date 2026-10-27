"""Screen an imported landscape with the existing S&E gate engine.

DealScreen does not have its own eligibility logic: :class:`GateEngine` decides PASS /
FAIL / UNKNOWN per requirement and ELIGIBLE / EXCLUDED / UNRESOLVED per asset. This module
only supplies the facts, orders candidates by the buyer's declared preferences, and
attaches the separate commercial assessment.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from bve.dealscreen.buyer import BuyerSpec
from bve.dealscreen.commercial import CommercialAssessment, assess
from bve.dealscreen.facts import AssetFacts, FactBuilder, ReviewInputs, finding_claim
from bve.dealscreen.models import IdentityFlag, LandscapeAsset
from bve.se.gates.engine import GateEngine
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

    def gate_status(self, requirement_id: str) -> str | None:
        for decision in self.decisions:
            if decision["requirement_id"] == requirement_id:
                return decision["analyst_override"] or decision["status"]
        return None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["commercial"]["display"] = self.commercial.display
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

    screens: list[AssetScreen] = []
    for asset in sorted(assets, key=lambda a: a.asset_id):
        facts = builder.build(asset, review)
        evaluation = engine.evaluate(spec.problem, subject_id=asset.asset_id, facts=facts.facts)
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
                    confirmed_findings=tuple(
                        finding_claim(f) for f in review.confirmed_findings
                    ),
                ),
                identity_flag_ids=sorted(flags_by_asset.get(asset.asset_id, [])),
            )
        )

    _rank(screens)
    return ScreeningResult(
        problem_id=spec.problem.problem_id, screens=screens, funnel=funnel(screens, assets)
    )


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
