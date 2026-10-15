"""Conservative BD research triage of displayed candidates (``bd_opportunity_triage_v1.md``).

Groups each candidate a brief shows into one of five *research* categories. It is decision
neutral: no gate, identity, target or ranking output is read differently, and nothing here
says an asset is available for a transaction. Three separate questions stay separate:

* **what the name identifies** -- a named product (development code, INN, trade name), a
  descriptive construct, or something that is not one product at all;
* **US approval** -- only from a frozen openFDA label snapshot (FDA SPL), by exact normalized
  equality of a displayed or authority name with a label's brand or generic name. No match is
  UNKNOWN, never "not approved"; several products answering one name is CONFLICTING;
* **who sponsors the registry records** -- an organisation type, never ownership.

Rules are generic: name shape and organisation type, no drug- or target-specific lists.
"""

from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict

__all__ = [
    "ApprovalStatus",
    "LabelSnapshot",
    "NameKind",
    "SponsorKind",
    "Triage",
    "TriageCategory",
    "classify_name",
    "classify_sponsors",
    "triage",
]


class TriageCategory(str, Enum):
    NAMED_INVESTIGATIONAL = "NAMED_INVESTIGATIONAL"
    APPROVED_REFERENCE = "APPROVED_REFERENCE"
    ACADEMIC_CONSTRUCT = "ACADEMIC_CONSTRUCT"
    INSUFFICIENTLY_IDENTIFIED = "INSUFFICIENTLY_IDENTIFIED"
    UNKNOWN_OR_CONFLICTING = "UNKNOWN_OR_CONFLICTING"


CATEGORY_LABEL = {
    TriageCategory.NAMED_INVESTIGATIONAL: "Named product, no US FDA label found (research)",
    TriageCategory.APPROVED_REFERENCE: "Approved / marketed reference product",
    TriageCategory.ACADEMIC_CONSTRUCT: "Academic / unnamed experimental construct",
    TriageCategory.INSUFFICIENTLY_IDENTIFIED: "Insufficiently identified",
    TriageCategory.UNKNOWN_OR_CONFLICTING: "Unknown or conflicting status",
}


class NameKind(str, Enum):
    NAMED_PRODUCT = "NAMED_PRODUCT"
    DESCRIPTIVE_CONSTRUCT = "DESCRIPTIVE_CONSTRUCT"
    NOT_ONE_PRODUCT = "NOT_ONE_PRODUCT"


class SponsorKind(str, Enum):
    COMMERCIAL = "COMMERCIAL"
    ACADEMIC = "ACADEMIC"
    UNKNOWN = "UNKNOWN"


class ApprovalStatus(str, Enum):
    US_LABEL_FOUND = "US_LABEL_FOUND"
    CONFLICTING = "CONFLICTING"
    UNKNOWN = "UNKNOWN"


class Triage(BaseModel):
    model_config = ConfigDict(frozen=True)

    category: TriageCategory
    name_kind: NameKind
    name_basis: str
    sponsor_kind: SponsorKind
    approval: ApprovalStatus
    approval_basis: str
    approval_sources: tuple[tuple[str, str], ...] = ()
    reasons: tuple[str, ...] = ()


# ----------------------------------------------------------------------------- names

#: Development code: a letter prefix with at least three letters, or at least three digits.
_CODE = re.compile(
    r"^(?=[A-Za-z]{0,8}-?\d)(?:[A-Za-z]{3,8}-?\d+|[A-Za-z]{1,8}-?\d{3,})[A-Za-z0-9-]*$"
)
#: USAN/INN stems for the products this engine meets (suffix of a lowercase INN word).
_INN_STEM = re.compile(
    r"(?:cel|leucel|mab|cept|tinib|ciclib|parib|rafenib|lisib|degib|stat|vir|tide|platin|"
    r"taxel|rubicin|mustine|zomib|lidomide|gene|tecan|sertib)$",
    re.IGNORECASE,
)
#: Second words of cell-therapy INNs: on their own they name no product.
_INN_FRAGMENT = re.compile(r"^(?:auto|cilo|mara|vic|anseged|ansegedi)?leucel$", re.IGNORECASE)
#: Words that describe a construct, a procedure or a class rather than name a product.
_DESCRIPTIVE = {
    "cell",
    "cells",
    "car",
    "car-t",
    "cart",
    "t",
    "nk",
    "injection",
    "infusion",
    "targeted",
    "targeting",
    "autologous",
    "allogeneic",
    "allogenic",
    "anti",
    "dual",
    "based",
    "derived",
    "expressing",
    "enriched",
    "lymphocytes",
    "pre-treated",
    "pretreated",
    "umbilical",
    "cord",
    "blood",
    "and",
    "with",
    "following",
    "u",
    "nanobody",
    "γδt",
    "t-cells",
    "t-lymphocytes",
}
_NOT_PRODUCT = {
    "protocol",
    "collection",
    "biospecimen",
    "specimen",
    "procedure",
    "transplant",
    "transplantation",
    "hsct",
    "allo-hsct",
    "standard",
    "care",
    "placebo",
}
_CLASS_REASON = "denotes a class of therapies"
_TOKEN = re.compile(r"[\wγδ][\wγδ\-/]*", re.UNICODE)


def _tokens(name: str) -> list[str]:
    return [t for part in _TOKEN.findall(name) for t in part.split("/") if t]


def classify_name(name: str, review_reasons: tuple[str, ...] = ()) -> tuple[NameKind, str]:
    if any(_CLASS_REASON in r for r in review_reasons):
        return NameKind.NOT_ONE_PRODUCT, "the engine flagged this name as a class of therapies"
    tokens = _tokens(name)
    lowered = [t.lower() for t in tokens]
    if not tokens:
        return NameKind.NOT_ONE_PRODUCT, "no name"
    if any(t in _NOT_PRODUCT for t in lowered):
        return NameKind.NOT_ONE_PRODUCT, "names a procedure or specimen, not a product"
    if len(tokens) == 1 and _INN_FRAGMENT.match(tokens[0]):
        return NameKind.NOT_ONE_PRODUCT, "an INN fragment, not a whole product name"
    codes = [t for t in tokens if _CODE.match(t) and not re.fullmatch(r"(?i)cd\d+[a-z]?", t)]
    if codes:
        return NameKind.NAMED_PRODUCT, f"development code {codes[0]}"
    content = [t for t, low in zip(tokens, lowered) if low not in _DESCRIPTIVE]
    if any(_INN_STEM.search(t) and len(t) >= 6 and t.isalpha() for t in content) or (
        len(tokens) == 1 and re.fullmatch(r"[a-z]{2,6}-cel", lowered[0])
    ):
        return NameKind.NAMED_PRODUCT, "INN-shaped name"
    if (
        len(tokens) == 1
        and tokens[0].isalpha()
        and tokens[0][0].isupper()
        and lowered[0] not in _DESCRIPTIVE
    ):
        return NameKind.NAMED_PRODUCT, "single proper-noun name (trade-name shape)"
    if not content or len(content) < len(tokens):
        return (
            NameKind.DESCRIPTIVE_CONSTRUCT,
            "describes a construct (target, cell type, route) rather than naming one",
        )
    return NameKind.NOT_ONE_PRODUCT, "name shape not recognised as a product"


# --------------------------------------------------------------------------- sponsors

_COMMERCIAL = re.compile(
    r"\b(?:Inc|Ltd|LLC|GmbH|Co|Corp|Corporation|AG|SA|plc|Limited|Company|Therapeutics|"
    r"Pharma\w*|Biotech\w*|Bio|Biosciences|Biomedicine|Biopharma\w*|Biologics|Oncology)\b\.?",
)
_ACADEMIC = re.compile(
    r"(?i)\b(?:University|Universit\w+|Hospital|Institute|Center|Centre|College|School|Clinic|"
    r"Network|Health System|Academy|Foundation|Medical|Research|NCI|M\.?D\.?|Ph\.?D\.?|Dr\.)\b"
)


def classify_sponsors(sponsors: str | None) -> SponsorKind:
    if not sponsors:
        return SponsorKind.UNKNOWN
    parts = [p.strip() for p in re.split(r",\s+(?=[A-Z])", sponsors) if p.strip()]
    if any(_COMMERCIAL.search(p) for p in parts):
        return SponsorKind.COMMERCIAL
    if all(_ACADEMIC.search(p) or re.fullmatch(r"[A-Za-z]+(?: [A-Za-z]+){0,2}", p) for p in parts):
        return SponsorKind.ACADEMIC
    return SponsorKind.UNKNOWN


# --------------------------------------------------------------------------- approval


_BIOLOGIC_SUFFIX = re.compile(r"-[a-z]{4}$", re.IGNORECASE)


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


class LabelSnapshot:
    """Exact-key index over a frozen openFDA label snapshot."""

    def __init__(self, payload: dict) -> None:
        self.retrieved = payload.get("retrieved", "")
        self._by_key: dict[str, list[dict]] = {}
        for label in payload.get("labels", {}).values():
            names = set(label.get("brand_name", []) + label.get("generic_name", []))
            # FDA biologic nonproprietary names carry a four-letter suffix ("-cqyv"); the core
            # name is the INN. Stripped only on the label side, only for that exact shape.
            names |= {_BIOLOGIC_SUFFIX.sub("", g) for g in label.get("generic_name", [])}
            for name in names:
                self._by_key.setdefault(_norm(name), []).append(label)

    @classmethod
    def load(cls, path: Path) -> LabelSnapshot:
        return cls(json.loads(path.read_text()))

    def lookup(
        self, names: tuple[str, ...]
    ) -> tuple[ApprovalStatus, str, tuple[tuple[str, str], ...]]:
        hits: dict[str, dict] = {}
        for name in names:
            for label in self._by_key.get(_norm(name), []) if _norm(name) else []:
                hits[label["set_id"]] = label
        if not hits:
            return (
                ApprovalStatus.UNKNOWN,
                "no FDA label with exactly this name in the snapshot (not evidence of non-approval)",
                (),
            )
        generics = {
            tuple(sorted(_norm(_BIOLOGIC_SUFFIX.sub("", g)) for g in h["generic_name"]))
            for h in hits.values()
        }
        apps = sorted({a for h in hits.values() for a in h["application_number"]})
        sources = tuple(
            sorted(
                {
                    (", ".join(h["application_number"]) or h["set_id"], h["url"])
                    for h in hits.values()
                }
            )
        )[:3]
        if len(generics) > 1:
            return (
                ApprovalStatus.CONFLICTING,
                f"the name matches FDA labels for {len(generics)} different products; the match is ambiguous",
                sources,
            )
        newest = max(h.get("effective_time") or "" for h in hits.values())
        brands = sorted({b for h in hits.values() for b in h["brand_name"]})[:3]
        return (
            ApprovalStatus.US_LABEL_FOUND,
            f"FDA label(s) {', '.join(apps[:3])} ({', '.join(brands)}); label version {newest}. "
            "US only; approval date, approved indication scope and other jurisdictions not established",
            sources,
        )


# --------------------------------------------------------------------------- triage


def triage(
    *,
    name: str,
    authority_name: str | None,
    sponsors: str | None,
    review_reasons: tuple[str, ...],
    labels: LabelSnapshot | None,
) -> Triage:
    kind, name_basis = classify_name(name, review_reasons)
    sponsor_kind = classify_sponsors(sponsors)
    names = tuple(n for n in (name, authority_name) if n)
    if labels is None:
        approval, approval_basis, sources = (
            ApprovalStatus.UNKNOWN,
            "no approval snapshot supplied",
            (),
        )
    elif kind is NameKind.NAMED_PRODUCT or authority_name:
        approval, approval_basis, sources = labels.lookup(names)
    else:
        approval, approval_basis, sources = (
            ApprovalStatus.UNKNOWN,
            "not looked up: the name does not identify one product",
            (),
        )
    reasons = [name_basis, f"registry sponsors: {sponsor_kind.value.lower()} (not ownership)"]
    if kind is NameKind.NOT_ONE_PRODUCT:
        category = TriageCategory.INSUFFICIENTLY_IDENTIFIED
    elif approval is ApprovalStatus.CONFLICTING:
        category = TriageCategory.UNKNOWN_OR_CONFLICTING
    elif approval is ApprovalStatus.US_LABEL_FOUND:
        category = TriageCategory.APPROVED_REFERENCE
        reasons.append(
            "an FDA label exists: treat as a competitor or benchmark; rights are not assessed"
        )
    elif kind is NameKind.DESCRIPTIVE_CONSTRUCT:
        category = (
            TriageCategory.ACADEMIC_CONSTRUCT
            if sponsor_kind is SponsorKind.ACADEMIC
            else TriageCategory.INSUFFICIENTLY_IDENTIFIED
        )
        if sponsor_kind is not SponsorKind.ACADEMIC:
            reasons.append(
                "descriptive name with a non-academic or unknown sponsor: identify the product first"
            )
    else:
        category = TriageCategory.NAMED_INVESTIGATIONAL
        reasons.append(
            "no US FDA label found by exact name; not evidence it is investigational (non-US approvals and unlabelled US records not checked)"
        )
    return Triage(
        category=category,
        name_kind=kind,
        name_basis=name_basis,
        sponsor_kind=sponsor_kind,
        approval=approval,
        approval_basis=approval_basis,
        approval_sources=sources,
        reasons=tuple(reasons),
    )
