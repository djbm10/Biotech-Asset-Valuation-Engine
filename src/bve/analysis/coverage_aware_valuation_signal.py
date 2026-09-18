"""Coverage-aware Valuation Dislocation Signal V1.

This module classifies a point-in-time company model before any market-vs-model
interpretation is allowed.  It is intentionally additive: the existing valuation
bridge and implied-PoS solver remain operational, while research reporting can use
this layer to suppress invalid comparisons from incomplete company SOTPs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Optional, Union


FULL_MODEL_THRESHOLD = 0.70


class SignalOutputClass(str, Enum):
    FULLY_MODELED_VALUATION = "fully_modeled_valuation"
    PARTIAL_MODEL = "partial_model"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class CoverageStatus(str, Enum):
    MODELED_COMPANY_SPECIFIC = "modeled_company_specific"
    MODELED_STANDARDIZED_PRIOR = "modeled_standardized_prior"
    EVIDENCED_IMMATERIAL_OR_ZERO = "evidenced_immaterial_or_zero"
    OMITTED_POTENTIALLY_MATERIAL = "omitted_potentially_material"
    NOT_PUBLICLY_KNOWABLE = "not_publicly_knowable"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ComponentType(str, Enum):
    LEAD_ASSET = "lead_asset"
    OTHER_CLINICAL_ASSETS = "other_clinical_assets"
    ADDITIONAL_INDICATIONS = "additional_indications"
    APPROVED_COMMERCIAL_PRODUCTS = "approved_commercial_products"
    PARTNERSHIPS_ROYALTIES = "partnerships_royalties"
    PLATFORM_TECHNOLOGY = "platform_technology"
    CASH_MARKETABLE_SECURITIES = "cash_marketable_securities"
    DEBT_SENIOR_CLAIMS = "debt_senior_claims"
    CORPORATE_OVERHEAD = "corporate_overhead"
    EXPECTED_BURN = "expected_burn"
    EXPECTED_DILUTION = "expected_dilution"
    OTHER_LIABILITIES = "other_liabilities"


# Initial V1 allocation. These weights sum to 1.00 and are fixed before any
# cohort-level return work. Individual component records carry their assigned
# weight explicitly so multi-asset companies can split a type's allocation.
DEFAULT_COMPONENT_WEIGHTS: dict[ComponentType, float] = {
    ComponentType.LEAD_ASSET: 0.20,
    ComponentType.OTHER_CLINICAL_ASSETS: 0.12,
    ComponentType.ADDITIONAL_INDICATIONS: 0.08,
    ComponentType.APPROVED_COMMERCIAL_PRODUCTS: 0.12,
    ComponentType.PARTNERSHIPS_ROYALTIES: 0.08,
    ComponentType.PLATFORM_TECHNOLOGY: 0.05,
    ComponentType.CASH_MARKETABLE_SECURITIES: 0.08,
    ComponentType.DEBT_SENIOR_CLAIMS: 0.06,
    ComponentType.CORPORATE_OVERHEAD: 0.06,
    ComponentType.EXPECTED_BURN: 0.06,
    ComponentType.EXPECTED_DILUTION: 0.07,
    ComponentType.OTHER_LIABILITIES: 0.02,
}

COVERAGE_CREDIT: dict[CoverageStatus, float] = {
    CoverageStatus.MODELED_COMPANY_SPECIFIC: 1.0,
    CoverageStatus.MODELED_STANDARDIZED_PRIOR: 0.5,
    CoverageStatus.EVIDENCED_IMMATERIAL_OR_ZERO: 1.0,
    CoverageStatus.OMITTED_POTENTIALLY_MATERIAL: 0.0,
    CoverageStatus.NOT_PUBLICLY_KNOWABLE: 0.0,
    CoverageStatus.INSUFFICIENT_EVIDENCE: 0.0,
}


class EvidenceType(str, Enum):
    COMPANY_FILING = "company_filing"
    COMPANY_DISCLOSURE = "company_disclosure"
    REGULATORY_OR_TRIAL_SOURCE = "regulatory_or_trial_source"
    MARKET_DATA = "market_data"
    STANDARDIZED_PRIOR = "standardized_prior"
    ANALYST_DERIVATION = "analyst_derivation"
    NONE = "none"


class PriceVerificationStatus(str, Enum):
    VERIFIED = "verified"
    PROVISIONAL = "provisional"
    UNVERIFIED = "unverified"
    MISSING = "missing"


class RobustnessStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_ASSESSED = "not_assessed"


@dataclass(frozen=True)
class ComponentCoverage:
    component_id: str
    component_type: ComponentType
    estimated_materiality_weight: float
    coverage_status: CoverageStatus
    evidence_type: EvidenceType
    point_in_time_source: Optional[str]
    knowability_date: Optional[date]
    modeled_value_millions: Optional[float]
    omission_reason: Optional[str] = None
    critical: bool = False
    omitted_value_constrained_nonnegative: bool = False

    def __post_init__(self) -> None:
        if not 0.0 < self.estimated_materiality_weight <= 1.0:
            raise ValueError("estimated_materiality_weight must be in (0, 1]")
        if self.coverage_status in {
            CoverageStatus.OMITTED_POTENTIALLY_MATERIAL,
            CoverageStatus.NOT_PUBLICLY_KNOWABLE,
            CoverageStatus.INSUFFICIENT_EVIDENCE,
        } and not self.omission_reason:
            raise ValueError(f"omission_reason required for {self.coverage_status.value}")


@dataclass(frozen=True)
class CompletenessResult:
    score: float
    credited_weight: float
    total_weight: float
    unmodeled_component_count: int
    unmodeled_material_components: tuple[str, ...]
    critical_omission_reasons: tuple[str, ...]


def calculate_weighted_completeness(
    components: tuple[ComponentCoverage, ...],
) -> CompletenessResult:
    """Calculate materiality-weighted coverage; populated-field counts are irrelevant."""
    if not components:
        return CompletenessResult(0.0, 0.0, 0.0, 0, (), ())

    total_weight = sum(item.estimated_materiality_weight for item in components)
    credited_weight = sum(
        item.estimated_materiality_weight * COVERAGE_CREDIT[item.coverage_status]
        for item in components
    )
    unmodeled = tuple(
        item.component_id
        for item in components
        if item.coverage_status
        in {
            CoverageStatus.OMITTED_POTENTIALLY_MATERIAL,
            CoverageStatus.NOT_PUBLICLY_KNOWABLE,
            CoverageStatus.INSUFFICIENT_EVIDENCE,
        }
    )
    critical_reasons = tuple(
        item.omission_reason or f"{item.component_id} is not adequately represented"
        for item in components
        if item.critical
        and item.coverage_status
        in {
            CoverageStatus.OMITTED_POTENTIALLY_MATERIAL,
            CoverageStatus.NOT_PUBLICLY_KNOWABLE,
            CoverageStatus.INSUFFICIENT_EVIDENCE,
        }
    )
    score = credited_weight / total_weight if total_weight else 0.0
    return CompletenessResult(
        score=round(score, 6),
        credited_weight=round(credited_weight, 6),
        total_weight=round(total_weight, 6),
        unmodeled_component_count=len(unmodeled),
        unmodeled_material_components=unmodeled,
        critical_omission_reasons=critical_reasons,
    )


@dataclass(frozen=True)
class ScenarioValues:
    conservative_operating_value_millions: float
    base_operating_value_millions: float
    upside_operating_value_millions: float
    conservative_weight: float = 0.25
    base_weight: float = 0.50
    upside_weight: float = 0.25

    def __post_init__(self) -> None:
        weights = (self.conservative_weight, self.base_weight, self.upside_weight)
        if any(weight < 0.0 for weight in weights):
            raise ValueError("scenario weights cannot be negative")
        if abs(sum(weights) - 1.0) > 1e-9:
            raise ValueError("scenario weights must sum to 1.0")


@dataclass(frozen=True)
class SolverDiagnostics:
    solver_status: str
    valuation_gap_millions: Optional[float] = None
    required_peak_sales_at_pos_1_millions: Optional[float] = None
    required_penetration_at_pos_1: Optional[float] = None
    unexplained_residual_millions: Optional[float] = None


@dataclass(frozen=True)
class SignalConfidence:
    price_verification_status: PriceVerificationStatus
    provisional_price: bool
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True)
class CoverageAwareSignalInput:
    ticker: str
    valuation_date: Optional[date]
    share_price: Optional[float]
    shares_outstanding_millions: Optional[float]
    cash_millions: Optional[float]
    debt_millions: Optional[float]
    pipeline_identity_available: bool
    components: tuple[ComponentCoverage, ...]
    price_verification_status: PriceVerificationStatus
    expected_burn_millions: Optional[float] = None
    expected_dilution_millions: Optional[float] = None
    corporate_overhead_pv_millions: Optional[float] = None
    other_liabilities_millions: Optional[float] = None
    modeled_lead_asset_value_millions: float = 0.0
    modeled_other_asset_value_millions: float = 0.0
    known_partnership_or_commercial_value_millions: float = 0.0
    scenarios: Optional[ScenarioValues] = None
    scenario_valuation_completed: bool = False
    robustness_status: RobustnessStatus = RobustnessStatus.NOT_ASSESSED
    date_contract_resolved: bool = True
    material_provenance_violations: tuple[str, ...] = ()
    valuation_function_monotonic: bool = False
    lead_asset_market_value_isolated: bool = False
    implied_pos_candidate: Optional[float] = None
    solver_diagnostics: Optional[SolverDiagnostics] = None
    lower_bound_requested: bool = False
    all_negative_claims_modeled: bool = False
    all_overhead_modeled: bool = False
    all_dilution_modeled: bool = False
    all_liabilities_modeled: bool = False


@dataclass(frozen=True)
class FullyModeledValuationSignal:
    output_class: SignalOutputClass
    ticker: str
    model_completeness_score: float
    market_capitalization_millions: float
    scenario_weighted_equity_value: float
    conservative_equity_value: float
    base_equity_value: float
    upside_equity_value: float
    equity_value_spread: float
    valuation_gap_ratio: float
    dilution_adjusted_spread: float
    robustness_status: RobustnessStatus
    implied_pos_if_eligible: Optional[float]
    solver_status: str
    solver_diagnostics: Optional[SolverDiagnostics]
    confidence: SignalConfidence


@dataclass(frozen=True)
class PartialModelSignal:
    output_class: SignalOutputClass
    ticker: str
    value_label: str
    partial_modeled_value: float
    known_net_cash_after_burn: float
    modeled_lead_asset_value: float
    modeled_other_asset_value: float
    known_partnership_or_commercial_value: float
    known_liabilities_and_overhead: float
    market_value_unexplained: float
    model_completeness_score: float
    unmodeled_component_count: int
    unmodeled_material_components: tuple[str, ...]
    critical_omission_reasons: tuple[str, ...]
    confidence: SignalConfidence


@dataclass(frozen=True)
class InsufficientEvidenceSignal:
    output_class: SignalOutputClass
    ticker: str
    signal_status: str
    missing_required_inputs: tuple[str, ...]
    research_priority: tuple[str, ...]
    coverage_failure_reasons: tuple[str, ...]
    confidence: SignalConfidence


CoverageAwareSignal = Union[
    FullyModeledValuationSignal,
    PartialModelSignal,
    InsufficientEvidenceSignal,
]


_FULL_REQUIRED_COMPONENT_TYPES = {
    ComponentType.CASH_MARKETABLE_SECURITIES,
    ComponentType.DEBT_SENIOR_CLAIMS,
    ComponentType.CORPORATE_OVERHEAD,
    ComponentType.EXPECTED_BURN,
    ComponentType.EXPECTED_DILUTION,
}

_BLOCKING_STATUSES = {
    CoverageStatus.OMITTED_POTENTIALLY_MATERIAL,
    CoverageStatus.INSUFFICIENT_EVIDENCE,
}


def classify_coverage_aware_signal(data: CoverageAwareSignalInput) -> CoverageAwareSignal:
    """Classify first, then expose only the outputs permitted for that class."""
    confidence = _build_confidence(data)
    missing = _missing_core_inputs(data)
    if missing or not data.date_contract_resolved or data.material_provenance_violations:
        reasons = list(data.material_provenance_violations)
        if not data.date_contract_resolved:
            reasons.append("valuation date contract is unresolved")
        reasons.extend(f"missing core input: {item}" for item in missing)
        priorities = tuple(dict.fromkeys((*missing, "resolve_point_in_time_provenance")))
        return InsufficientEvidenceSignal(
            output_class=SignalOutputClass.INSUFFICIENT_EVIDENCE,
            ticker=data.ticker,
            signal_status="insufficient_evidence",
            missing_required_inputs=tuple(missing),
            research_priority=priorities,
            coverage_failure_reasons=tuple(reasons),
            confidence=confidence,
        )

    completeness = calculate_weighted_completeness(data.components)
    full_blockers = _full_model_blockers(data, completeness)
    if full_blockers:
        return _build_partial_signal(data, completeness, confidence, full_blockers)
    return _build_full_signal(data, completeness, confidence)


def _missing_core_inputs(data: CoverageAwareSignalInput) -> list[str]:
    missing: list[str] = []
    candidates = {
        "valuation_date": data.valuation_date,
        "share_price": data.share_price,
        "shares_outstanding_millions": data.shares_outstanding_millions,
        "cash_millions": data.cash_millions,
        "debt_millions": data.debt_millions,
    }
    missing.extend(name for name, value in candidates.items() if value is None)
    if not data.pipeline_identity_available:
        missing.append("pipeline_identity")
    if data.share_price is not None and data.share_price <= 0:
        missing.append("positive_share_price")
    if data.shares_outstanding_millions is not None and data.shares_outstanding_millions <= 0:
        missing.append("positive_share_count")
    return missing


def _full_model_blockers(
    data: CoverageAwareSignalInput,
    completeness: CompletenessResult,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if completeness.score < FULL_MODEL_THRESHOLD:
        blockers.append(
            f"weighted completeness {completeness.score:.1%} is below "
            f"the provisional {FULL_MODEL_THRESHOLD:.0%} threshold"
        )
    blockers.extend(completeness.critical_omission_reasons)
    blockers.extend(
        item.omission_reason or f"{item.component_id} is omitted"
        for item in data.components
        if item.coverage_status in _BLOCKING_STATUSES
        and (item.omission_reason or f"{item.component_id} is omitted")
        not in blockers
    )
    represented_types = {
        item.component_type
        for item in data.components
        if item.coverage_status
        in {
            CoverageStatus.MODELED_COMPANY_SPECIFIC,
            CoverageStatus.MODELED_STANDARDIZED_PRIOR,
            CoverageStatus.EVIDENCED_IMMATERIAL_OR_ZERO,
        }
    }
    for component_type in sorted(_FULL_REQUIRED_COMPONENT_TYPES - represented_types, key=str):
        blockers.append(f"required component is not represented: {component_type.value}")
    numeric_requirements = {
        "expected burn": data.expected_burn_millions,
        "expected dilution": data.expected_dilution_millions,
        "corporate overhead": data.corporate_overhead_pv_millions,
        "other liabilities": data.other_liabilities_millions,
    }
    blockers.extend(
        f"{name} is not quantified" for name, value in numeric_requirements.items() if value is None
    )
    if not data.scenario_valuation_completed or data.scenarios is None:
        blockers.append("scenario valuation did not complete")
    return tuple(dict.fromkeys(blockers))


def _known_balance_adjustments(data: CoverageAwareSignalInput) -> tuple[float, float]:
    cash = float(data.cash_millions or 0.0)
    debt = float(data.debt_millions or 0.0)
    burn = float(data.expected_burn_millions or 0.0)
    dilution = float(data.expected_dilution_millions or 0.0)
    overhead = float(data.corporate_overhead_pv_millions or 0.0)
    other_liabilities = float(data.other_liabilities_millions or 0.0)
    known_net_cash_after_burn = cash - debt - burn
    liabilities_and_overhead = dilution + overhead + other_liabilities
    return known_net_cash_after_burn, liabilities_and_overhead


def _build_partial_signal(
    data: CoverageAwareSignalInput,
    completeness: CompletenessResult,
    confidence: SignalConfidence,
    blockers: tuple[str, ...],
) -> PartialModelSignal:
    net_cash_after_burn, liabilities_and_overhead = _known_balance_adjustments(data)
    partial_value = (
        net_cash_after_burn
        + data.modeled_lead_asset_value_millions
        + data.modeled_other_asset_value_millions
        + data.known_partnership_or_commercial_value_millions
        - liabilities_and_overhead
    )
    market_cap = float(data.share_price or 0.0) * float(data.shares_outstanding_millions or 0.0)
    lower_bound_eligible = (
        data.lower_bound_requested
        and data.all_negative_claims_modeled
        and data.all_overhead_modeled
        and data.all_dilution_modeled
        and data.all_liabilities_modeled
        and all(
            item.omitted_value_constrained_nonnegative
            for item in data.components
            if item.coverage_status
            in {
                CoverageStatus.OMITTED_POTENTIALLY_MATERIAL,
                CoverageStatus.NOT_PUBLICLY_KNOWABLE,
                CoverageStatus.INSUFFICIENT_EVIDENCE,
            }
        )
    )
    critical_reasons = tuple(dict.fromkeys((*completeness.critical_omission_reasons, *blockers)))
    return PartialModelSignal(
        output_class=SignalOutputClass.PARTIAL_MODEL,
        ticker=data.ticker,
        value_label="modeled_value_lower_bound" if lower_bound_eligible else "partial_modeled_value",
        partial_modeled_value=round(partial_value, 6),
        known_net_cash_after_burn=round(net_cash_after_burn, 6),
        modeled_lead_asset_value=round(data.modeled_lead_asset_value_millions, 6),
        modeled_other_asset_value=round(data.modeled_other_asset_value_millions, 6),
        known_partnership_or_commercial_value=round(
            data.known_partnership_or_commercial_value_millions, 6
        ),
        known_liabilities_and_overhead=round(liabilities_and_overhead, 6),
        market_value_unexplained=round(market_cap - partial_value, 6),
        model_completeness_score=completeness.score,
        unmodeled_component_count=completeness.unmodeled_component_count,
        unmodeled_material_components=completeness.unmodeled_material_components,
        critical_omission_reasons=critical_reasons,
        confidence=confidence,
    )


def _build_full_signal(
    data: CoverageAwareSignalInput,
    completeness: CompletenessResult,
    confidence: SignalConfidence,
) -> FullyModeledValuationSignal:
    assert data.scenarios is not None
    net_cash_after_burn, liabilities_and_overhead = _known_balance_adjustments(data)
    adjustment = net_cash_after_burn - liabilities_and_overhead
    scenarios = data.scenarios
    conservative = scenarios.conservative_operating_value_millions + adjustment
    base = scenarios.base_operating_value_millions + adjustment
    upside = scenarios.upside_operating_value_millions + adjustment
    weighted = (
        conservative * scenarios.conservative_weight
        + base * scenarios.base_weight
        + upside * scenarios.upside_weight
    )
    market_cap = float(data.share_price) * float(data.shares_outstanding_millions)
    spread = weighted - market_cap
    implied_pos = _eligible_implied_pos(data)
    solver_status = data.solver_diagnostics.solver_status if data.solver_diagnostics else "not_run"
    return FullyModeledValuationSignal(
        output_class=SignalOutputClass.FULLY_MODELED_VALUATION,
        ticker=data.ticker,
        model_completeness_score=completeness.score,
        market_capitalization_millions=round(market_cap, 6),
        scenario_weighted_equity_value=round(weighted, 6),
        conservative_equity_value=round(conservative, 6),
        base_equity_value=round(base, 6),
        upside_equity_value=round(upside, 6),
        equity_value_spread=round(spread, 6),
        valuation_gap_ratio=round(spread / market_cap, 6),
        dilution_adjusted_spread=round(spread, 6),
        robustness_status=data.robustness_status,
        implied_pos_if_eligible=implied_pos,
        solver_status=solver_status,
        solver_diagnostics=data.solver_diagnostics,
        confidence=confidence,
    )


def _eligible_implied_pos(data: CoverageAwareSignalInput) -> Optional[float]:
    candidate = data.implied_pos_candidate
    if (
        data.valuation_function_monotonic
        and data.lead_asset_market_value_isolated
        and candidate is not None
        and 0.0 <= candidate <= 1.0
        and data.solver_diagnostics is not None
        and data.solver_diagnostics.solver_status.lower() == "solvable"
    ):
        return candidate
    return None


def _build_confidence(data: CoverageAwareSignalInput) -> SignalConfidence:
    limitations: list[str] = []
    if data.price_verification_status == PriceVerificationStatus.PROVISIONAL:
        limitations.append("point-in-time price is provisional and lacks full verification")
    elif data.price_verification_status == PriceVerificationStatus.UNVERIFIED:
        limitations.append("point-in-time price is unverified")
    limitations.extend(data.material_provenance_violations)
    return SignalConfidence(
        price_verification_status=data.price_verification_status,
        provisional_price=data.price_verification_status == PriceVerificationStatus.PROVISIONAL,
        limitations=tuple(limitations),
    )
