"""Gate rule implementations for the M&A hard exclusion / routing layer.

Each public function corresponds to one gate (Gates 0–10).  Company-level
gates take a single ``CompanyProfile``; pair-level gates (Gate 2) take both
a ``CompanyProfile`` and an ``AcquirerProfile``.

All functions return a ``GateResult`` — they never raise.

Score-cap defaults (SEVERE_CAP gates):
  G4  failed pivotal with salvage path   → 0.40
  G4  mechanism invalidated / no dose    → 0.40
  G4  weak single-study signal           → 0.60
  G5  fully licensed away (cap path)     → 0.55
  G5  weak IP / short exclusivity        → 0.55
  G5  royalty burden                     → 0.55
  G5  IP dispute / blocking rights       → 0.55
  G6  negative EV distressed             → capped; routed
  G7  illiquid / microcap                → 0.65
  G8  fraud allegation                   → 0.35
  G8  data integrity / enforcement cloud → 0.50
  G9  commercial relevance weak          → 0.60
"""
from __future__ import annotations

from .enums import ExclusionStatus, GateName, RoutingModel
from .models import AcquirerProfile, CompanyProfile, GateResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pass(gate: GateName) -> GateResult:
    return GateResult(
        gate_name=gate,
        status=ExclusionStatus.PASS,
        reason="all_rules_passed",
        recommended_action="proceed_to_scoring",
    )


def _hard_fail(gate: GateName, rule_id: str, reason: str, fields: list[str]) -> GateResult:
    return GateResult(
        gate_name=gate,
        status=ExclusionStatus.HARD_FAIL,
        triggered_rules=[rule_id],
        reason=reason,
        evidence_fields_used=fields,
        recommended_action="exclude_from_live_ranking",
    )


def _historical_only(gate: GateName, rule_id: str, reason: str, fields: list[str]) -> GateResult:
    return GateResult(
        gate_name=gate,
        status=ExclusionStatus.HISTORICAL_ONLY,
        triggered_rules=[rule_id],
        reason=reason,
        evidence_fields_used=fields,
        recommended_action="move_to_historical_training_set",
    )


def _route(
    gate: GateName,
    rule_id: str,
    reason: str,
    fields: list[str],
    model: RoutingModel,
) -> GateResult:
    return GateResult(
        gate_name=gate,
        status=ExclusionStatus.ROUTE_TO_OTHER_MODEL,
        triggered_rules=[rule_id],
        reason=reason,
        evidence_fields_used=fields,
        recommended_action=f"route_to:{model.value}",
        route_to_model=model,
    )


def _severe_cap(
    gate: GateName,
    rule_id: str,
    reason: str,
    fields: list[str],
    cap: float,
) -> GateResult:
    return GateResult(
        gate_name=gate,
        status=ExclusionStatus.SEVERE_CAP,
        triggered_rules=[rule_id],
        reason=reason,
        evidence_fields_used=fields,
        recommended_action=f"allow_scoring_cap_at_{cap:.2f}",
        score_cap=cap,
    )


def _diligence_queue(gate: GateName, rule_id: str, reason: str, fields: list[str]) -> GateResult:
    return GateResult(
        gate_name=gate,
        status=ExclusionStatus.DILIGENCE_QUEUE,
        triggered_rules=[rule_id],
        reason=reason,
        evidence_fields_used=fields,
        recommended_action="add_to_diligence_export_hold_from_ranked_output",
    )


def _refresh_required(gate: GateName, rule_id: str, reason: str, fields: list[str]) -> GateResult:
    return GateResult(
        gate_name=gate,
        status=ExclusionStatus.REFRESH_REQUIRED,
        triggered_rules=[rule_id],
        reason=reason,
        evidence_fields_used=fields,
        recommended_action="refresh_data_before_scoring",
    )


def _pair_fail(gate: GateName, rule_id: str, reason: str, fields: list[str]) -> GateResult:
    return GateResult(
        gate_name=gate,
        status=ExclusionStatus.PAIR_LEVEL_FAIL,
        triggered_rules=[rule_id],
        reason=reason,
        evidence_fields_used=fields,
        recommended_action="exclude_this_acquirer_target_pair",
        is_company_level=False,
        is_pair_level=True,
    )


def _pair_cap(
    gate: GateName,
    rule_id: str,
    reason: str,
    fields: list[str],
    cap: float,
) -> GateResult:
    return GateResult(
        gate_name=gate,
        status=ExclusionStatus.PAIR_LEVEL_CAP,
        triggered_rules=[rule_id],
        reason=reason,
        evidence_fields_used=fields,
        recommended_action=f"cap_pair_score_at_{cap:.2f}",
        score_cap=cap,
        is_company_level=False,
        is_pair_level=True,
    )


# ---------------------------------------------------------------------------
# Gate 0 — Entity Validity
# ---------------------------------------------------------------------------

# Entity types that are valid biotech/pharma M&A targets
_VALID_TARGET_ENTITY_TYPES: frozenset[str] = frozenset({
    "biotech",
    "pharma",
    "diagnostics",
    "medical_device",
    "tools_reagents",
    "platform",
})


def gate_0_entity_validity(company: CompanyProfile) -> GateResult:
    """Determine whether the entity is a valid biotech/pharma M&A target.

    Hard fail or route if the entity type is wrong for this model.

    Non-biotech / shell / holding / nonprofit → HARD_FAIL
    Royalty company                           → ROUTE_TO_OTHER_MODEL (royalty model)
    Service-only company (CRO/CDMO)          → ROUTE_TO_OTHER_MODEL (services M&A)
    Government-controlled / restricted        → HARD_FAIL (if formally restricted)
                                                DILIGENCE_QUEUE (if uncertain)
    Known acquirer profile                    → HARD_FAIL (wrong universe)
    """
    gate = GateName.GATE_0_ENTITY_VALIDITY
    et = company.entity_type

    if et in ("spac_shell",):
        return _hard_fail(gate, "G0.SPAC_SHELL", "spac_shell_or_blank_check_company", ["entity_type"])

    if et in ("holding_company", "investment_vehicle"):
        return _hard_fail(gate, "G0.HOLDING", "holding_company_or_investment_vehicle", ["entity_type"])

    if et in ("consulting_staffing",):
        return _route(gate, "G0.SERVICE_NO_ASSET", "service_only_no_proprietary_asset",
                      ["entity_type"], RoutingModel.SERVICES_MA_MODEL)

    if et in ("cro_cdmo",):
        return _route(gate, "G0.CRO_CDMO", "contract_service_no_proprietary_platform",
                      ["entity_type"], RoutingModel.SERVICES_MA_MODEL)

    if et in ("research_nonprofit", "academic_entity"):
        return _hard_fail(gate, "G0.NONPROFIT", "research_nonprofit_or_academic_entity", ["entity_type"])

    if et == "royalty_company":
        return _route(gate, "G0.ROYALTY_CO", "royalty_company_passive_ip_vehicle",
                      ["entity_type"], RoutingModel.ROYALTY_MODEL)

    if et == "government_controlled":
        if company.is_government_restricted:
            return _hard_fail(gate, "G0.GOV_RESTRICTED", "government_controlled_structurally_restricted",
                              ["entity_type", "is_government_restricted"])
        return _diligence_queue(gate, "G0.GOV_UNCERTAIN",
                                "government_controlled_restriction_status_uncertain",
                                ["entity_type", "is_government_restricted"])

    if et in ("diversified_conglomerate", "other"):
        return _hard_fail(gate, "G0.NON_BIOTECH", f"non_biotech_pharma_entity:{et}", ["entity_type"])

    # Known acquirer profiles should not be in the target universe
    if company.is_known_acquirer:
        return _hard_fail(gate, "G0.KNOWN_ACQUIRER", "company_is_a_known_acquirer_profile",
                          ["is_known_acquirer"])

    if et not in _VALID_TARGET_ENTITY_TYPES:
        return _hard_fail(gate, "G0.UNKNOWN_TYPE", f"unrecognised_entity_type:{et}", ["entity_type"])

    return _pass(gate)


# ---------------------------------------------------------------------------
# Gate 1 — Standalone / Corporate Status
# ---------------------------------------------------------------------------

def gate_1_corporate_status(company: CompanyProfile) -> GateResult:
    """Check whether the company is still an independent, scoreable entity.

    Already acquired / merged / delisted after takeout → HISTORICAL_ONLY
    Pending definitive acquisition agreement           → HARD_FAIL (announced deal)
    Post-spin mismatch / ticker mismatch               → REFRESH_REQUIRED or DILIGENCE_QUEUE
    Duplicate entity                                   → DILIGENCE_QUEUE
    Bankrupt / liquidating                             → HARD_FAIL (overlaps Gate 6)
    """
    gate = GateName.GATE_1_CORPORATE_STATUS
    status = company.corporate_status

    if status in ("acquired", "merged", "delisted_takeout"):
        return _historical_only(gate, "G1.ALREADY_ACQUIRED",
                                f"already_acquired_merged_or_delisted_takeout:{status}",
                                ["corporate_status"])

    if status == "pending_acquisition":
        return _hard_fail(gate, "G1.PENDING_DEAL",
                          "pending_definitive_acquisition_agreement_announced_deal",
                          ["corporate_status"])

    if status in ("bankrupt", "liquidating"):
        return _hard_fail(gate, "G1.BANKRUPT",
                          f"company_in_{status}_proceedings",
                          ["corporate_status"])

    if status == "post_spin":
        return _diligence_queue(gate, "G1.POST_SPIN",
                                "post_spin_entity_data_may_be_stale_or_mismatched",
                                ["corporate_status"])

    if status == "ticker_mismatch":
        return _refresh_required(gate, "G1.TICKER_MISMATCH",
                                 "ticker_no_longer_matches_original_entity",
                                 ["corporate_status"])

    if company.is_duplicate or status == "duplicate_entity":
        return _diligence_queue(gate, "G1.DUPLICATE",
                                "duplicate_entity_deduplicate_before_scoring",
                                ["corporate_status", "is_duplicate"])

    return _pass(gate)


# ---------------------------------------------------------------------------
# Gate 2 — Buyer-Target Validity (pair-level)
# ---------------------------------------------------------------------------

_ANTITRUST_HARD_FAIL_THRESHOLD = 0.85  # prob > this → near-certain block


def gate_2_buyer_target_validity(
    company: CompanyProfile,
    acquirer: AcquirerProfile,
) -> GateResult:
    """Validate a specific acquirer-target pairing.

    Self-acquisition                          → PAIR_LEVEL_FAIL
    Acquirer already has majority control     → PAIR_LEVEL_FAIL
    Affordability impossible                  → PAIR_LEVEL_FAIL
    Direct strategic conflict                 → PAIR_LEVEL_FAIL
    Antitrust impossibility                   → PAIR_LEVEL_FAIL
    Merger-of-equals                          → ROUTE_TO_OTHER_MODEL
    """
    gate = GateName.GATE_2_BUYER_TARGET_VALIDITY

    # Self-acquisition
    if (
        company.ticker
        and acquirer.ticker
        and company.ticker.upper() == acquirer.ticker.upper()
    ):
        return _pair_fail(gate, "G2.SELF_ACQUISITION",
                          "self_acquisition_buyer_and_target_are_same_entity",
                          ["ticker"])

    if (
        company.company_id == acquirer.acquirer_id
    ):
        return _pair_fail(gate, "G2.SELF_ACQUISITION_ID",
                          "self_acquisition_buyer_and_target_share_company_id",
                          ["company_id"])

    # Acquirer already controls the target
    if acquirer.has_majority_control:
        return _pair_fail(gate, "G2.EXISTING_CONTROL",
                          "acquirer_already_has_majority_control_of_target",
                          ["has_majority_control"])

    # Affordability: total deal capacity vs. expected acquisition cost
    deal_capacity = (
        acquirer.cash_available_millions
        + acquirer.debt_capacity_millions
        + acquirer.realistic_stock_component_millions
    )
    if company.market_cap_millions is not None and company.market_cap_millions > 0:
        expected_cost = company.market_cap_millions * (1.0 + acquirer.expected_premium)
        if expected_cost > 0 and deal_capacity / expected_cost < 0.25:
            return _pair_fail(gate, "G2.AFFORDABILITY",
                              f"deal_cost_{expected_cost:.0f}M_far_exceeds_capacity_{deal_capacity:.0f}M",
                              ["market_cap_millions", "cash_available_millions"])

    # Direct strategic conflict
    if acquirer.has_direct_strategic_conflict:
        return _pair_fail(gate, "G2.STRATEGIC_CONFLICT",
                          "direct_product_ta_conflict_makes_acquisition_counterproductive",
                          ["has_direct_strategic_conflict"])

    # Antitrust impossibility
    if acquirer.antitrust_block_probability >= _ANTITRUST_HARD_FAIL_THRESHOLD:
        return _pair_fail(gate, "G2.ANTITRUST",
                          f"antitrust_block_probability_{acquirer.antitrust_block_probability:.0%}_exceeds_threshold",
                          ["antitrust_block_probability"])

    # Merger of equals → route to different model
    if acquirer.is_merger_of_equals:
        return GateResult(
            gate_name=gate,
            status=ExclusionStatus.ROUTE_TO_OTHER_MODEL,
            triggered_rules=["G2.MERGER_OF_EQUALS"],
            reason="merger_of_equals_requires_different_model",
            evidence_fields_used=["is_merger_of_equals"],
            recommended_action=f"route_to:{RoutingModel.MERGER_OF_EQUALS_MODEL.value}",
            route_to_model=RoutingModel.MERGER_OF_EQUALS_MODEL,
            is_company_level=False,
            is_pair_level=True,
        )

    return _pass(gate)


# ---------------------------------------------------------------------------
# Gate 3 — Asset Visibility
# ---------------------------------------------------------------------------

def gate_3_asset_visibility(company: CompanyProfile) -> GateResult:
    """Verify there is an identifiable value driver.

    No asset / platform / pipeline / product → HARD_FAIL
    Vague pipeline / unclear TA or modality  → DILIGENCE_QUEUE
    """
    gate = GateName.GATE_3_ASSET_VISIBILITY

    # No identifiable value driver at all
    if (
        not company.has_lead_asset
        and not company.has_platform
        and not company.has_active_pipeline
        and not company.has_commercial_product
    ):
        return _hard_fail(gate, "G3.NO_VALUE_DRIVER",
                          "no_identifiable_asset_platform_pipeline_or_product",
                          ["has_lead_asset", "has_platform", "has_active_pipeline",
                           "has_commercial_product"])

    if company.pipeline_description_quality == "missing":
        return _hard_fail(gate, "G3.MISSING_PIPELINE",
                          "pipeline_is_completely_undescribed_cannot_underwrite",
                          ["pipeline_description_quality"])

    # Vague pipeline / unclear TA or modality → DILIGENCE_QUEUE
    diligence_triggers: list[str] = []
    if company.pipeline_description_quality == "vague":
        diligence_triggers.append("pipeline_description_quality:vague")
    if not company.therapeutic_area_known:
        diligence_triggers.append("therapeutic_area_unknown")
    if not company.modality_known:
        diligence_triggers.append("modality_unknown")

    if diligence_triggers:
        return _diligence_queue(gate, "G3.VAGUE_PIPELINE",
                                "vague_or_unclear_pipeline:" + ";".join(diligence_triggers),
                                ["pipeline_description_quality", "therapeutic_area_known",
                                 "modality_known"])

    return _pass(gate)


# ---------------------------------------------------------------------------
# Gate 4 — Asset Viability
# ---------------------------------------------------------------------------

def gate_4_asset_viability(company: CompanyProfile) -> GateResult:
    """Assess whether the lead asset is viable.

    Discontinued / fatal safety / no path         → HARD_FAIL
    Failed pivotal with credible salvage path      → SEVERE_CAP 0.40
    Mechanism invalidated / no dose window         → SEVERE_CAP 0.40
    Weak single-study signal                       → SEVERE_CAP 0.60
    Abandoned                                      → HARD_FAIL or REFRESH_REQUIRED
    Clinical hold unresolved                       → SEVERE_CAP 0.40
    """
    gate = GateName.GATE_4_ASSET_VIABILITY
    s = company.lead_asset_status

    if s in ("discontinued", "failed_pivotal_no_path", "regulatory_rejected_no_path"):
        return _hard_fail(gate, f"G4.{s.upper()}",
                          f"lead_asset_{s}_no_viable_path_forward",
                          ["lead_asset_status"])

    if s == "safety_blocked":
        return _hard_fail(gate, "G4.SAFETY_BLOCKED",
                          "fatal_safety_signal_or_unresolvable_clinical_hold",
                          ["lead_asset_status"])

    if s == "failed_pivotal":
        if company.has_salvage_path:
            return _severe_cap(gate, "G4.FAILED_PIVOTAL_SALVAGE",
                               "pivotal_trial_failed_salvage_path_exists",
                               ["lead_asset_status", "has_salvage_path"], 0.40)
        return _hard_fail(gate, "G4.FAILED_PIVOTAL_NO_PATH",
                          "pivotal_trial_failed_no_credible_salvage_path",
                          ["lead_asset_status", "has_salvage_path"])

    if s in ("mechanism_invalidated", "no_dose_window"):
        return _severe_cap(gate, f"G4.{s.upper()}",
                           f"lead_asset_{s}_severely_limits_value",
                           ["lead_asset_status"], 0.40)

    if s == "weak_signal_single_study":
        return _severe_cap(gate, "G4.WEAK_SIGNAL",
                           "lead_asset_single_non_replicated_weak_dataset",
                           ["lead_asset_status"], 0.60)

    if s == "abandoned":
        if company.has_salvage_path:
            return _refresh_required(gate, "G4.ABANDONED_SALVAGE",
                                     "development_abandoned_possible_new_program",
                                     ["lead_asset_status", "has_salvage_path"])
        return _hard_fail(gate, "G4.ABANDONED",
                          "development_fully_abandoned_no_path",
                          ["lead_asset_status"])

    # Clinical hold unresolved (even if lead is otherwise "active")
    if company.clinical_hold_unresolved:
        return _severe_cap(gate, "G4.CLINICAL_HOLD",
                           "unresolved_clinical_hold_blocks_development",
                           ["clinical_hold_unresolved"], 0.40)

    return _pass(gate)


# ---------------------------------------------------------------------------
# Gate 5 — Rights / IP / Ownership
# ---------------------------------------------------------------------------

_ROYALTY_STACK_HIGH_THRESHOLD = 0.20  # cumulative rate above which royalty burden is severe


def gate_5_rights_ip_ownership(company: CompanyProfile) -> GateResult:
    """Assess IP ownership and rights encumbrances.

    No ownable rights                        → HARD_FAIL
    Fully licensed away                      → ROUTE_TO_OTHER_MODEL (or SEVERE_CAP per config)
    Key territory unavailable                → SEVERE_CAP 0.55
    Weak IP / short exclusivity              → SEVERE_CAP 0.55
    IP dispute / blocking consent rights     → DILIGENCE_QUEUE or SEVERE_CAP
    Royalty burden                           → SEVERE_CAP 0.55
    """
    gate = GateName.GATE_5_RIGHTS_IP_OWNERSHIP

    if company.ip_ownership_status == "fully_licensed_away":
        return _route(gate, "G5.NO_OWNABLE_RIGHTS",
                      "lead_asset_rights_fully_licensed_away_acquirer_cannot_own",
                      ["ip_ownership_status"], RoutingModel.LICENSING_MODEL)

    if company.ip_ownership_status == "key_territory_unavailable":
        return _severe_cap(gate, "G5.TERRITORY_UNAVAILABLE",
                           "key_commercial_territory_rights_unavailable_to_acquirer",
                           ["ip_ownership_status"], 0.55)

    if company.ip_ownership_status == "co_owned_disputed":
        return _diligence_queue(gate, "G5.IP_CO_OWNED_DISPUTED",
                                "ip_co_owned_or_ownership_disputed_cannot_score_reliably",
                                ["ip_ownership_status"])

    if company.has_ip_dispute:
        return _severe_cap(gate, "G5.IP_DISPUTE",
                           "active_ip_ownership_dispute_material_deal_risk",
                           ["has_ip_dispute"], 0.55)

    if company.has_blocking_third_party_rights:
        return _diligence_queue(gate, "G5.BLOCKING_RIGHTS",
                                "blocking_third_party_consent_rights_require_diligence",
                                ["has_blocking_third_party_rights"])

    if company.ip_durability in ("weak", "short_exclusivity"):
        return _severe_cap(gate, "G5.WEAK_IP",
                           f"ip_durability_{company.ip_durability}_limits_deal_value",
                           ["ip_durability"], 0.55)

    if (
        company.royalty_stack_rate is not None
        and company.royalty_stack_rate > _ROYALTY_STACK_HIGH_THRESHOLD
    ):
        return _severe_cap(gate, "G5.ROYALTY_BURDEN",
                           f"royalty_stack_{company.royalty_stack_rate:.0%}_exceeds_{_ROYALTY_STACK_HIGH_THRESHOLD:.0%}_threshold",
                           ["royalty_stack_rate"], 0.55)

    return _pass(gate)


# ---------------------------------------------------------------------------
# Gate 6 — Financial / Going-Concern
# ---------------------------------------------------------------------------

def gate_6_financial_going_concern(company: CompanyProfile) -> GateResult:
    """Assess financial health and data completeness.

    Bankrupt / liquidating                  → HARD_FAIL
    Going-concern warning                   → ROUTE_TO_OTHER_MODEL (distress)
    Negative EV (distressed asset shell)    → ROUTE_TO_OTHER_MODEL + note SEVERE_CAP
    No / unreliable financials              → DILIGENCE_QUEUE or HARD_FAIL
    Missing all financial data              → DILIGENCE_QUEUE
    """
    gate = GateName.GATE_6_FINANCIAL_GOING_CONCERN
    fs = company.financial_status

    if fs in ("bankrupt", "liquidating"):
        return _hard_fail(gate, f"G6.{fs.upper()}",
                          f"company_is_{fs}_not_a_standard_ma_target",
                          ["financial_status"])

    if fs == "going_concern_warning":
        return _route(gate, "G6.GOING_CONCERN",
                      "severe_going_concern_warning_route_to_distressed_model",
                      ["financial_status"], RoutingModel.DISTRESSED_OPTIONALITY_MODEL)

    if fs == "negative_ev_distressed":
        return _route(gate, "G6.NEGATIVE_EV_DISTRESS",
                      "negative_enterprise_value_distressed_asset_shell",
                      ["financial_status", "enterprise_value_millions"],
                      RoutingModel.DISTRESSED_OPTIONALITY_MODEL)

    if fs == "unreliable_financials":
        return _diligence_queue(gate, "G6.UNRELIABLE_FINANCIALS",
                                "financials_present_but_unreliable_cannot_score",
                                ["financial_status"])

    if fs == "no_data" or company.financial_data_missing:
        return _diligence_queue(gate, "G6.MISSING_FINANCIAL_DATA",
                                "no_market_cap_cash_debt_or_valuation_data_available",
                                ["financial_status", "financial_data_missing"])

    return _pass(gate)


# ---------------------------------------------------------------------------
# Gate 7 — Market Data Quality
# ---------------------------------------------------------------------------

_STALE_DATA_DAYS_THRESHOLD = 30        # older than this → REFRESH_REQUIRED
_VERY_STALE_DATA_DAYS_THRESHOLD = 90   # older than this → DILIGENCE_QUEUE
_ILLIQUID_VOLUME_USD_MILLIONS = 0.5    # avg daily volume below this → SEVERE_CAP


def gate_7_market_data_quality(company: CompanyProfile) -> GateResult:
    """Assess market data freshness and reliability.

    Stale market data                       → REFRESH_REQUIRED
    Extremely illiquid / microcap trap      → SEVERE_CAP 0.65
    OTC / pink sheet                        → DILIGENCE_QUEUE
    Foreign listing data gap                → DILIGENCE_QUEUE
    Unresolved corporate action             → REFRESH_REQUIRED
    """
    gate = GateName.GATE_7_MARKET_DATA_QUALITY

    if company.recent_corporate_action_unresolved:
        return _refresh_required(gate, "G7.CORPORATE_ACTION",
                                 "unresolved_corporate_action_price_data_unreliable",
                                 ["recent_corporate_action_unresolved"])

    staleness = company.market_data_staleness_days
    if staleness is not None:
        if staleness > _VERY_STALE_DATA_DAYS_THRESHOLD:
            return _diligence_queue(gate, "G7.VERY_STALE_DATA",
                                    f"market_data_{staleness}d_old_exceeds_{_VERY_STALE_DATA_DAYS_THRESHOLD}d_threshold",
                                    ["market_data_staleness_days"])
        if staleness > _STALE_DATA_DAYS_THRESHOLD:
            return _refresh_required(gate, "G7.STALE_DATA",
                                     f"market_data_{staleness}d_old_exceeds_{_STALE_DATA_DAYS_THRESHOLD}d_threshold",
                                     ["market_data_staleness_days"])

    if company.listing_type == "otc_pink":
        return _diligence_queue(gate, "G7.OTC_PINK",
                                "otc_pink_sheet_listing_data_quality_risk",
                                ["listing_type"])

    if company.listing_type == "foreign_adr":
        return _diligence_queue(gate, "G7.FOREIGN_LISTING",
                                "foreign_listing_data_gaps_may_affect_scoring_accuracy",
                                ["listing_type"])

    vol = company.avg_daily_volume_usd_millions
    if vol is not None and vol < _ILLIQUID_VOLUME_USD_MILLIONS:
        return _severe_cap(gate, "G7.ILLIQUID",
                           f"avg_daily_volume_{vol:.2f}M_below_{_ILLIQUID_VOLUME_USD_MILLIONS}M_microcap_data_trap",
                           ["avg_daily_volume_usd_millions"], 0.65)

    return _pass(gate)


# ---------------------------------------------------------------------------
# Gate 8 — Legal / Integrity
# ---------------------------------------------------------------------------

def gate_8_legal_integrity(company: CompanyProfile) -> GateResult:
    """Assess legal and integrity risk.

    Sanctions / restricted ownership            → HARD_FAIL
    Confirmed fraud                             → HARD_FAIL
    Fraud allegation (unconfirmed)              → SEVERE_CAP 0.35
    Clinical data integrity issue               → SEVERE_CAP 0.50
    SEC / enforcement cloud                     → SEVERE_CAP 0.50
    Major asset litigation                      → SEVERE_CAP 0.50 or DILIGENCE_QUEUE
    GMP / manufacturing compliance failure      → DILIGENCE_QUEUE
    """
    gate = GateName.GATE_8_LEGAL_INTEGRITY

    if company.has_sanctions:
        return _hard_fail(gate, "G8.SANCTIONS",
                          "sanctions_or_restricted_ownership_structure",
                          ["has_sanctions"])

    if company.fraud_severity == "confirmed":
        return _hard_fail(gate, "G8.FRAUD_CONFIRMED",
                          "confirmed_fraud_fundamental_integrity_failure",
                          ["fraud_severity"])

    if company.has_fraud_allegation and company.fraud_severity == "allegation":
        return _severe_cap(gate, "G8.FRAUD_ALLEGATION",
                           "unconfirmed_fraud_allegation_material_deal_risk",
                           ["has_fraud_allegation", "fraud_severity"], 0.35)

    if company.has_clinical_data_integrity_issue:
        return _severe_cap(gate, "G8.DATA_INTEGRITY",
                           "clinical_data_integrity_issue_undermines_asset_value",
                           ["has_clinical_data_integrity_issue"], 0.50)

    if company.has_sec_enforcement_cloud:
        return _severe_cap(gate, "G8.SEC_ENFORCEMENT",
                           "sec_or_regulatory_enforcement_cloud",
                           ["has_sec_enforcement_cloud"], 0.50)

    if company.has_major_asset_litigation:
        return _diligence_queue(gate, "G8.ASSET_LITIGATION",
                                "major_litigation_over_core_asset_requires_diligence",
                                ["has_major_asset_litigation"])

    if company.has_gmp_failure:
        return _diligence_queue(gate, "G8.GMP_FAILURE",
                                "manufacturing_compliance_failure_gmp_or_facility_issue",
                                ["has_gmp_failure"])

    return _pass(gate)


# ---------------------------------------------------------------------------
# Gate 9 — Commercial Relevance
# ---------------------------------------------------------------------------

def gate_9_commercial_relevance(company: CompanyProfile) -> GateResult:
    """Assess commercial viability.

    Market too small / no unmet need / me-too / reimbursement impossible → SEVERE_CAP 0.60
    Severe generic/biosimilar pressure                                   → SEVERE_CAP 0.60
    Adoption barriers too high                                           → SEVERE_CAP 0.60
    Note: geography is handled at pair level; pair-level caps not generated here.
    """
    gate = GateName.GATE_9_COMMERCIAL_RELEVANCE

    if company.addressable_market_size == "tiny":
        return _severe_cap(gate, "G9.MARKET_TOO_SMALL",
                           "addressable_market_too_small_for_standard_ma_model",
                           ["addressable_market_size"], 0.60)

    if not company.has_unmet_need:
        return _severe_cap(gate, "G9.NO_UNMET_NEED",
                           "no_clinically_meaningful_unmet_need_limits_deal_rationale",
                           ["has_unmet_need"], 0.60)

    if not company.is_differentiated:
        return _severe_cap(gate, "G9.UNDIFFERENTIATED",
                           "undifferentiated_me_too_asset_limited_strategic_value",
                           ["is_differentiated"], 0.60)

    if company.reimbursement_feasibility == "impossible":
        return _severe_cap(gate, "G9.REIMBURSEMENT_IMPOSSIBLE",
                           "reimbursement_pathway_assessed_as_impossible",
                           ["reimbursement_feasibility"], 0.60)

    if company.generic_biosimilar_pressure == "severe":
        return _severe_cap(gate, "G9.GENERIC_PRESSURE",
                           "severe_generic_or_biosimilar_pressure_on_commercial_franchise",
                           ["generic_biosimilar_pressure"], 0.60)

    if company.adoption_barriers == "high":
        return _severe_cap(gate, "G9.ADOPTION_BARRIERS",
                           "adoption_barriers_too_high_to_commercialise_at_scale",
                           ["adoption_barriers"], 0.60)

    return _pass(gate)


# ---------------------------------------------------------------------------
# Gate 10 — Eligibility Confirmation (model routing moved to Layer 0B)
# ---------------------------------------------------------------------------
#
# ARCHITECTURE NOTE (refactor 2026-06-04):
#   Gate 10 previously routed companies to specialist models based on
#   deal_type_classification (licensing_only, platform_only, etc.).
#   This responsibility now belongs to Layer 0B (classify_deal_structure_route
#   in deal_type_classification.py).
#
#   Gate 10 now only handles:
#     1. "historical_training" sentinel → HISTORICAL_ONLY (not a live candidate)
#     2. All deal types (including licensing/platform/commercial/distress) → PASS
#        (0B will assign the appropriate deal-structure route)
#
# ---------------------------------------------------------------------------

# Map legacy Gate 10 string literals to canonical DealType values.
# Retained for backward compatibility: callers that normalise or read this
# map still work.  Routing decisions are no longer made from this map.
_LEGACY_GATE10_MAP: dict[str, "str | None"] = {
    "standard_pipeline":  None,                        # → PASS
    "licensing_only":     "asset_license_partnership",
    "distress_only":      "distressed_optionality",
    "commercial_only":    "commercial_franchise_acquisition",
    "platform_only":      "platform_acquisition",
}

# _CANONICAL_ROUTING_MAP is kept as an empty dict for backward compatibility
# with callers that import it (e.g. test_deal_type_enum_drift.py).
# Model routing based on deal type now lives in Layer 0B
# (classify_deal_structure_route in deal_type_classification.py).
_CANONICAL_ROUTING_MAP: dict[str, tuple[str, RoutingModel]] = {}


def gate_10_model_routing(company: CompanyProfile) -> GateResult:
    """Confirm eligibility based on deal-type classification signal.

    Accepts both legacy Gate 10 string literals (backward-compatible via
    _LEGACY_GATE10_MAP) and canonical DealType enum values.

    Decision sequence:
      1. None → PASS (gate not invoked)
      2. "historical_training" → HISTORICAL_ONLY (special sentinel — already acquired)
      3. All other values (legacy or canonical) → PASS
         (model routing for licensing/platform/commercial/distress is owned by
         Layer 0B via classify_deal_structure_route(), not by this gate)

    The old behaviour of routing licensing_only/platform_only/commercial_only/
    distress_only to specialist models has been moved to Layer 0B so that 0A
    answers "is this target eligible?" and 0B answers "what deal structure fits?".
    """
    gate = GateName.GATE_10_MODEL_ROUTING
    dtc = company.deal_type_classification

    if dtc is None:
        return _pass(gate)

    # Special sentinel: already-acquired historical training data.
    # This is an eligibility decision (the company is gone), not a routing decision.
    if dtc == "historical_training":
        return _historical_only(gate, "G10.HISTORICAL_TRAINING",
                                "explicitly_marked_as_historical_training_case",
                                ["deal_type_classification"])

    # All deal types — including licensing, platform, commercial, distress —
    # pass Gate 10.  Layer 0B (classify_deal_structure_route) owns the model route.
    return _pass(gate)
