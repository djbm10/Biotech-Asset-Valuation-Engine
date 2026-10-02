"""Construct target sets from NCIt, only where two curated NCIt statements agree.

NCI files CAR products under curated antigen classes ("Anti-CD19 CAR T Cells Preparation").
That is curation, not prose, but it is incomplete: dual constructs often carry only one of
their two classes, and a ``construct_target_set`` is read as a *complete* description. So a
class set (E1) is emitted only when the definition's mechanism sentence -- "Upon
administration, X ... induce selective toxicity in BCMA-expressing tumor cells" -- names
exactly the same genes (E2). That sentence says what the product is directed *to*; CAR
architecture (hinge, costimulatory and signaling domains, switches, armoring) is written in
the product's own name, which the preposition-governed positions below never read.

Everything else is UNKNOWN with a reason code, including antigens that are not one human
gene (GD2, Claudin18.2). Policy: ``docs/se_policies/ncit_target_sidecar_v1.md``; the frozen
reference implementation is ``research/se_ncit/reader_frozen_v1.py``.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path

SIDECAR_VERSION = "ncit_target_sidecar_v1"
#: Key under ``RunManifest.extractor_versions`` that pins the sidecar for replay.
NCIT_EXTRACTOR_KEY = "ncit_target_sidecar"
NCIT_RELEASE = "26.08e"
_DEFAULT_PATH = Path("data/se/ontology/ncit/ncit_26.08e_targets.json")

#: CAR roots and the antineoplastic immune-cell root (§3.1).
POPULATION_ROOTS = ("C126102", "C137999", "C201933", "C129826")

#: NCIt antigen class -> (HGNC symbol or None, non-gene reason, NCIt's own surface forms).
#: Frozen by hand from the class names and definitions (§3.2). Not a target resolver: the
#: resolver's homonyms (``CD20``) are exactly what this route must not inherit.
CLASS_MAP: dict[str, tuple[str | None, str | None, tuple[str, ...]]] = {
    "C201492": ("CD276", None, ("B7-H3", "CD276")),
    "C176023": ("TNFRSF17", None, ("BCMA", "TNFRSF17")),
    "C201493": ("IL3RA", None, ("CD123",)),
    "C176018": ("CD19", None, ("CD19",)),
    "C201174": ("MS4A1", None, ("CD20",)),
    "C201173": ("CD22", None, ("CD22",)),
    "C201495": ("CD33", None, ("CD33",)),
    "C201510": ("CD38", None, ("CD38",)),
    "C211937": ("CD5", None, ("CD5",)),
    "C201176": ("CD70", None, ("CD70",)),
    "C226253": ("CD79B", None, ("CD79b",)),
    "C201172": (None, "isoform_specific_antigen", ("Claudin18.2", "CLDN18.2")),
    "C226930": ("DLL3", None, ("DLL3",)),
    "C201175": ("EGFR", None, ("EGFR",)),
    "C201491": (None, "non_protein_antigen", ("GD2",)),
    "C225034": ("GPC3", None, ("GPC-3", "GPC3")),
    "C212993": ("GPRC5D", None, ("GPRC5D",)),
    "C201497": ("ERBB2", None, ("HER2", "ErbB2", "HER-2")),
    "C201178": ("FOLH1", None, ("PSMA",)),
    "C224031": ("ROR1", None, ("ROR1",)),
    "C201275": ("MSLN", None, ("mesothelin", "MSLN")),
}


def _surface_key(value: str) -> str:
    return re.sub(r"[^a-z0-9.]", "", value.casefold())


def _class_value(code: str) -> str:
    gene, _, _ = CLASS_MAP[code]
    return f"TARGET:{gene}" if gene else f"NONGENE:{code}"


_SURFACE = {
    _surface_key(form): _class_value(code)
    for code, (gene, _, forms) in CLASS_MAP.items()
    for form in (*forms, *((gene,) if gene else ()))
}

# -- E2: the mechanism sentence (§3.3) -------------------------------------------------

_MECHANISM_START = re.compile(r"^(Upon|After|Following)\b")
_SEG = r"[A-Za-z0-9][A-Za-z0-9.*+\-]*?(?:/[A-Za-z0-9][A-Za-z0-9.*+\-]*?)*"
_GOVERNOR = (
    r"(?:in|to|toward|towards|against|kill|kills|lyse|lyses|recognize|recognizes"
    r"|target|targets|of|both)"
)
_POSITIONS = (
    re.compile(
        _GOVERNOR + r",?\s+(?:the\s+)?(?:both\s+)?(" + _SEG + r")(?:-?\s*(?:,|and/or|and|or)\s+("
        + _SEG + r"))?-(?:expressing|positive|overexpressing)\b"
    ),
    re.compile(
        r"(?:tumor|cancer|neoplastic|malignant)\s+(?:B-)?cells\s+(?:that\s+)?"
        r"(?:express(?:ing)?|overexpress(?:ing)?)\s+(?:the\s+)?(" + _SEG
        + r")(?:\s+(?:and/or|and|or)\s+(" + _SEG + r"))?\b"
    ),
    re.compile(r"\bthe\s+(" + _SEG + r")\s+antigen\s+on\b"),
    re.compile(
        r"\bbind(?:s)?\s+to\s+(?:the\s+)?(" + _SEG + r")(?:\s+and\s+(" + _SEG
        + r"))?\s+(?:on|expressed)\b"
    ),
)


def mechanism_sentence(definition: str) -> str | None:
    for sentence in re.split(r"(?<=\.)\s+(?=[A-Z])", definition):
        if _MECHANISM_START.match(sentence):
            return sentence
    return None


def _symbol_shaped(value: str) -> bool:
    body = value.replace("-", "").replace(".", "")
    if not re.match(r"^[A-Za-z][A-Za-z0-9]*$", body):
        return False
    uppers = sum(char.isupper() for char in body)
    return uppers >= 2 or (uppers >= 1 and any(char.isdigit() for char in body))


def _strict(mention: str) -> str | None:
    """Approved symbol, or a synonym of at least three characters; otherwise nothing."""

    from bve.se.ontology.targets import resolve_target

    result = resolve_target(mention)
    if result is None or not result.canonical_id:
        return None
    matched = result.basis.matched_alias if result.basis else mention
    approved = re.sub(r"[^A-Z0-9]", "", matched.upper()) == re.sub(
        r"[^A-Z0-9]", "", (result.canonical_symbol or "").upper()
    )
    if not approved and len(re.sub(r"[^A-Za-z0-9]", "", matched)) < 3:
        return None
    return result.canonical_id


def _read_part(part: str) -> str:
    part = part.strip("-.,* ")
    if _surface_key(part) in _SURFACE:
        return _SURFACE[_surface_key(part)]
    if _symbol_shaped(part):
        return _strict(part) or f"UNRESOLVED:{part}"
    return f"UNRESOLVED:{part}"


def mechanism_antigens(definition: str) -> tuple[frozenset[str] | None, str]:
    """E2: what the mechanism sentence says the product is directed to, or why not."""

    sentence = mechanism_sentence(definition)
    if sentence is None:
        return None, "no_mechanism_sentence"
    found: set[str] = set()
    for position in _POSITIONS:
        for match in position.finditer(sentence):
            for group in match.groups():
                if group:
                    found.update(_read_part(part) for part in group.split("/"))
    unresolved = sorted(value for value in found if value.startswith("UNRESOLVED"))
    if unresolved:
        return None, "unresolved:" + ",".join(unresolved)
    if not found:
        return None, "no_antigen"
    return frozenset(found), "ok"


@dataclass(frozen=True)
class ConceptDecision:
    """The emit/refuse decision for one NCIt product concept (§3.4)."""

    targets: tuple[str, ...]
    reason: str
    class_set: tuple[str, ...]
    mechanism_set: tuple[str, ...]


def decide(class_codes: set[str], definition: str) -> ConceptDecision:
    class_set = {_class_value(code) for code in class_codes if code in CLASS_MAP}
    mechanism, why = mechanism_antigens(definition)
    mech = tuple(sorted(mechanism or ()))
    if not class_set:
        return ConceptDecision((), "no_antigen_class", (), mech)
    nongene = sorted(value for value in class_set if value.startswith("NONGENE"))
    if nongene:
        reason = CLASS_MAP[nongene[0].split(":", 1)[1]][1] or "non_gene_class"
        return ConceptDecision((), reason, tuple(sorted(class_set)), mech)
    if mechanism is None:
        return ConceptDecision((), why.split(":", 1)[0], tuple(sorted(class_set)), mech)
    if mechanism != class_set:
        return ConceptDecision((), "class_mechanism_disagree", tuple(sorted(class_set)), mech)
    return ConceptDecision(tuple(sorted(class_set)), "emit", tuple(sorted(class_set)), mech)


# -- building the sidecar from the pinned release ---------------------------------------


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def build_sidecar(flat_txt: Path, *, release_zip_sha256: str) -> dict:
    """Every population concept with its names, decision and evidence, as plain data."""

    csv.field_size_limit(1 << 30)
    concepts: dict[str, dict] = {}
    with flat_txt.open(encoding="utf-8") as handle:
        for row in csv.reader(handle, delimiter="\t", quoting=csv.QUOTE_NONE):
            code, _, parents, synonyms, definition, display = row[:6]
            names = [name for name in synonyms.split("|") if name]
            concepts[code] = {
                "parents": [parent for parent in parents.split("|") if parent],
                "names": names,
                "definition": definition,
                "name": display or (names[0] if names else code),
            }

    ancestors_cache: dict[str, frozenset[str]] = {}

    def ancestors(code: str) -> frozenset[str]:
        if code not in ancestors_cache:
            found: set[str] = set()
            stack = list(concepts.get(code, {}).get("parents", ()))
            while stack:
                parent = stack.pop()
                if parent in found or parent not in concepts:
                    continue
                found.add(parent)
                stack.extend(concepts[parent]["parents"])
            ancestors_cache[code] = frozenset(found)
        return ancestors_cache[code]

    excluded = set(CLASS_MAP) | set(POPULATION_ROOTS)
    products = {}
    for code in sorted(concepts):
        if code in excluded or not ancestors(code) & set(POPULATION_ROOTS):
            continue
        concept = concepts[code]
        decision = decide(set(ancestors(code)) & set(CLASS_MAP), concept["definition"])
        products[code] = {
            "name": concept["name"],
            "names": sorted(set(concept["names"]) | {concept["name"]}),
            "classes": sorted(set(ancestors(code)) & set(CLASS_MAP)),
            "targets": list(decision.targets),
            "reason": decision.reason,
            "class_set": list(decision.class_set),
            "mechanism_set": list(decision.mechanism_set),
            "mechanism_sentence": mechanism_sentence(concept["definition"]),
            "definition_sha256": hashlib.sha256(concept["definition"].encode()).hexdigest(),
        }
    from bve.se.ontology.targets import ontology_version

    return {
        "version": SIDECAR_VERSION,
        "ncit_release": NCIT_RELEASE,
        "release_zip_sha256": release_zip_sha256,
        "target_ontology_version": ontology_version(),
        "products": products,
    }


# -- runtime ---------------------------------------------------------------------------


def default_sidecar_path() -> Path:
    override = os.environ.get("BVE_SE_NCIT_SIDECAR")
    return Path(override) if override else _DEFAULT_PATH


def _link_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


@dataclass(frozen=True)
class NcitLink:
    code: str
    matched_name: str | None
    reason: str


class NcitTargetAuthority:
    def __init__(self, payload: dict, sha256: str) -> None:
        self.payload = payload
        self.sha256 = sha256
        self.products: dict[str, dict] = payload["products"]
        index: dict[str, set[str]] = {}
        for code, product in self.products.items():
            for name in product["names"]:
                key = _link_key(name)
                if key:
                    index.setdefault(key, set()).add(code)
        self._index = index

    @property
    def version_token(self) -> str:
        return f"{SIDECAR_VERSION}@ncit_{self.payload['ncit_release']}@{self.sha256[:16]}"

    def link(self, names: list[str]) -> NcitLink | None:
        """The one product concept these names reach, ``None`` when none (§3.5)."""

        from bve.se.discovery.class_terms import is_class_term

        hits: dict[str, str] = {}
        for name in names:
            if not name or is_class_term(name):
                continue
            for code in sorted(self._index.get(_link_key(name), ())):
                hits.setdefault(code, name)
        if not hits:
            return None
        if len(hits) > 1:
            return NcitLink(code=",".join(sorted(hits)), matched_name=None, reason="ambiguous_link")
        code, name = next(iter(hits.items()))
        return NcitLink(code=code, matched_name=name, reason=self.products[code]["reason"])


@lru_cache(maxsize=4)
def _load(path: str) -> NcitTargetAuthority | None:
    file = Path(path)
    if not file.exists():
        return None
    raw = file.read_bytes()
    return NcitTargetAuthority(json.loads(raw), hashlib.sha256(raw).hexdigest())


def ncit_authority() -> NcitTargetAuthority | None:
    return _load(str(default_sidecar_path()))


def reset_ncit_cache() -> None:
    _load.cache_clear()


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def ncit_construct_evidence(asset_id: str, link: NcitLink, authority: NcitTargetAuthority,
                            *, as_of_date: date):
    """The fact for a linked, emitting concept, with its document and claim; else ``None``."""

    from bve.se.evidence.construct_targets import ConstructTargetEvidence
    from bve.se.schemas.contracts import (
        ExtractedClaim,
        NormalizedFact,
        SourceDocument,
        SourceTier,
        VerificationStatus,
    )

    if link.reason != "emit":
        return None
    product = authority.products[link.code]
    targets = sorted(product["targets"])
    release = authority.payload["ncit_release"]
    document = SourceDocument(
        document_id=_id("doc", "ncit", release, authority.sha256),
        source_url=f"urn:ncit:{release}",
        publisher="NCI Thesaurus",
        document_type="ontology_snapshot",
        retrieval_date=_EPOCH,
        content_hash=authority.sha256,
        source_tier=SourceTier.REGISTRY,
        public_only=True,
    )
    claim = ExtractedClaim(
        claim_id=_id("claim", asset_id, "construct_target_set", link.code, *targets),
        subject_id=asset_id,
        predicate="construct_target_set",
        normalized_value=targets,
        source_document_id=document.document_id,
        supporting_passage=product["mechanism_sentence"] or "",
        locator=(
            f"NCIt:{link.code}#class=[{','.join(product['class_set'])}];"
            f"mechanism=[{','.join(product['mechanism_set'])}];link={link.matched_name}"
        ),
        direct_observation=True,
        extraction_method="ncit_class_mechanism_agreement",
        extractor_version=SIDECAR_VERSION,
        extraction_confidence=0.95,
        verification_status=VerificationStatus.MACHINE_VERIFIED,
        applicable_as_of_date=as_of_date,
    )
    fact = NormalizedFact(
        fact_id=_id("fact", asset_id, "construct_target_set", *targets),
        subject_id=asset_id,
        fact_type="construct_target_set",
        value=targets,
        supporting_claim_ids=[claim.claim_id],
        confidence=0.95,
    )
    return ConstructTargetEvidence(documents=[document], claims=[claim], fact=fact)


def _id(prefix: str, *parts: str) -> str:
    return f"{prefix}:{hashlib.sha256('|'.join(parts).encode()).hexdigest()[:20]}"
