"""Merges per-adapter unit ledgers (ctgov modality, Tier A openFDA, and any
later Tier B/C units) into the canonical per-subject assertion ledger,
conflict ledger, and research-completion-state ledger. Pure, deterministic,
no network I/O.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRATCH = ROOT / "_m4_scratch"


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def main() -> None:
    subjects = load_jsonl(SCRATCH / "authority_research_subject_ledger.jsonl")
    modality_units = load_jsonl(SCRATCH / "ctgov_modality_units.jsonl")
    tier_a_units = load_jsonl(SCRATCH / "tier_a_units.jsonl")
    tier_bc_units = load_jsonl(SCRATCH / "tier_bc_units.jsonl")  # may not exist yet

    assertions_by_subject: dict[str, list[dict]] = {}
    source_evidence_by_subject: dict[str, list[dict]] = {}
    source_attempts: list[dict] = []

    for unit in modality_units:
        sid = unit["subject_id"]
        assertions_by_subject.setdefault(sid, []).extend(unit["assertions"])

    for unit in tier_a_units:
        sid = unit["subject_id"]
        assertions_by_subject.setdefault(sid, []).extend(unit["assertions"])
        source_evidence_by_subject.setdefault(sid, []).append(unit["source_evidence"])
        source_attempts.append({
            "subject_id": sid,
            "source_target": unit["source_target"],
            "query": unit["query"],
            "result_state": unit["research_completion_state_contribution"],
        })

    for unit in tier_bc_units:
        sid = unit["subject_id"]
        assertions_by_subject.setdefault(sid, []).extend(unit.get("assertions", []))
        if unit.get("source_evidence"):
            source_evidence_by_subject.setdefault(sid, []).append(unit["source_evidence"])
        source_attempts.append({
            "subject_id": sid,
            "source_target": unit["source_target"],
            "query": unit.get("query"),
            "result_state": unit.get("research_completion_state_contribution"),
        })

    conflicts = []
    completion_states = []

    for subject in subjects:
        sid = subject["subject_id"]
        assertions = assertions_by_subject.get(sid, [])
        types_present = {a["assertion_type"] for a in assertions}

        # Conflict detection: mixed modality, or both EXACT_PRODUCT_NAME_EXISTS
        # and NO_EXACT_REGULATORY_MATCH-as-if-terminal without resolution,
        # or contradictory modality vs product-existence signals.
        mixed_modality = any(
            a["assertion_type"] == "MODALITY_EXPLICIT" and a.get("detail", {}).get("modality") == "MIXED_ACROSS_OCCURRENCES"
            for a in assertions
        )
        if mixed_modality:
            competing = [a for a in assertions if a["assertion_type"] == "MODALITY_EXPLICIT"]
            conflicts.append({
                "subject_id": sid,
                "unique_string_key": subject["source_strings"][0],
                "conflict_class": "MODALITY_DISAGREEMENT_ACROSS_OCCURRENCES",
                "competing_assertions": competing,
                "reason_unresolved": "Intervention type field disagrees across bound occurrences (registry captured differing types for the same unique string across studies/versions).",
                "recommended_next_evidence_source": "official_company_pipeline_page or per-trial protocol review to disambiguate whether the string denotes different entities across trials",
            })

        state = None
        has_exact = "EXACT_PRODUCT_NAME_EXISTS" in types_present
        has_no_reg_match = "NO_EXACT_REGULATORY_MATCH" in types_present
        has_nonproduct = "GENERIC_DESCRIPTION_NOT_PRODUCT_NAME" in types_present
        has_tier_bc_positive = any(
            a["assertion_type"] in (
                "CODE_TO_NAME_EXPLICIT_LINK", "OFFICIAL_ALIAS_EXPLICIT_LINK",
                "TRIAL_TO_PRODUCT_EXPLICIT_LINK", "ADC_DISTINCT_FROM_BACKBONE",
                "BIOSIMILAR_DISTINCT_PRODUCT", "COMBINATION_CONTAINS_DISTINCT_PRODUCTS",
            )
            for a in assertions
        )

        # Cross-source contradiction: a Tier A regulatory record confirms an
        # approved/marketed product exists under this exact name, while the
        # registry's own intervention-type field classified the same string
        # as non-product/procedural. Not resolved -- both assertions are
        # preserved and flagged for adjudicator attention.
        if has_exact and has_nonproduct:
            competing = [
                a for a in assertions
                if a["assertion_type"] in ("EXACT_PRODUCT_NAME_EXISTS", "GENERIC_DESCRIPTION_NOT_PRODUCT_NAME")
            ]
            conflicts.append({
                "subject_id": sid,
                "unique_string_key": subject["source_strings"][0],
                "conflict_class": "REGULATORY_EXISTENCE_VS_REGISTRY_MODALITY_CONTRADICTION",
                "competing_assertions": competing,
                "reason_unresolved": "A Tier A regulatory source confirms an exact product-name match while the registry's own intervention-type field classifies the same string as non-product/procedural.",
                "recommended_next_evidence_source": "official_company_product_page or per-trial protocol review to determine whether the string denotes the regulated product or an unrelated procedural/diagnostic use of the same word",
            })

        # Cross-source contradiction: multiple distinct alias/code-linkage
        # targets asserted for the same subject (e.g. two different official
        # sources link the same code to two different product names).
        alias_link_types = ("CODE_TO_NAME_EXPLICIT_LINK", "OFFICIAL_ALIAS_EXPLICIT_LINK")
        alias_assertions = [a for a in assertions if a["assertion_type"] in alias_link_types]
        alias_target_keys = ("linked_name", "linked_entity", "official_name", "alias", "name", "product")

        def _alias_target(a: dict) -> str | None:
            detail = a.get("detail", {})
            for k in alias_target_keys:
                v = detail.get(k)
                if v:
                    return v
            return None

        alias_targets = {
            _alias_target(a) for a in alias_assertions if _alias_target(a)
        }
        if len(alias_targets) > 1:
            conflicts.append({
                "subject_id": sid,
                "unique_string_key": subject["source_strings"][0],
                "conflict_class": "COMPETING_ALIAS_LINKAGE_TARGETS",
                "competing_assertions": alias_assertions,
                "reason_unresolved": f"Distinct official sources link this string to {len(alias_targets)} different product names/codes: {sorted(alias_targets)}.",
                "recommended_next_evidence_source": "primary_publication or additional official_company_source cross-check to determine whether both linkages are simultaneously valid (e.g. co-development renaming) or mutually exclusive",
            })

        has_regulatory_modality_contradiction = has_exact and has_nonproduct
        has_competing_alias_targets = len(alias_targets) > 1

        if mixed_modality or has_regulatory_modality_contradiction or has_competing_alias_targets:
            state = "CONFLICTING_AUTHORITY_CAPTURED"
        elif has_nonproduct:
            state = "SUFFICIENT_EXTERNAL_AUTHORITY_CAPTURED"
        elif has_exact:
            state = "SUFFICIENT_EXTERNAL_AUTHORITY_CAPTURED"
        elif has_tier_bc_positive:
            state = "SUFFICIENT_EXTERNAL_AUTHORITY_CAPTURED"
        elif has_no_reg_match and tier_bc_units:
            # Tier B/C was attempted for this subject and still nothing.
            attempted = any(u["subject_id"] == sid for u in tier_bc_units)
            state = "NO_EXTERNAL_AUTHORITY_FOUND" if attempted else "PARTIAL_AUTHORITY_CAPTURED"
        elif has_no_reg_match:
            state = "PARTIAL_AUTHORITY_CAPTURED"
        else:
            state = "RETRYABLE"

        completion_states.append({
            "subject_id": sid,
            "unique_string_key": subject["source_strings"][0],
            "priority_tier": subject["priority_tier"],
            "state": state,
            "assertion_types": sorted(types_present),
        })

    with (SCRATCH / "normalized_assertion_ledger.jsonl").open("w") as f:
        for sid in sorted(assertions_by_subject):
            for a in assertions_by_subject[sid]:
                f.write(json.dumps(a, sort_keys=True) + "\n")

    with (SCRATCH / "source_evidence_ledger.jsonl").open("w") as f:
        for sid in sorted(source_evidence_by_subject):
            for e in source_evidence_by_subject[sid]:
                f.write(json.dumps(e, sort_keys=True) + "\n")

    with (SCRATCH / "source_attempt_ledger.jsonl").open("w") as f:
        for a in source_attempts:
            f.write(json.dumps(a, sort_keys=True) + "\n")

    with (SCRATCH / "authority_conflict_ledger.jsonl").open("w") as f:
        for c in conflicts:
            f.write(json.dumps(c, sort_keys=True) + "\n")

    with (SCRATCH / "research_completion_state_ledger.jsonl").open("w") as f:
        for c in completion_states:
            f.write(json.dumps(c, sort_keys=True) + "\n")

    from collections import Counter
    print("completion states:", dict(Counter(c["state"] for c in completion_states)))
    print("conflicts:", len(conflicts))
    print("total assertions:", sum(len(v) for v in assertions_by_subject.values()))


if __name__ == "__main__":
    main()
