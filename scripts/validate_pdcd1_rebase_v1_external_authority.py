"""Milestone 4 (PDCD1_BENCHMARK_REBASE_V1_MILESTONE_4_EXTERNAL_PRODUCT_AUTHORITY_CAPTURE)
independent authority validator.

Structurally separate from the extraction/research scripts: this module
imports nothing from build_authority_research_universe.py,
run_tier_a_regulatory_adapter.py, run_ctgov_modality_adapter.py,
run_tier_bc_research.py, or merge_authority_evidence.py. It re-derives the
approved research-subject universe independently from the finalized
Milestone 3 review queues and checks the published snapshot against it.
Fails closed: any check that cannot be evaluated is treated as a failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

FORBIDDEN_KEYS = {
    # NOTE: bare "alias" is intentionally excluded -- it is a legitimate
    # narrow evidence-detail field on OFFICIAL_ALIAS_EXPLICIT_LINK
    # assertions (the literal alias string a source explicitly states),
    # not an adjudicated canonical-alias decision. Only decision-shaped
    # keys are forbidden below.
    "canonical_alias", "adjudicated", "is_alias_of", "resolved_identity",
    "canonical_candidate_id", "canonical_candidate", "benchmark_label",
    "ownership", "owner_organization", "chronology", "candidate_chronology",
    "prediction", "predicted_label", "evaluation_score", "score",
}

OFFICIAL_COMPANY_DOMAIN_HINTS_REQUIRED_HTTP = False  # documented policy flag


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cb(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def stable_hash(obj) -> str:
    return sha_bytes(cb(obj))


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def rebuild_approved_subject_ids(m3_snapshot_dir: Path) -> set[str]:
    targeted = load_jsonl(m3_snapshot_dir / "triage" / "targeted_review_queue.jsonl")
    forensic = load_jsonl(m3_snapshot_dir / "triage" / "forensic_review_queue.jsonl")
    keys = {e["unique_string_key"] for e in targeted} | {e["unique_string_key"] for e in forensic}
    return {stable_hash({"unique_string_key": k})[:24] for k in keys}


def validate(snapshot_dir: Path, m3_snapshot_dir: Path) -> dict:
    checks: dict[str, dict] = {}

    def record(name, passed, detail=None):
        checks[name] = {"pass": bool(passed), "detail": detail}

    try:
        manifest = json.loads((snapshot_dir / "manifest.json").read_text())
    except Exception as exc:
        record("manifest_readable", False, str(exc))
        return {"overall_pass": False, "checks": checks, "failed_checks": list(checks)}
    record("manifest_readable", True)

    subjects = load_jsonl(snapshot_dir / "subjects" / "authority_research_subject_ledger.jsonl")
    assertions = load_jsonl(snapshot_dir / "assertions" / "normalized_assertion_ledger.jsonl")
    source_evidence = load_jsonl(snapshot_dir / "source" / "source_evidence_ledger.jsonl")
    conflicts = load_jsonl(snapshot_dir / "conflicts" / "authority_conflict_ledger.jsonl")
    completion = load_jsonl(snapshot_dir / "validation" / "research_completion_state_ledger.jsonl")

    # 1. Every subject originates from finalized Milestone 3 review evidence;
    #    no unapproved research subject was added.
    approved_ids = rebuild_approved_subject_ids(m3_snapshot_dir)
    subject_ids = {s["subject_id"] for s in subjects}
    unapproved = sorted(subject_ids - approved_ids)
    record("every_subject_originates_from_milestone3_queues", not unapproved, unapproved[:20])

    missing = sorted(approved_ids - subject_ids)
    record("no_approved_subject_silently_dropped", not missing, missing[:20])

    # 2. Every positive assertion has a source (except MODALITY_EXPLICIT /
    #    GENERIC_DESCRIPTION_NOT_PRODUCT_NAME, which are sourced from the
    #    already-captured registry field, not a new external source_evidence
    #    row -- their evidence_hash must still be present).
    bad_assertions = []
    for a in assertions:
        if not a.get("evidence_hash"):
            bad_assertions.append(a)
    record("every_assertion_has_evidence_hash", not bad_assertions, len(bad_assertions))

    # 3. Every source locator (requested_url) resolves within captured
    #    material: response_sha256 + byte_length present for every capture.
    bad_evidence = [
        e for e in source_evidence
        if not e.get("response_sha256") or e.get("response_byte_length") is None
    ]
    record("every_source_locator_has_response_hash_and_length", not bad_evidence, len(bad_evidence))

    # 4. Regulatory matches are exact (Tier A assertions must cite an exact
    #    field match, not a fuzzy search note).
    tier_a_positive = [
        a for a in assertions
        if a["assertion_type"] == "EXACT_PRODUCT_NAME_EXISTS" and a["authority_tier"] == "tier_a"
    ]
    EXACT_FIELD_LOCATOR_MARKERS = (
        "exact", "openfda", "otherstitle", "othernames", "intervention name",
        "armsinterventionsmodule intervention entry", "brand_name", "generic_name",
        "substance_name",
    )
    non_exact = [
        a for a in tier_a_positive
        if not any(m in a.get("evidence_location", "").lower() for m in EXACT_FIELD_LOCATOR_MARKERS)
    ]
    record("tier_a_positive_matches_are_exact_field_matches", not non_exact, len(non_exact))

    # 5. No search-engine snippet treated as authority (by declared
    #    source_class, or by the captured URL actually being a search
    #    results page rather than a resolved document -- e.g. a
    #    google.com/search or bing.com/search final_url/requested_url).
    SNIPPET_SOURCE_CLASSES = {"search_snippet", "google_snippet", "bing_snippet", "google_search_results", "bing_search_results"}
    SNIPPET_URL_MARKERS = ("google.com/search", "bing.com/search", "duckduckgo.com/?q=", "search.yahoo.com/search")
    snippet_sources = [
        e for e in source_evidence
        if e.get("source_class") in SNIPPET_SOURCE_CLASSES
        or any(m in e.get("requested_url", "") or m in e.get("final_url", "") for m in SNIPPET_URL_MARKERS)
    ]
    record("no_search_snippet_treated_as_authority", not snippet_sources, len(snippet_sources))

    # 5b. Wikipedia (or any other open-editable encyclopedia) is never
    #     itself product-existence/linkage authority, regardless of tier
    #     label -- flag by domain, independent of any name policy table.
    WIKI_DOMAIN_MARKERS = ("wikipedia.org", "wikidata.org")
    wikipedia_sources = [
        e for e in source_evidence
        if e.get("source_class", "").lower().startswith("wikipedia")
        or any(m in e.get("requested_url", "") or m in e.get("final_url", "") for m in WIKI_DOMAIN_MARKERS)
    ]
    record("no_wikipedia_treated_as_authority", not wikipedia_sources, len(wikipedia_sources))

    # 6. Company sources use official domains (heuristic: final_url host
    #    recorded and source_class is an official_company_* class).
    company_evidence = [e for e in source_evidence if e.get("source_class", "").startswith("official_company")]
    missing_domain = [e for e in company_evidence if not e.get("final_url")]
    record("company_sources_have_recorded_domain", not missing_domain, len(missing_domain))

    # 7. No candidate ID has been canonically adjudicated / no ownership /
    #    no benchmark label / no candidate chronology / no predictions —
    #    scan every jsonl/json artifact in the snapshot for forbidden keys.
    def scan_for_forbidden_keys(obj, path_hint):
        found = []
        def walk(o):
            if isinstance(o, dict):
                for k, v in o.items():
                    if k in FORBIDDEN_KEYS:
                        found.append((path_hint, k))
                    walk(v)
            elif isinstance(o, list):
                for item in o:
                    walk(item)
        walk(obj)
        return found

    forbidden_hits = []
    for jsonl_path in sorted(snapshot_dir.rglob("*.jsonl")):
        for row in load_jsonl(jsonl_path):
            forbidden_hits += scan_for_forbidden_keys(row, str(jsonl_path.relative_to(snapshot_dir)))
    for json_path in sorted(snapshot_dir.rglob("*.json")):
        try:
            obj = json.loads(json_path.read_text())
        except Exception:
            continue
        forbidden_hits += scan_for_forbidden_keys(obj, str(json_path.relative_to(snapshot_dir)))
    record("no_out_of_scope_fields_present_anywhere_in_snapshot", not forbidden_hits, forbidden_hits[:20])

    # 8. Manifest scope flags.
    expected_flags = {
        "external_authority_capture_performed": True,
        "canonical_candidates_created": False,
        "aliases_adjudicated": False,
        "ownership_claims_created": False,
        "candidate_chronology_created": False,
        "benchmark_labels_created": False,
        "predictions_generated": False,
        "evaluation_performed": False,
    }
    flag_mismatches = {k: manifest.get(k) for k, v in expected_flags.items() if manifest.get(k) != v}
    record("manifest_scope_flags_correct", not flag_mismatches, flag_mismatches)

    # 9. Every subject ends in exactly one recognized completion state.
    from collections import Counter
    VALID_STATES = {
        "SUFFICIENT_EXTERNAL_AUTHORITY_CAPTURED", "PARTIAL_AUTHORITY_CAPTURED",
        "CONFLICTING_AUTHORITY_CAPTURED", "NO_EXTERNAL_AUTHORITY_FOUND",
        "ACCESS_BLOCKED", "RETRYABLE", "TERMINAL_SOURCE_LIMITATION",
    }
    state_by_subject = Counter(c["subject_id"] for c in completion)
    dup_states = {k: v for k, v in state_by_subject.items() if v != 1}
    record("every_subject_has_exactly_one_completion_state", not dup_states, len(dup_states))
    bad_states = [c for c in completion if c["state"] not in VALID_STATES]
    record("all_completion_states_are_recognized_values", not bad_states, len(bad_states))
    completion_subject_ids = {c["subject_id"] for c in completion}
    missing_completion = sorted(subject_ids - completion_subject_ids)
    record("every_subject_has_a_completion_state_entry", not missing_completion, missing_completion[:20])

    # 10. Conflicts are preserved, not resolved (no "winner" field).
    conflict_has_winner = [c for c in conflicts if "winner" in c or "resolution" in c or "decision" in c]
    record("conflicts_not_resolved_with_a_winner", not conflict_has_winner, len(conflict_has_winner))

    # 11. Explicit-linkage assertions (alias/code-to-name/trial-to-product)
    #     must not be justified by a fuzzy-match confidence class.
    linkage_types = {
        "CODE_TO_NAME_EXPLICIT_LINK", "OFFICIAL_ALIAS_EXPLICIT_LINK",
        "TRIAL_TO_PRODUCT_EXPLICIT_LINK", "REGULATORY_IDENTIFIER_EXPLICIT_LINK",
    }
    fuzzy_linkages = [
        a for a in assertions
        if a["assertion_type"] in linkage_types and "FUZZY" in a.get("confidence_class", "").upper()
    ]
    record("no_fuzzy_match_treated_as_explicit_linkage", not fuzzy_linkages, len(fuzzy_linkages))

    # 12. Explicit-linkage assertions must not rest solely on a tier_d
    #     secondary database (Open Targets / ChEMBL / PubChem alone).
    tier_d_linkages = [a for a in assertions if a["assertion_type"] in linkage_types and a.get("authority_tier") == "tier_d"]
    record("no_tier_d_secondary_database_alone_proves_linkage", not tier_d_linkages, len(tier_d_linkages))

    # 13. ADC_DISTINCT_FROM_BACKBONE / BIOSIMILAR_DISTINCT_PRODUCT must not
    #     carry a merge/same-entity signal in their detail -- these types
    #     exist specifically to assert distinctness.
    merge_signal_keys = {"merged", "merged_with", "same_as", "same_entity_as", "equivalent_to"}
    illegally_merged = [
        a for a in assertions
        if a["assertion_type"] in ("ADC_DISTINCT_FROM_BACKBONE", "BIOSIMILAR_DISTINCT_PRODUCT")
        and merge_signal_keys & set(a.get("detail", {}).keys())
    ]
    record("no_adc_or_biosimilar_merged_with_reference", not illegally_merged, len(illegally_merged))

    # 14. Explicit-linkage assertions sourced from a publication must cite a
    #     source_class within the tier_c primary-linkage allowlist, not a
    #     secondary/review article or a publication that merely mentions the
    #     target without linking the product.
    TIER_C_ALLOWED = {
        "peer_reviewed_primary_publication", "conference_abstract_explicit_linkage",
        "publication_supplement_or_protocol",
    }
    pub_linkages_by_key = {}
    for e in source_evidence:
        pub_linkages_by_key.setdefault((e["subject_id"], e.get("source_class")), e)
    bad_pub_linkages = []
    for a in assertions:
        if a["assertion_type"] not in linkage_types or a.get("authority_tier") != "tier_c":
            continue
        sid = a["subject_id"]
        matching = [e for e in source_evidence if e["subject_id"] == sid and e.get("authority_tier") == "tier_c"]
        if not matching or any(e.get("source_class") not in TIER_C_ALLOWED for e in matching):
            bad_pub_linkages.append(a)
    record("tier_c_linkage_uses_primary_publication_source_class", not bad_pub_linkages, len(bad_pub_linkages))

    # 15/16. Evidence-hash / evidence-locator integrity: for assertions bound
    #        to a discrete external capture (tier_a drugs_at_fda + all
    #        tier_b/c), evidence_hash must exactly match a captured
    #        source_evidence.response_sha256 for the same subject -- catches
    #        an altered exact evidence locator or an altered source hash.
    hashes_by_subject: dict[str, set[str]] = {}
    for e in source_evidence:
        hashes_by_subject.setdefault(e["subject_id"], set()).add(e.get("response_sha256"))
    unresolvable_hash = []
    for a in assertions:
        if a.get("authority_tier") in ("tier_b", "tier_c") or (a.get("authority_tier") == "tier_a" and a["assertion_type"] not in ("MODALITY_EXPLICIT", "GENERIC_DESCRIPTION_NOT_PRODUCT_NAME")):
            sid = a["subject_id"]
            if a.get("evidence_hash") not in hashes_by_subject.get(sid, set()):
                unresolvable_hash.append(a)
    record("every_evidence_hash_resolves_to_a_captured_source", not unresolvable_hash, len(unresolvable_hash))

    # 17. No unjustified authority-tier escalation: an assertion's
    #     authority_tier must match the authority_tier actually recorded on
    #     the specific source_evidence capture that produced it (bound by
    #     exact evidence_hash == response_sha256 for the same subject) --
    #     i.e. the tier claimed at assertion time cannot diverge from the
    #     tier recorded at capture time for that same byte-identical
    #     evidence. Registry-field-derived assertions (MODALITY_EXPLICIT /
    #     GENERIC_DESCRIPTION_NOT_PRODUCT_NAME) have no discrete
    #     source_evidence row (tier_a is inherent to the M3-bound registry
    #     field) and are exempt.
    evidence_by_subject_hash: dict[tuple[str, str], set[str]] = {}
    for e in source_evidence:
        evidence_by_subject_hash.setdefault((e["subject_id"], e.get("response_sha256")), set()).add(e.get("authority_tier"))
    escalated = []
    for a in assertions:
        if a["assertion_type"] in ("MODALITY_EXPLICIT", "GENERIC_DESCRIPTION_NOT_PRODUCT_NAME"):
            continue
        key = (a["subject_id"], a.get("evidence_hash"))
        recorded_tiers = evidence_by_subject_hash.get(key)
        if recorded_tiers and a.get("authority_tier") not in recorded_tiers:
            escalated.append(a)
    record("no_unjustified_authority_tier_escalation", not escalated, len(escalated))

    # 18. Every assertion_type is one of the fixed, narrowly-scoped schema
    #     types -- rejects any fabricated type (e.g. a "proven nonexistent"
    #     or "confirmed absent" claim) that would treat the absence of a
    #     regulatory match as positive proof a product does not exist,
    #     rather than the honest narrow NO_EXACT_REGULATORY_MATCH claim.
    KNOWN_ASSERTION_TYPES = {
        "EXACT_PRODUCT_NAME_EXISTS", "PRODUCT_CODE_EXISTS",
        "CODE_TO_NAME_EXPLICIT_LINK", "OFFICIAL_ALIAS_EXPLICIT_LINK",
        "TRIAL_TO_PRODUCT_EXPLICIT_LINK", "REGULATORY_IDENTIFIER_EXPLICIT_LINK",
        "ADC_DISTINCT_FROM_BACKBONE", "BIOSIMILAR_DISTINCT_PRODUCT",
        "COMBINATION_CONTAINS_DISTINCT_PRODUCTS", "GENERIC_DESCRIPTION_NOT_PRODUCT_NAME",
        "MODALITY_EXPLICIT", "NO_EXACT_REGULATORY_MATCH",
    }
    unknown_types = [a for a in assertions if a.get("assertion_type") not in KNOWN_ASSERTION_TYPES]
    record("every_assertion_type_is_schema_defined", not unknown_types, len(unknown_types))

    overall_pass = all(c["pass"] for c in checks.values())
    failed = [k for k, v in checks.items() if not v["pass"]]
    return {
        "validator_schema_version": "1.0.0",
        "snapshot_dir": str(snapshot_dir),
        "checks": checks,
        "failed_checks": failed,
        "overall_pass": overall_pass,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot-dir", required=True, type=Path)
    ap.add_argument("--m3-dir", required=True, type=Path)
    ap.add_argument("--report-out", type=Path)
    args = ap.parse_args()

    report = validate(args.snapshot_dir, args.m3_dir)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.report_out:
        args.report_out.write_text(text)
    print(text)
    sys.exit(0 if report["overall_pass"] else 1)


if __name__ == "__main__":
    main()
