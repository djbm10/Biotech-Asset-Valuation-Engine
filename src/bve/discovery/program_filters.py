"""Filters that drop junk before it reaches the routing/review queue.

The first review cycle showed the dominant false-positive class is not modality —
it is "what counts as a lead." Three patterns recur:

1. generic / comparator drug arms picked as the "lead" (warfarin, gemcitabine,
   standard-of-care backbones);
2. partner / someone-else's molecule run in a collaborator trial (the company is
   not the originator);
3. device / diagnostics companies that pass the liquidity screen but do not
   develop therapeutics.

These helpers are pure and deterministic (no network, no LLM), used by
``program_cluster`` (drop comparator programs) and ``routing`` (originator gate,
device/dx exclusion).
"""
from __future__ import annotations

import re

# Generic / comparator / backbone agents that are never a biotech's *lead* asset.
# Matched against the drug name, canonical key, and synonyms. Placebo / standard-
# of-care are already dropped upstream in sponsor_trials, but kept here too for the
# canonical-key path (e.g. CT.gov labels a warfarin arm "anticoagulation").
_GENERIC_COMPARATORS: set[str] = {
    "warfarin", "coumadin", "anticoagulation", "heparin", "enoxaparin", "aspirin",
    "gemcitabine", "gemzar", "paclitaxel", "nab-paclitaxel", "abraxane", "docetaxel",
    "carboplatin", "cisplatin", "oxaliplatin", "doxorubicin", "cyclophosphamide",
    "fluorouracil", "5-fu", "capecitabine", "irinotecan", "methotrexate",
    "vincristine", "etoposide", "pemetrexed", "dacarbazine", "temozolomide",
    "cytarabine", "azacitidine", "decitabine", "dexamethasone", "prednisone",
    "prednisolone", "folfox", "folfiri", "chemotherapy", "standard of care",
    "best supportive care", "investigator's choice", "physician's choice",
    "placebo", "saline",
    # Immuno-oncology checkpoint inhibitors — ubiquitous combo backbones / active
    # comparators, never a small biotech's *originated* lead.
    "pembrolizumab", "keytruda", "nivolumab", "opdivo", "atezolizumab", "tecentriq",
    "durvalumab", "imfinzi", "cemiplimab", "libtayo", "ipilimumab", "yervoy",
    "rituximab", "rituxan", "bevacizumab", "avastin", "trastuzumab", "herceptin",
    "cetuximab", "erbitux", "sorafenib", "nexavar", "niraparib", "zejula",
    "biosimilar",
}

# Company-name cues for device / diagnostics / imaging firms (not drug developers).
_DEVICE_DX_RE = re.compile(
    r"\b(surgical|surgery|devices?|diagnostics?|imaging|robotics?|instruments?|"
    r"medtech|medical systems|orthopaedics?|orthopedics?|implants?)\b",
    re.I,
)


# A conjugated / novel derivative built on a backbone INN is itself a real asset
# (e.g. "trastuzumab deruxtecan" is an ADC, not a trastuzumab comparator). When any
# of these cues is present, do not treat the drug as a plain generic comparator.
_CONJUGATE_GUARD_RE = re.compile(
    r"(deruxtecan|emtansine|vedotin|govitecan|duocarmazine|tirumotecan|conjugate)",
    re.I,
)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower()).strip()


def is_generic_comparator(*names: str, drug_key: str = "") -> bool:
    """True when a program's drug is a generic comparator / backbone, not a lead.

    Checks the canonical key and each name/synonym: a denylisted token appearing
    as a whole word, or a multi-word denylist phrase as a substring. A conjugated
    derivative (ADC etc.) built on a backbone INN is exempt — it is a real asset.
    """
    candidates = [drug_key, *names]
    if any(_CONJUGATE_GUARD_RE.search(c or "") for c in candidates):
        return False
    for raw in candidates:
        norm = _norm(raw)
        if not norm:
            continue
        tokens = set(norm.split())
        for entry in _GENERIC_COMPARATORS:
            if " " in entry:
                if entry in norm:
                    return True
            elif entry in tokens:
                return True
    return False


def is_device_or_dx_company(company_name: str) -> bool:
    """True for obvious device / diagnostics / imaging companies (not therapeutics)."""
    return bool(_DEVICE_DX_RE.search(company_name or ""))
