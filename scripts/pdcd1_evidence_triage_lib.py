"""Pure, deterministic extraction/classification logic for Milestone 3
(PDCD1_BENCHMARK_REBASE_V1_MILESTONE_3_CANDIDATE_BEARING_EVIDENCE_EXTRACTION_AND_TRIAGE).

Nothing in this module performs I/O, network access, or randomness. Every
function is a pure transform so that two independent build processes,
given the same validated prerequisite bytes, produce byte-identical
canonical output. This module extracts and triages evidence only; it does
not create canonical candidates, aliases, ownership claims, benchmark
labels, predictions, or evaluation metrics.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata

EXTRACTOR_SCHEMA_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Canonical hashing helpers
# ---------------------------------------------------------------------------

def cb(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_str(s: str) -> str:
    return sha_bytes(s.encode("utf-8"))


def stable_hash(obj) -> str:
    return sha_bytes(cb(obj))


# ---------------------------------------------------------------------------
# Deterministic classification lexicons (versioned as part of the rules hash)
# ---------------------------------------------------------------------------

PLACEBO_CONTROL_EXACT = {
    "placebo", "control", "standard of care", "observation",
    "watchful waiting", "no intervention", "best supportive care",
    "sham", "sham procedure", "vehicle", "vehicle control",
}

GENERIC_TARGET_MODALITY_EXACT = {
    "pd-1", "pd1", "pdcd1", "pd-l1", "pdl1",
    "anti-pd-1", "anti pd-1", "anti-pd1", "antipd1",
    "anti-pd-l1", "anti pd-l1", "anti-pdl1",
    "pd-1 antibody", "pd-1 inhibitor", "anti-pd-1 antibody",
    "pd-1/pd-l1 antibody", "pd-1/pd-l1 inhibitor",
    "immunotherapy", "checkpoint inhibitor", "immune checkpoint inhibitor",
    "chemotherapy", "radiotherapy", "radiation therapy",
    "cell therapy", "car-t", "car t cell therapy", "car t-cell therapy",
    "tumor infiltrating lymphocytes", "til therapy",
    "monoclonal antibody", "targeted therapy", "combination chemotherapy",
}

PROCEDURE_DIAGNOSTIC_EXACT = {
    "surgery", "biopsy", "imaging", "mri", "ct scan", "pet scan",
    "resection", "lymphodepletion", "conditioning regimen",
    "apheresis", "leukapheresis", "endoscopy", "blood draw",
    "questionnaire", "quality of life questionnaire",
}

ROUTE_EXACT = {
    "iv", "intravenous", "oral", "subcutaneous", "sc", "im",
    "intramuscular", "topical", "intratumoral", "intravesical",
}

NCT_ID_RE = re.compile(r"^NCT\d{7,9}$", re.IGNORECASE)
DOSE_RE = re.compile(
    r"^\d+(\.\d+)?\s*(mg|mcg|g|ml|iu|mg/kg|mg/m2|mg/m\^2)\b", re.IGNORECASE
)
ARM_COHORT_RE = re.compile(
    r"^(arm|cohort|group|dose level|part)\s*[a-z0-9\-]*$", re.IGNORECASE
)

CONNECTOR_SPLIT_RE = re.compile(
    r"\s*(?:\+|;|/|\band\b|\bplus\b|\bwith\b|\bcombined with\b|\bin combination with\b"
    r"|\bfollowed by\b|\bversus\b|\bvs\.?\b)\s*",
    re.IGNORECASE,
)

# Milestone 3B Section 5: a bare comma is deliberately NOT a connector. Only
# these explicit tokens/symbols are evidence of multiple registry-string
# components; a comma inside an otherwise-single string (very common in
# IUPAC/chemical nomenclature, e.g. "1-Nitrosourea, 1-(2-chloroethyl)-3-
# cyclohexyl-") must not be silently promoted to
# MULTI_PRODUCT_OR_COMBINATION_STRING.
CHEMICAL_LOCANT_RE = re.compile(r"\d+[a-zA-Z]?-")
STEREOCHEM_RE = re.compile(r"\((?:\d*[RSEZrsez](?:,\d*[RSEZrsez])*)\)")
BRACKET_RE = re.compile(r"[\[\]{}]")
# Deliberately no suffix-based heuristic (e.g. "-ide", "-ol", "-ane"): ordinary
# drug names in a comma/"or"-separated list (e.g. "dacarbazine, temozolomide,
# paclitaxel or platinum") commonly end in such suffixes, so a suffix rule
# would misclassify a genuine multi-drug list as one chemical name. Only
# structural IUPAC evidence (locants, stereodescriptors, brackets) counts.

TRADEMARK_CHARS = "™®©"  # ™ ® ©
HYPHEN_VARIANTS = "‐‑‒–—―-"

TRIAGE_CATEGORIES = (
    "ISOLATED_PRODUCT_LIKE_STRING",
    "OFFICIAL_OTHER_NAME_STRING",
    "MULTI_PRODUCT_OR_COMBINATION_STRING",
    "GENERIC_TARGET_OR_MODALITY_STRING",
    "EXPLICIT_NONPRODUCT_INTERVENTION",
    "PLACEBO_OR_CONTROL",
    "DOSE_ROUTE_COHORT_OR_ARM_TEXT",
    "PROCEDURE_OR_DIAGNOSTIC_DESCRIPTION",
    "AMBIGUOUS_REQUIRES_REVIEW",
    "MALFORMED_OR_EMPTY",
)

RULES_DEFINITION = {
    "schema_version": EXTRACTOR_SCHEMA_VERSION,
    "placebo_control_exact": sorted(PLACEBO_CONTROL_EXACT),
    "generic_target_modality_exact": sorted(GENERIC_TARGET_MODALITY_EXACT),
    "procedure_diagnostic_exact": sorted(PROCEDURE_DIAGNOSTIC_EXACT),
    "route_exact": sorted(ROUTE_EXACT),
    "nct_id_pattern": NCT_ID_RE.pattern,
    "dose_pattern": DOSE_RE.pattern,
    "arm_cohort_pattern": ARM_COHORT_RE.pattern,
    "connector_split_pattern": CONNECTOR_SPLIT_RE.pattern,
    "chemical_locant_pattern": CHEMICAL_LOCANT_RE.pattern,
    "stereochem_pattern": STEREOCHEM_RE.pattern,
    "bracket_pattern": BRACKET_RE.pattern,
}

EXTRACTION_RULES_HASH = stable_hash(RULES_DEFINITION)


def normalize_nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def presentation_key(s: str) -> str:
    """Deterministic key collapsing pure presentation differences only."""
    t = unicodedata.normalize("NFC", s)
    t = t.strip()
    for ch in TRADEMARK_CHARS:
        t = t.replace(ch, "")
    for ch in HYPHEN_VARIANTS:
        t = t.replace(ch, "-")
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s*-\s*", "-", t)
    t = re.sub(r"\s*,\s*", ", ", t)
    t = t.casefold()
    return t.strip()


def normalize_for_lexicon(s: str) -> str:
    t = presentation_key(s)
    t = t.strip(" .")
    return t


def looks_chemical_like(stripped: str) -> bool:
    """Conservative signal that a string is a single IUPAC/chemical-style
    name whose internal commas are punctuation, not product separators.
    Any one structural signal (locants, stereodescriptors, or brackets) is
    enough to treat the string as one ambiguous unit.
    """
    return bool(
        CHEMICAL_LOCANT_RE.search(stripped)
        or STEREOCHEM_RE.search(stripped)
        or BRACKET_RE.search(stripped)
    )


def classify_content(raw: str) -> tuple[str, dict]:
    """Return (category, flags) based on string content alone, ignoring
    which field it was observed in. This is the content-based category;
    the OFFICIAL_OTHER_NAME_STRING override is applied by the caller,
    which has field-provenance context this function does not.

    Milestone 3B Section 5: a bare comma no longer implies multiple
    products. Comma-containing strings are routed through a conservative
    chemical-name check; the resulting POSSIBLE_SINGLE_CHEMICAL_NAME_WITH_
    INTERNAL_COMMAS flag never decides identity by itself, and strings
    that are neither chemical-like nor otherwise unambiguous are sent to
    AMBIGUOUS_REQUIRES_REVIEW rather than guessed at.
    """
    stripped = raw.strip()
    flags = {
        "contains_target_token": bool(
            re.search(r"pd-?1|pdcd1|pd-?l1", raw, re.IGNORECASE)
        ),
        "contains_connector": bool(CONNECTOR_SPLIT_RE.search(stripped)),
        "is_nct_id_like": bool(NCT_ID_RE.match(stripped)),
        "has_comma": "," in stripped,
        "looks_chemical_like": looks_chemical_like(stripped),
    }
    flags["possible_single_chemical_name_with_internal_commas"] = (
        flags["has_comma"] and not flags["contains_connector"] and flags["looks_chemical_like"]
    )

    if not stripped:
        return "MALFORMED_OR_EMPTY", flags

    norm = normalize_for_lexicon(stripped)

    if flags["is_nct_id_like"]:
        return "EXPLICIT_NONPRODUCT_INTERVENTION", flags

    if norm in PLACEBO_CONTROL_EXACT:
        return "PLACEBO_OR_CONTROL", flags

    if norm in GENERIC_TARGET_MODALITY_EXACT:
        return "GENERIC_TARGET_OR_MODALITY_STRING", flags

    if norm in ROUTE_EXACT or DOSE_RE.match(stripped) or ARM_COHORT_RE.match(stripped):
        return "DOSE_ROUTE_COHORT_OR_ARM_TEXT", flags

    if norm in PROCEDURE_DIAGNOSTIC_EXACT:
        return "PROCEDURE_OR_DIAGNOSTIC_DESCRIPTION", flags

    if len(stripped) > 200:
        return "AMBIGUOUS_REQUIRES_REVIEW", flags

    if flags["contains_connector"]:
        return "MULTI_PRODUCT_OR_COMBINATION_STRING", flags

    if flags["has_comma"]:
        # No explicit connector token fired. Never guess: chemical-like
        # commas stay one ambiguous product-like unit; anything else with
        # an unexplained comma is uncertain and must be reviewed, not
        # silently classified either way.
        if flags["looks_chemical_like"] and 1 <= len(stripped) <= 200:
            return "ISOLATED_PRODUCT_LIKE_STRING", flags
        return "AMBIGUOUS_REQUIRES_REVIEW", flags

    if 1 <= len(stripped) <= 120:
        return "ISOLATED_PRODUCT_LIKE_STRING", flags

    return "AMBIGUOUS_REQUIRES_REVIEW", flags


def classify(raw: str, field_class: str, is_otherName_only: bool) -> tuple[str, dict]:
    category, flags = classify_content(raw)
    if is_otherName_only and category == "ISOLATED_PRODUCT_LIKE_STRING":
        category = "OFFICIAL_OTHER_NAME_STRING"
    flags["field_class"] = field_class
    return category, flags


def classify_component(segment: str) -> str:
    stripped = segment.strip()
    if not stripped:
        return "EMPTY_COMPONENT"
    norm = normalize_for_lexicon(stripped)
    if norm in PLACEBO_CONTROL_EXACT:
        return "placebo_or_control_component"
    if norm in GENERIC_TARGET_MODALITY_EXACT:
        return "generic_target_or_modality_component"
    if norm in ROUTE_EXACT or DOSE_RE.match(stripped) or ARM_COHORT_RE.match(stripped):
        return "dose_route_cohort_component"
    if norm in PROCEDURE_DIAGNOSTIC_EXACT:
        return "procedure_or_diagnostic_component"
    if 1 <= len(stripped) <= 120:
        return "possible_product_like_component"
    return "ambiguous_component"


def parse_components(raw: str) -> list[dict]:
    """Split only on explicit, unambiguous connector tokens. Never rewrites
    the source text; records character offsets into the original string.
    """
    components = []
    pos = 0
    stripped = raw
    for match in CONNECTOR_SPLIT_RE.finditer(stripped):
        segment = stripped[pos:match.start()]
        if segment.strip():
            components.append(
                {
                    "text": segment,
                    "start_offset": pos,
                    "end_offset": match.start(),
                    "component_class": classify_component(segment),
                }
            )
        pos = match.end()
    tail = stripped[pos:]
    if tail.strip():
        components.append(
            {
                "text": tail,
                "start_offset": pos,
                "end_offset": len(stripped),
                "component_class": classify_component(tail),
            }
        )
    if len(components) <= 1:
        return []
    return components


def review_routing(unique_string_row: dict) -> list[dict]:
    """Return zero or more review-queue routing entries with explicit reasons.
    Does not resolve or adjudicate; purely explains why a record is routed.
    """
    routes = []
    category = unique_string_row["triage_category"]
    flags = unique_string_row["flags"]
    components = unique_string_row.get("components", [])

    if category == "ISOLATED_PRODUCT_LIKE_STRING":
        routes.append({"queue": "TARGETED", "reason": "isolated_product_like_name_or_code"})
    if category == "OFFICIAL_OTHER_NAME_STRING":
        routes.append({"queue": "TARGETED", "reason": "official_other_name_edge"})
    if unique_string_row.get("presentation_group_size", 1) > 1 and category in (
        "ISOLATED_PRODUCT_LIKE_STRING", "OFFICIAL_OTHER_NAME_STRING",
    ):
        routes.append({"queue": "TARGETED", "reason": "presentation_variant_needs_authority_check"})
    if category == "MULTI_PRODUCT_OR_COMBINATION_STRING":
        product_like = [c for c in components if c["component_class"] == "possible_product_like_component"]
        if len(product_like) >= 2:
            routes.append({"queue": "FORENSIC", "reason": "multiple_inseparable_product_like_components"})
        elif len(product_like) == 1:
            routes.append({"queue": "TARGETED", "reason": "one_product_like_component_plus_background_therapy"})
        else:
            routes.append({"queue": "FORENSIC", "reason": "combination_string_with_no_isolable_product_like_component"})
        if flags.get("contains_target_token"):
            routes.append({"queue": "FORENSIC", "reason": "generic_anti_pd1_language_mixed_with_possible_product_code"})
    if category == "AMBIGUOUS_REQUIRES_REVIEW":
        if flags.get("has_comma") and not flags.get("contains_connector"):
            routes.append({"queue": "FORENSIC", "reason": "unexplained_internal_comma_not_chemical_like"})
        else:
            routes.append({"queue": "FORENSIC", "reason": "unparseable_or_ambiguous_string"})
    if flags.get("possible_single_chemical_name_with_internal_commas"):
        routes.append({"queue": "TARGETED", "reason": "possible_single_chemical_name_with_internal_commas"})
    return routes
