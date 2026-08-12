"""Pure, deterministic logic for Milestone 4
(PDCD1_BENCHMARK_REBASE_V1_MILESTONE_4_EXTERNAL_PRODUCT_AUTHORITY_CAPTURE).

Nothing in this module performs network I/O. It only defines the research
subject universe, question taxonomy, priority policy, and assertion schema
as pure transforms of already-finalized Milestone 3 evidence. This module
does not create canonical candidates, adjudicate aliases, decide ownership,
assign benchmark labels, build candidate chronology, or run predictions or
evaluation.
"""
from __future__ import annotations

import hashlib
import json

RESEARCH_SCHEMA_VERSION = "1.0.0"
ASSERTION_SCHEMA_VERSION = "1.0.0"

SOURCE_AUTHORITY_POLICY = {
    "tier_a": [
        "clinicaltrials_gov_candidate_bearing_field",
        "fda_official_product_record",
        "drugs_at_fda",
        "purple_book",
        "fda_label_or_approval_package",
        "ema_or_other_official_regulatory_record",
        "official_trial_protocol_or_amendment",
        "official_governmental_or_institutional_registry",
    ],
    "tier_b": [
        "official_company_product_page",
        "official_company_pipeline_page",
        "official_company_press_release",
        "official_investor_presentation",
        "official_developer_scientific_presentation",
        "official_licensing_or_acquisition_announcement",
    ],
    "tier_c": [
        "peer_reviewed_primary_publication",
        "conference_abstract_explicit_linkage",
        "publication_supplement_or_protocol",
    ],
    "tier_d": [
        "open_targets",
        "chembl",
        "pubchem",
        "crossref_metadata",
        "other_secondary_database",
    ],
}


def cb(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_str(s: str) -> str:
    return sha_bytes(s.encode("utf-8"))


def stable_hash(obj) -> str:
    return sha_bytes(cb(obj))


SOURCE_AUTHORITY_POLICY_HASH = stable_hash(SOURCE_AUTHORITY_POLICY)


# ---------------------------------------------------------------------------
# Priority tiers (deterministic policy over Milestone 3 triage categories)
# ---------------------------------------------------------------------------

# Tier 1: single candidate-like strings whose product identity is the
#   direct blocking question (development codes, isolated names).
# Tier 2: official otherName edges -- alias-vs-product verification.
# Tier 3: multi-product/combination strings -- component decomposition.
# Tier 4: ambiguous/presentation/background-therapy strings -- lowest
#   yield, researched last if budget remains.
REASON_PRIORITY_TIER = {
    "isolated_product_like_name_or_code": 1,
    "possible_single_chemical_name_with_internal_commas": 1,
    "official_other_name_edge": 2,
    "multiple_inseparable_product_like_components": 3,
    "one_product_like_component_plus_background_therapy": 3,
    "generic_anti_pd1_language_mixed_with_possible_product_code": 4,
    "unexplained_internal_comma_not_chemical_like": 4,
    "presentation_variant_needs_authority_check": 4,
}


# ---------------------------------------------------------------------------
# Research-question taxonomy: maps a queue reason/category pair to the
# explicit narrow question(s) that must be answered for that subject.
# ---------------------------------------------------------------------------

def research_questions_for(reason: str, category: str) -> list[str]:
    questions: list[str] = []
    if reason in ("isolated_product_like_name_or_code", "possible_single_chemical_name_with_internal_commas"):
        questions += [
            "IS_ACTUAL_NAMED_INVESTIGATIONAL_PRODUCT",
            "HAS_OFFICIAL_REGULATORY_IDENTIFIER",
            "IS_DIAGNOSTIC_THERAPEUTIC_OR_PROCEDURAL",
        ]
    if reason == "official_other_name_edge":
        questions += [
            "IS_OFFICIAL_OTHER_NAME_TRUE_PRODUCT_ALIAS",
            "IS_DEVELOPMENT_CODE_EQUIVALENT_TO_NAMED_PRODUCT",
        ]
    if reason in (
        "multiple_inseparable_product_like_components",
        "one_product_like_component_plus_background_therapy",
    ):
        questions.append("COMBINATION_CONTAINS_ONE_OR_MULTIPLE_INDEPENDENT_PRODUCTS")
    if reason == "generic_anti_pd1_language_mixed_with_possible_product_code":
        questions.append("IS_GENERIC_ANTI_PD1_DESCRIPTION_NOT_PRODUCT_NAME")
    if reason == "unexplained_internal_comma_not_chemical_like":
        questions.append("COMBINATION_CONTAINS_ONE_OR_MULTIPLE_INDEPENDENT_PRODUCTS")
    if reason == "presentation_variant_needs_authority_check":
        questions.append("DO_VARIANT_SPELLINGS_REFER_TO_SAME_PRODUCT")
    if category == "MULTI_PRODUCT_OR_COMBINATION_STRING" and "COMBINATION_CONTAINS_ONE_OR_MULTIPLE_INDEPENDENT_PRODUCTS" not in questions:
        questions.append("COMBINATION_CONTAINS_ONE_OR_MULTIPLE_INDEPENDENT_PRODUCTS")
    if not questions:
        questions.append("IS_ACTUAL_NAMED_INVESTIGATIONAL_PRODUCT")
    return questions


ASSERTION_TYPES = {
    "EXACT_PRODUCT_NAME_EXISTS",
    "PRODUCT_CODE_EXISTS",
    "CODE_TO_NAME_EXPLICIT_LINK",
    "OFFICIAL_ALIAS_EXPLICIT_LINK",
    "TRIAL_TO_PRODUCT_EXPLICIT_LINK",
    "REGULATORY_IDENTIFIER_EXPLICIT_LINK",
    "ADC_DISTINCT_FROM_BACKBONE",
    "BIOSIMILAR_DISTINCT_PRODUCT",
    "COMBINATION_CONTAINS_DISTINCT_PRODUCTS",
    "GENERIC_DESCRIPTION_NOT_PRODUCT_NAME",
    "MODALITY_EXPLICIT",
    "NO_EXACT_REGULATORY_MATCH",
}

RESEARCH_COMPLETION_STATES = {
    "SUFFICIENT_EXTERNAL_AUTHORITY_CAPTURED",
    "PARTIAL_AUTHORITY_CAPTURED",
    "CONFLICTING_AUTHORITY_CAPTURED",
    "NO_EXTERNAL_AUTHORITY_FOUND",
    "ACCESS_BLOCKED",
    "RETRYABLE",
    "TERMINAL_SOURCE_LIMITATION",
}
