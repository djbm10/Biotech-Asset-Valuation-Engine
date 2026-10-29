"""Turn source claims (plus analyst decisions) into S&E ``NormalizedFact`` objects.

The facts feed the existing :class:`bve.se.gates.engine.GateEngine` unchanged. The rules:

- A value the normalizer cannot read yields **no fact**, so the gate says UNKNOWN. A free
  text target the authority cannot resolve is not a target, and a mechanism with no
  direction word is not a direction.
- Two claims that disagree on a single-valued field (phase, target set, mechanism,
  modality) yield one fact that carries the disagreement as ``contradicting_claim_ids``,
  and the gate turns that into UNKNOWN with "Reconcile the conflicting claims".
- An analyst decision is the only thing that resolves a conflict: a rejected claim is
  dropped, a confirmed claim (or a confirmed agent finding) supersedes the other claims on
  its field, and the resulting fact is marked ``analyst_confirmed``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from bve.dealscreen.importer import split_list
from bve.dealscreen.indications import qualified_indication
from bve.dealscreen.mapping import MappingProfile
from bve.dealscreen.models import (
    AgentFinding,
    AnalystAssertion,
    ClaimOrigin,
    LandscapeAsset,
    SourceClaim,
)
from bve.se.ontology.modality import normalize_modality
from bve.se.ontology.therapeutic_areas import canonical_therapeutic_area, classify_therapeutic_areas
from bve.se.schemas.contracts import NormalizedFact

TargetNormalizer = Callable[[str], str | None]

#: Confidence carried on facts. Source-provided vendor data is not BVE-confirmed.
SOURCE_CONFIDENCE = 0.6
CONFIRMED_CONFIDENCE = 0.9

_ANTAGONIST = re.compile(
    r"\b(antagonist|antagonis\w*|inhibit\w*|block\w*|neutraliz\w*|neutralis\w*)\b", re.IGNORECASE
)
_AGONIST = re.compile(r"\b(agonist|agonis\w*|activat\w*|stimulat\w*)\b", re.IGNORECASE)
_DEPLETING = re.compile(r"\b(deplet\w*|cytotoxic|adcc)\b", re.IGNORECASE)


def mechanism_direction(text: str) -> str | None:
    """ANTAGONIST / AGONIST / DEPLETING, or None when no direction word is present.

    Antagonist is tested first because "antagonist" contains "agonist". Text naming both
    directions is not read as either.
    """

    antagonist = bool(_ANTAGONIST.search(text))
    agonist = bool(_AGONIST.search(_ANTAGONIST.sub(" ", text)))
    if antagonist and agonist:
        return None
    if antagonist:
        return "ANTAGONIST"
    if agonist:
        return "AGONIST"
    if _DEPLETING.search(text):
        return "DEPLETING"
    return None


_ACTIVE_WORD = re.compile(r"\b(active|ongoing|recruiting|in development)\b")
_NEGATED_ACTIVE = re.compile(r"\b(no|not|non|without)[\s-]+(?:currently\s+)?(active|ongoing|recruiting)\b")


def activity_status(text: str) -> str:
    """ACTIVE, INACTIVE, MARKETED or UNKNOWN from status text.

    A negated activity word ("no recruiting trial") is never ACTIVE (cycle A1 F1). MARKETED is
    kept apart from ACTIVE so a marketed product does not count as active development.
    """
    folded = text.casefold()
    if any(w in folded for w in ("discontinu", "terminat", "inactive", "suspend", "halted", "no development",
                                 "no longer", "not developed", "not in development", "withdrawn")):
        return "INACTIVE"
    if _ACTIVE_WORD.search(_NEGATED_ACTIVE.sub(" ", folded)):
        return "ACTIVE"
    if re.search(r"\bmarketed\b", folded):
        return "MARKETED"
    return "UNKNOWN"


_JOINER = re.compile(r"\s*\+\s*|\s+plus\s+", re.IGNORECASE)
#: Second "components" that are not drugs (review A3-1): a procedure, placebo or standard of care.
_NON_DRUG = re.compile(r"^(placebo|thymectomy|surgery|radiotherapy|radiation|standard of care|soc|"
                       r"best supportive care|bsc|ivig|plasma exchange|plex)\b", re.IGNORECASE)


def is_combination(program_name: str) -> bool:
    """A program named as two or more drug components joined by '+' or 'plus'."""
    parts = [p.strip() for p in _JOINER.split(program_name.replace("\n", " ")) if p.strip()]
    drugs = [p for p in parts if not _NON_DRUG.match(p)]
    return len(parts) > 1 and len(drugs) > 1


_CLAUSE = re.compile(r"[;,]|\bwhile\b|\bwhereas\b|\bbut\b", re.IGNORECASE)
_PRODUCT_APPROVAL = re.compile(r"\b(marketed|approved|approval|launched|commercially available)\b", re.IGNORECASE)
#: Regulatory events that are not a marketing approval (review A5-1/2).
_NOT_MARKETING = re.compile(r"\b(ind|designation|fast track|breakthrough|orphan|clearance|irb|protocol|"
                            r"trial|study|cta|priority review|accepted)\b", re.IGNORECASE)
_NEGATION = re.compile(r"\b(not|never|no longer|not yet|withdrawn|pending|seeking|expected|planned)\b",
                       re.IGNORECASE)
#: A positive U.S. jurisdiction in the same clause. "us" only as capitalised US / U.S.
_US_JURISDICTION = re.compile(r"(?<![-\w])(?:U\.S\.|US|USA|United States|FDA|Food and Drug Administration)\b")
_EX_US = re.compile(r"\b(ex-?\s?u\.?s\.?|outside (?:the )?u\.?s\.?)", re.IGNORECASE)


def market_status(status_texts: list[str], phase_texts: list[str]) -> str | None:
    """US_MARKETED, MARKETED_NO_US_STATEMENT, PHASE4_STUDY_ONLY or None (cycle A5 K1).

    Read clause by clause: a clause counts only when it states a product approval or marketing,
    is not negated or hedged, is not another regulatory event (IND, designation, protocol), and
    names the U.S. in that same clause. Display only: no gate reads it.
    """
    us = other = False
    for text in status_texts:
        for clause in _CLAUSE.split(text):
            if (not _PRODUCT_APPROVAL.search(clause) or _NOT_MARKETING.search(clause)
                    or _NEGATION.search(clause)):
                continue
            if _US_JURISDICTION.search(clause) and not _EX_US.search(clause):
                us = True
            else:
                other = True
    if us:
        return "US_MARKETED"
    if other:
        return "MARKETED_NO_US_STATEMENT"
    if any(re.search(r"\bphase\s*(4|iv)\b", t.casefold()) for t in phase_texts):
        return "PHASE4_STUDY_ONLY"
    return None


def combine_activity(statuses: list[str]) -> str:
    """One activity value from several status claims (review A2-4).

    UNKNOWN is silence, not disagreement; ACTIVE with MARKETED is compatible (a marketed product
    with ongoing trials). Only genuinely different readings are CONFLICTING.
    """
    known = set(statuses) - {"UNKNOWN"}
    if not known:
        return "UNKNOWN"
    if known == {"ACTIVE", "MARKETED"}:
        return "ACTIVE"
    return known.pop() if len(known) == 1 else "CONFLICTING"


@dataclass(frozen=True)
class ReviewInputs:
    """The parts of the analyst decision log that change facts."""

    rejected_claim_ids: frozenset[str] = frozenset()
    confirmed_claim_ids: frozenset[str] = frozenset()
    confirmed_findings: tuple[AgentFinding, ...] = ()
    #: Active (not retracted) analyst assertions, oldest first.
    assertions: tuple[AnalystAssertion, ...] = ()


@dataclass
class AssetFacts:
    facts: list[NormalizedFact]
    #: Notes on claims that produced no fact (unreadable target, mechanism, phase...).
    unreadable: list[dict[str, str]] = field(default_factory=list)
    stage_order: int | None = None
    activity: str = "UNKNOWN"
    modality: str | None = None
    target_symbols: list[str] = field(default_factory=list)
    #: Analyst assertions that replaced a readable, different source value on their field.
    overrides: list[dict[str, Any]] = field(default_factory=list)
    #: Display-only market status (cycle A5 K1); never read by a gate.
    market_status: str | None = None
    #: Qualified indication names also read as their NCIt parent (cycle A1 F2), disclosed.
    indication_readings: list[dict[str, str]] = field(default_factory=list)


def assertion_claim(assertion: AnalystAssertion) -> SourceClaim:
    """An analyst assertion in claim form; its citation travels with it."""
    return SourceClaim(
        claim_id=assertion.assertion_id,
        asset_id=assertion.asset_id,
        field=assertion.field,
        value_as_written=assertion.value,
        origin=ClaimOrigin.ANALYST_ASSERTED,
        source_system=f"analyst:{assertion.reviewer_id}",
        dataset_version="decision_log",
        source_reference=assertion.source_url,
        source_date=assertion.source_date,
        evidence_span=assertion.evidence_span,
    )


def finding_claim(finding: AgentFinding) -> SourceClaim:
    """An analyst-confirmed agent finding, in claim form, keeping its citation."""
    return SourceClaim(
        claim_id=finding.finding_id,
        asset_id=finding.asset_id,
        field=finding.field,
        value_as_written=finding.proposed_value,
        origin=ClaimOrigin.AGENT_PROPOSED,
        source_system=finding.provider,
        dataset_version="agent",
        source_reference=finding.source_url,
        source_date=finding.document_date,
        evidence_span=finding.evidence_span,
    )


class FactBuilder:
    def __init__(self, profile: MappingProfile, target_normalizer: TargetNormalizer) -> None:
        self.profile = profile
        self.normalize_target = target_normalizer

    # -- per-field readers: claim text -> normalized value or None ---------------------
    def _targets(self, text: str) -> list[str] | None:
        parts = split_list(text.replace("/", self.profile.list_separator), self.profile.list_separator)
        symbols = [self.normalize_target(part) for part in parts]
        if not parts or any(symbol is None for symbol in symbols):
            return None
        return sorted({s for s in symbols if s})

    def readable(self, field_name: str, text: str) -> bool:
        """Whether a value for this field can be read by its normalizer (assertion check)."""
        if not text.strip():
            return False
        if field_name in {"target", "mechanism", "modality", "phase"}:
            return self._read(field_name, text) is not None
        if field_name == "us_rights":
            from bve.dealscreen.commercial import UNKNOWN, rights_status

            return rights_status(text) != UNKNOWN
        if field_name == "indication":
            from bve.se.ontology.indication_compatibility import disease_id

            # NCIt names, or a disclosed qualifier reading of one (consistent with import, review A1-3).
            return disease_id(text) is not None or qualified_indication(text) is not None
        if field_name == "therapeutic_area":
            from bve.se.ontology.therapeutic_areas import CLASSIFIED_AREAS

            mapped = self.profile.therapeutic_area_map.get(text, text)
            return canonical_therapeutic_area(mapped) in CLASSIFIED_AREAS
        return True

    def _read(self, field_name: str, text: str) -> Any:
        if field_name == "target":
            return self._targets(text)
        if field_name == "mechanism":
            return mechanism_direction(text)
        if field_name == "modality":
            return normalize_modality(text)
        if field_name == "phase":
            return self.profile.stage_order(text)
        return text

    def build(
        self,
        asset: LandscapeAsset,
        review: ReviewInputs,
        requested_areas: frozenset[str] | None = None,
    ) -> AssetFacts:
        claims = [c for c in asset.claims if c.claim_id not in review.rejected_claim_ids]
        findings = [f for f in review.confirmed_findings if f.asset_id == asset.asset_id]
        asserted = [a for a in review.assertions if a.asset_id == asset.asset_id]
        confirmed = {*review.confirmed_claim_ids, *(f.finding_id for f in findings),
                     *(a.assertion_id for a in asserted)}
        claims.extend(finding_claim(f) for f in findings)
        claims.extend(assertion_claim(a) for a in asserted)
        result = AssetFacts(facts=[])

        name_claims = [c for c in claims if c.field == "program_name"]
        if name_claims:
            result.facts.append(self._fact(asset, "identity_valid", True, name_claims[:1], [], confirmed))

        single = {
            "target": "construct_target_set",
            "mechanism": "mechanism_direction",
            "modality": "modality_id",
            "phase": "development_stage_order",
        }
        combination = is_combination(asset.program_name)
        for field_name, fact_type in single.items():
            field_claims = [c for c in claims if c.field == field_name]
            if (combination and field_name == "modality" and field_claims
                    and all(c.origin is ClaimOrigin.SOURCE_PROVIDED for c in field_claims)):
                # One vendor modality cannot describe every component (cycle A3 H1).
                result.unreadable.extend(
                    {"claim_id": c.claim_id, "field": "modality", "value": c.value_as_written,
                     "reason": "combination product: one modality stated for several components"}
                    for c in field_claims)
                continue
            fact = self._single_valued(asset, field_name, fact_type, field_claims, confirmed, result)
            if fact is not None:
                result.facts.append(fact)
                if fact_type == "development_stage_order" and not fact.contradicting_claim_ids:
                    result.stage_order = fact.value
                if fact_type == "modality_id" and not fact.contradicting_claim_ids:
                    result.modality = fact.value
                if fact_type == "construct_target_set" and not fact.contradicting_claim_ids:
                    result.target_symbols = list(fact.value)

        indication_claims = [c for c in claims if c.field == "indication"]
        indications = sorted(
            {i for c in indication_claims for i in split_list(c.value_as_written, self.profile.list_separator)}
        )
        for indication in list(indications):
            reading = qualified_indication(indication)
            if reading is not None:
                result.indication_readings.append(reading)
                if reading["read_as"] not in indications:
                    indications.append(reading["read_as"])
        if indications:
            result.facts.append(
                self._fact(asset, "indication", indications, indication_claims, [], confirmed)
            )
        ta_claims = [c for c in claims if c.field == "therapeutic_area"]
        label_areas: set[str] = set()
        for claim in ta_claims:
            for label in split_list(claim.value_as_written, self.profile.list_separator):
                mapped = self.profile.therapeutic_area_map.get(label)
                label_areas.add(canonical_therapeutic_area(mapped or label))
        indication_areas: set[str] = set()
        for indication in indications:
            indication_areas.update(classify_therapeutic_areas(indication))
        areas = label_areas | indication_areas
        if (requested_areas and not indication_areas and label_areas
                and not label_areas & set(requested_areas)):
            # A vendor area label is not exclusive (cycle A1 F8): alone it cannot exclude.
            result.unreadable.extend(
                {"claim_id": c.claim_id, "field": "therapeutic_area", "value": c.value_as_written,
                 "reason": "vendor area label alone cannot exclude (areas are not exclusive); "
                           "no readable indication gives an area"}
                for c in ta_claims)
            areas = set()
        if areas:
            result.facts.append(
                self._fact(asset, "therapeutic_area", sorted(areas),
                           ta_claims or indication_claims, [], confirmed)
            )
        statuses = [activity_status(c.value_as_written) for c in claims if c.field == "development_status"]
        result.activity = combine_activity(statuses)
        result.market_status = market_status(
            [c.value_as_written for c in claims if c.field == "development_status"],
            [c.value_as_written for c in claims if c.field == "phase"])
        return result

    def _single_valued(
        self,
        asset: LandscapeAsset,
        field_name: str,
        fact_type: str,
        claims: list[SourceClaim],
        confirmed: set[str],
        result: AssetFacts,
    ) -> NormalizedFact | None:
        decisive = [c for c in claims if c.claim_id in confirmed]
        if decisive:
            winner = decisive[-1]  # the latest analyst confirmation decides the field
            winning_value = self._read(field_name, winner.value_as_written)
            superseded = [
                c.claim_id for c in claims
                if c is not winner and (v := self._read(field_name, c.value_as_written)) is not None
                and v != winning_value
            ]
            if superseded and winner.origin is ClaimOrigin.ANALYST_ASSERTED:
                result.overrides.append({"field": field_name, "asserted_value": winner.value_as_written,
                                         "assertion_id": winner.claim_id, "superseded_claim_ids": superseded})
            claims = [winner]
        readings: list[tuple[SourceClaim, Any]] = []
        for claim in claims:
            value = self._read(field_name, claim.value_as_written)
            if value is None:
                result.unreadable.append(
                    {"claim_id": claim.claim_id, "field": field_name, "value": claim.value_as_written}
                )
                continue
            readings.append((claim, value))
        if not readings:
            return None
        first_value = readings[0][1]
        supporting = [c for c, v in readings if v == first_value]
        contradicting = [c for c, v in readings if v != first_value]
        return self._fact(asset, fact_type, first_value, supporting, contradicting, confirmed)

    @staticmethod
    def _fact(
        asset: LandscapeAsset,
        fact_type: str,
        value: Any,
        supporting: list[SourceClaim],
        contradicting: list[SourceClaim],
        confirmed: set[str],
    ) -> NormalizedFact:
        is_confirmed = bool(supporting) and all(c.claim_id in confirmed for c in supporting)
        return NormalizedFact(
            fact_id=f"{asset.asset_id}:fact:{fact_type}",
            subject_id=asset.asset_id,
            fact_type=fact_type,
            value=value,
            supporting_claim_ids=[c.claim_id for c in supporting],
            contradicting_claim_ids=[c.claim_id for c in contradicting],
            confidence=CONFIRMED_CONFIDENCE if is_confirmed else SOURCE_CONFIDENCE,
            analyst_confirmed=is_confirmed,
        )
