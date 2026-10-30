"""Rights evidence: import a deals/rights export and derive a rights position per buyer territory (cycle R1).

Vendor deal databases are exported separately from pipeline databases. This module reads such an export
through a YAML profile, keeps every event's provenance (file hash, row, URL, verbatim quote, date) and
derives, for one program and one buyer territory, *what the evidence says about who holds rights there*.

Rules:

- Nothing is inferred from an empty field, a trial sponsor, an FDA labeler or a collaborator list. Only
  rows in the rights file are evidence.
- Absence of a known grant is never availability. Availability is only ever "stated by a source".
- Unknown vendor labels for deal type, status or exclusivity reject the row; they are never guessed.
- A territory that cannot be parsed is ``None`` (unstated), never "worldwide".
"""

from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

# --- canonical vocabulary -------------------------------------------------------------------------------

LICENSE = "LICENSE"
OPTION = "OPTION"
OPTION_EXERCISED = "OPTION_EXERCISED"
OPTION_LAPSED = "OPTION_LAPSED"
CO_DEVELOPMENT = "CO_DEVELOPMENT"
ACQUISITION = "ACQUISITION"
TERMINATION = "TERMINATION"
RIGHTS_RETURNED = "RIGHTS_RETURNED"
AVAILABILITY_STATED = "AVAILABILITY_STATED"
EVENT_TYPES = frozenset({LICENSE, OPTION, OPTION_EXERCISED, OPTION_LAPSED, CO_DEVELOPMENT, ACQUISITION,
                         TERMINATION, RIGHTS_RETURNED, AVAILABILITY_STATED})
GRANTS = frozenset({LICENSE, OPTION, CO_DEVELOPMENT, ACQUISITION})
CLEARING = frozenset({TERMINATION, RIGHTS_RETURNED, OPTION_LAPSED})
STATUSES = frozenset({"ACTIVE", "TERMINATED", "EXPIRED", "COMPLETED", "UNKNOWN"})
EXCLUSIVITY = frozenset({"EXCLUSIVE", "NON_EXCLUSIVE", "UNSTATED"})

RIGHTS_FIELDS: tuple[str, ...] = (
    "deal_id", "external_id", "event_type", "exclusivity", "grantee", "grantor", "territory",
    "event_date", "status", "related_deal_id", "source_reference", "evidence_quote", "source_date",
)
REQUIRED_RIGHTS_FIELDS: tuple[str, ...] = ("deal_id", "external_id", "event_type", "source_reference")

# --- positions (what the evidence says for the buyer's territory) ---------------------------------------

P_CONFLICTING = "CONFLICTING_EVIDENCE"
P_ACQUIRED = "ACQUIRED_BY_THIRD_PARTY_PER_EVIDENCE"
P_LICENSED = "LICENSED_IN_TERRITORY_PER_EVIDENCE"
P_OPTION = "OPTION_HELD_IN_TERRITORY_PER_EVIDENCE"
P_SHARED = "RIGHTS_SHARED_IN_TERRITORY_PER_EVIDENCE"
P_UNSTATED = "GRANT_TERRITORY_UNSTATED"
P_AVAILABILITY = "AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED"
P_RETURNED = "RIGHTS_RETURNED_PER_EVIDENCE"
P_NOT_ENCUMBERED = "NOT_ENCUMBERED_IN_TERRITORY_PER_EVIDENCE"
P_NONE = "NO_RIGHTS_EVIDENCE"
ENCUMBRANCE_POSITIONS = frozenset({P_ACQUIRED, P_LICENSED, P_OPTION, P_SHARED})

# --- territory ------------------------------------------------------------------------------------------

REGIONS = frozenset({"US", "CA", "EU", "UK", "JP", "CN", "HK", "MO", "TW", "KR", "ROW"})
_REGION_TERMS: tuple[tuple[str, frozenset[str]], ...] = (  # longest phrases first
    (r"greater china", frozenset({"CN", "HK", "MO", "TW"})),
    (r"mainland china|china'?s mainland|china mainland|prc", frozenset({"CN"})),
    (r"china", frozenset({"CN"})),
    (r"hong kong", frozenset({"HK"})),
    (r"maca[ou]", frozenset({"MO"})),
    (r"taiwan", frozenset({"TW"})),
    (r"south korea|republic of korea|korea", frozenset({"KR"})),
    (r"japan", frozenset({"JP"})),
    (r"north america", frozenset({"US", "CA"})),
    (r"united states|u\.s\.a?\.?|usa|us", frozenset({"US"})),
    (r"canada", frozenset({"CA"})),
    (r"european union|europe|eea|eu", frozenset({"EU", "UK"})),
    (r"united kingdom|uk", frozenset({"UK"})),
)
_ALL = re.compile(r"\b(worldwide|world-wide|global(ly)?|all (global )?territories|rest of (the )?world)\b")
_EXCLUDE = re.compile(r"\b(outside|excluding|exclusive of|except|other than|ex-)")


def parse_territory(text: str | None) -> frozenset[str] | None:
    """Territory text -> covered regions, or None when it cannot be read.

    "worldwide outside of Greater China" -> all but CN/HK/MO/TW. "rest of world" needs an exclusion list
    to mean anything; on its own it is unstated."""
    if not text or not text.strip():
        return None
    low = " " + " ".join(text.casefold().replace("(", " ").replace(")", " ").split()) + " "
    mentioned: set[str] = set()
    rest = low
    for pattern, regions in _REGION_TERMS:
        rx = re.compile(rf"(?<![a-z]){pattern}(?![a-z])")
        if rx.search(rest):
            mentioned |= regions
            rest = rx.sub(" ", rest)
    excluding = bool(_EXCLUDE.search(low))
    if _ALL.search(low):
        if "rest of" in low and not mentioned:
            return None
        return frozenset(REGIONS - mentioned) if (excluding or "rest of" in low) else frozenset(REGIONS)
    if excluding:
        return frozenset(REGIONS - mentioned) if mentioned else None
    return frozenset(mentioned) if mentioned else None


# --- party names ------------------------------------------------------------------------------------------

_SUFFIX = re.compile(
    r"\b(inc|incorporated|ltd|limited|co|corp|corporation|llc|plc|gmbh|s\.?a|n\.?v|b\.?v|holdings?|group)\b\.?")


def party_key(name: str | None) -> str:
    """Comparable party name. Strips punctuation and generic corporate suffixes only; "Acme KGaA" and
    "Acme & Co" stay distinct (KGaA is kept; "& co" reduces to "acme &")."""
    if not name:
        return ""
    low = name.casefold().replace(",", " ")
    low = _SUFFIX.sub(" ", low)
    return " ".join(re.sub(r"[^\w&]+", " ", low).split())


# --- profile and import ---------------------------------------------------------------------------------


class RightsProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    source_system: str = Field(min_length=1)
    license_status: str
    allowed_use: str
    columns: dict[str, str]
    #: vendor label (casefolded) -> canonical event type / status / exclusivity
    event_type_map: dict[str, str]
    status_map: dict[str, str] = Field(default_factory=dict)
    exclusivity_map: dict[str, str] = Field(default_factory=dict)
    date_formats: list[str] = Field(default_factory=lambda: ["%Y-%m-%d", "%Y-%m", "%Y"])

    @model_validator(mode="after")
    def _check(self) -> RightsProfile:
        unknown = sorted(set(self.columns) - set(RIGHTS_FIELDS))
        if unknown:
            raise ValueError(f"rights profile maps unknown fields {unknown}")
        missing = [f for f in REQUIRED_RIGHTS_FIELDS if f not in self.columns]
        if missing:
            raise ValueError(f"rights profile must map {missing}")
        for label, mapping, allowed in (("event_type_map", self.event_type_map, EVENT_TYPES),
                                        ("status_map", self.status_map, STATUSES),
                                        ("exclusivity_map", self.exclusivity_map, EXCLUSIVITY)):
            bad = sorted(set(mapping.values()) - allowed)
            if bad:
                raise ValueError(f"{label} maps to unknown canonical values {bad}")
        return self

    @classmethod
    def from_yaml(cls, path: str | Path) -> RightsProfile:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise TypeError(f"{path}: a rights profile must be a YAML mapping")
        return cls(**data)


class RightsEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    deal_id: str
    external_id: str
    event_type: str
    exclusivity: str = "UNSTATED"
    grantee: str | None = None
    grantor: str | None = None
    territory_as_written: str | None = None
    territory: list[str] | None = None  # None = unstated / unreadable
    event_date: date | None = None
    status: str = "UNKNOWN"
    related_deal_id: str | None = None
    source_system: str
    dataset_version: str
    row_number: int
    source_reference: str
    evidence_quote: str | None = None
    source_date: date | None = None

    @property
    def effective_date(self) -> date | None:
        return self.event_date or self.source_date


class RightsImport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_version: str
    source_file: str
    source_sha256: str
    profile_name: str
    license_status: str
    allowed_use: str
    events: list[RightsEvent]
    rejected: list[dict[str, object]]


def _date(text: str, formats: list[str]) -> date | None:
    for fmt in formats:
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def import_rights(path: str | Path, profile: RightsProfile) -> RightsImport:
    path = Path(path)
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    version = f"{profile.source_system}:{sha[:12]}"
    events: list[RightsEvent] = []
    rejected: list[dict[str, object]] = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [h for h in profile.columns.values() if h not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: rights file lacks mapped headers {missing}")
        for n, row in enumerate(reader, start=1):
            f = {k: (row.get(h) or "").strip() for k, h in profile.columns.items()}
            reasons: list[str] = []
            for req in REQUIRED_RIGHTS_FIELDS:
                if not f.get(req):
                    reasons.append(f"missing {req}")
            etype = profile.event_type_map.get(f.get("event_type", "").casefold())
            if f.get("event_type") and etype is None:
                reasons.append(f"unknown deal type label {f['event_type']!r} (add it to the profile; not guessed)")
            status = "UNKNOWN"
            if f.get("status"):
                status = profile.status_map.get(f["status"].casefold()) or ""
                if not status:
                    reasons.append(f"unknown status label {f['status']!r}")
            excl = "UNSTATED"
            if f.get("exclusivity"):
                excl = profile.exclusivity_map.get(f["exclusivity"].casefold()) or ""
                if not excl:
                    reasons.append(f"unknown exclusivity label {f['exclusivity']!r}")
            dates = {}
            for key in ("event_date", "source_date"):
                dates[key] = _date(f[key], profile.date_formats) if f.get(key) else None
                if f.get(key) and dates[key] is None:
                    reasons.append(f"unreadable {key} {f[key]!r}")
            if etype in GRANTS | {AVAILABILITY_STATED} and not (f.get("grantee") or f.get("grantor")):
                reasons.append("a grant or availability statement must name a party")
            if reasons:
                rejected.append({"row_number": n, "reasons": reasons, "raw": dict(row)})
                continue
            regions = parse_territory(f.get("territory"))
            events.append(RightsEvent(
                event_id=f"rx:{sha[:8]}:{n}", deal_id=f["deal_id"], external_id=f["external_id"],
                event_type=etype or "", exclusivity=excl, grantee=f.get("grantee") or None,
                grantor=f.get("grantor") or None, territory_as_written=f.get("territory") or None,
                territory=sorted(regions) if regions is not None else None,
                event_date=dates["event_date"], status=status, related_deal_id=f.get("related_deal_id") or None,
                source_system=profile.source_system, dataset_version=version, row_number=n,
                source_reference=f["source_reference"], evidence_quote=f.get("evidence_quote") or None,
                source_date=dates["source_date"]))
    return RightsImport(dataset_version=version, source_file=path.name, source_sha256=sha,
                        profile_name=profile.name, license_status=profile.license_status,
                        allowed_use=profile.allowed_use, events=events, rejected=rejected)


# --- position ------------------------------------------------------------------------------------------


@dataclass
class RightsPosition:
    position: str
    holder: str | None = None
    event_ids: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    stale: bool = False
    evidence: list[dict[str, object]] = field(default_factory=list)


@dataclass
class _Grant:
    event: RightsEvent
    holder: str
    kind: str  # event type, OPTION may become LICENSE on exercise
    cleared_by: RightsEvent | None = None


def _cite(e: RightsEvent) -> dict[str, object]:
    return {"event_id": e.event_id, "deal_id": e.deal_id, "type": e.event_type, "grantee": e.grantee,
            "grantor": e.grantor, "territory": e.territory_as_written, "exclusivity": e.exclusivity,
            "date": (e.effective_date.isoformat() if e.effective_date else None), "status": e.status,
            "source": e.source_reference, "quote": e.evidence_quote, "row": e.row_number}


def _order(e: RightsEvent) -> tuple[int, date]:
    # Clearing events refer back to a grant, so an undated one sorts after every dated grant.
    d = e.effective_date
    if d is None:
        return (1 if e.event_type in CLEARING | {OPTION_EXERCISED} else 0, date.min)
    return (0, d)


def _successions(events: list[RightsEvent]) -> dict[str, str]:
    """Acquired party -> acquirer, for company acquisitions recorded in the file."""
    out: dict[str, str] = {}
    for e in events:
        if e.event_type == ACQUISITION and e.grantee and e.grantor:
            out[party_key(e.grantor)] = e.grantee
    return out


def rights_position(
    events: list[RightsEvent], *, territory: frozenset[str], originator: str | None,
    as_of: date | None, max_age_days: int,
) -> RightsPosition:
    if not events:
        return RightsPosition(P_NONE, reasons=["no rights or deal record for this program in the imported rights file"],
                              questions=[("Who holds rights in the buyer territory? No deal record was imported; "
                                         "the registry sponsor is not evidence of ownership.")])
    succession = _successions(events)

    def current(name: str | None) -> str:
        seen = set()
        while name and party_key(name) in succession and party_key(name) not in seen:
            seen.add(party_key(name))
            name = succession[party_key(name)]
        return name or ""

    grants: list[_Grant] = []
    unmatched_clears: list[RightsEvent] = []
    availability: list[RightsEvent] = []
    for e in sorted(events, key=_order):
        if e.event_type in GRANTS:
            if e.event_type == ACQUISITION and party_key(e.grantor) != party_key(originator) and any(
                    party_key(g.holder) == party_key(e.grantor) for g in grants):
                continue  # acquirer of a licensee: handled by succession, not a new grant
            g = _Grant(e, e.grantee or e.grantor or "", e.event_type)
            if e.status in {"TERMINATED", "EXPIRED"}:
                g.cleared_by = e
            grants.append(g)
        elif e.event_type == AVAILABILITY_STATED:
            availability.append(e)
        elif e.event_type in CLEARING | {OPTION_EXERCISED}:
            party = party_key(current(e.grantee or e.grantor))
            targets = [g for g in grants if g.cleared_by is None and (
                (e.related_deal_id and g.event.deal_id == e.related_deal_id)
                or (not e.related_deal_id and party and party_key(current(g.holder)) == party))]
            if e.event_type == OPTION_EXERCISED:
                targets = [g for g in targets if g.kind == OPTION]
                for g in targets:
                    g.kind = LICENSE
            elif e.event_type == OPTION_LAPSED:
                for g in (t for t in targets if t.kind == OPTION):
                    g.cleared_by = e
            else:
                for g in targets:
                    g.cleared_by = e
            if not targets:
                unmatched_clears.append(e)

    def covers(g: _Grant) -> bool | None:
        if g.event.territory is None:
            return None if g.kind != ACQUISITION else True  # a company acquisition transfers everything held
        return bool(set(g.event.territory) & territory)

    active = [g for g in grants if g.cleared_by is None]
    in_terr = [g for g in active if covers(g)]
    unstated = [g for g in active if covers(g) is None]
    cleared_in_terr = [g for g in grants if g.cleared_by is not None and covers(g) is not False]
    used: list[RightsEvent] = []
    pos = RightsPosition(P_NONE)

    exclusive_holders = {party_key(current(g.holder)) for g in in_terr
                         if g.kind in {LICENSE, ACQUISITION} and g.event.exclusivity != "NON_EXCLUSIVE"}
    terr = "/".join(sorted(territory))
    if len(exclusive_holders) > 1:
        pos = RightsPosition(P_CONFLICTING, reasons=[
            f"more than one active grant covering {terr} to different parties: "
            + "; ".join(sorted({current(g.holder) for g in in_terr}))])
        used = [g.event for g in in_terr]
        pos.questions.append(f"Which grant over {terr} is in force? Two or more parties are recorded as holding it.")
    elif in_terr and availability:
        pos = RightsPosition(P_CONFLICTING, reasons=[("a source states availability while an active grant covers "
                                                     f"{terr}")])
        used = [g.event for g in in_terr] + availability
        pos.questions.append("Has the recorded grant ended? A source also says the program is available.")
    elif in_terr:
        rank = {ACQUISITION: 0, LICENSE: 1, OPTION: 2, CO_DEVELOPMENT: 3}
        g = min(in_terr, key=lambda g: rank[g.kind])
        holder = current(g.holder)
        position = {ACQUISITION: P_ACQUIRED, LICENSE: P_LICENSED, OPTION: P_OPTION, CO_DEVELOPMENT: P_SHARED}[g.kind]
        if g.kind == ACQUISITION and party_key(holder) == party_key(originator):
            position = P_NOT_ENCUMBERED  # the program's own company; nothing held by a third party
        pos = RightsPosition(position, holder=holder)
        used = [x.event for x in in_terr]
        where = g.event.territory_as_written or "territory not stated (company acquisition)"
        pos.reasons.append(f"{g.kind.lower().replace('_', '-')} to {holder} covering {terr} ({where})")
        if holder != g.holder:
            pos.reasons.append(f"{g.holder} was acquired by {holder} per a recorded acquisition")
        if g.kind == OPTION:
            pos.questions.append(f"Has {holder} exercised, declined or let lapse its option ({where})? "
                                 "No outcome is recorded.")
        elif g.kind == LICENSE and g.event.exclusivity == "UNSTATED":
            pos.questions.append(f"Is the license to {holder} exclusive? The source does not say.")
        elif g.kind == CO_DEVELOPMENT:
            pos.questions.append(f"Would any transaction need the consent of {holder}? Rights are shared.")
        if position in ENCUMBRANCE_POSITIONS:
            pos.questions.append(f"Is {holder}'s grant over {terr} still in force, and would {holder} "
                                 "sublicense or transfer it?")
    elif unstated:
        pos = RightsPosition(P_UNSTATED, holder=current(unstated[0].holder))
        used = [g.event for g in unstated]
        pos.reasons.append(f"active {unstated[0].kind.lower()} to {pos.holder} with territory not stated or "
                           "not readable; it may cover the buyer territory")
        pos.questions.append(f"Which territories does the grant to {pos.holder} cover?")
    elif availability:
        pos = RightsPosition(P_AVAILABILITY, holder=availability[-1].grantor or availability[-1].grantee)
        used = availability
        pos.reasons.append("a source states the program is available or a partner is sought (unverified)")
        pos.questions.append("Confirm with the owner that rights in the buyer territory are unencumbered and "
                             "available, and on what terms.")
    elif cleared_in_terr:
        pos = RightsPosition(P_RETURNED, holder=originator)
        used = [g.event for g in cleared_in_terr] + [g.cleared_by for g in cleared_in_terr if g.cleared_by]
        for g in cleared_in_terr:
            pos.reasons.append(f"grant to {current(g.holder)} ended per source; not a statement of availability")
        pos.questions.append("Who holds the returned rights now, and have they been re-licensed since?")
    elif grants:
        pos = RightsPosition(P_NOT_ENCUMBERED, holder=None)
        used = [g.event for g in grants]
        pos.reasons.append(f"recorded grants do not cover {terr}; this is not a statement of availability")
        pos.questions.append(f"Who holds {terr} rights? Recorded deals cover other territories only.")
    else:
        pos = RightsPosition(P_NONE, reasons=["no grant recorded"], questions=["Who holds rights?"])
        used = []

    for e in unmatched_clears:
        if pos.position in ENCUMBRANCE_POSITIONS | {P_UNSTATED}:
            pos.position = P_CONFLICTING
            pos.reasons.append(f"a {e.event_type.lower()} naming {e.grantee or e.grantor} is recorded, but it "
                               "matches no recorded grant holder")
            pos.questions.append(f"Is {e.grantee or e.grantor} the successor of {pos.holder}? If so, the grant "
                                 "has ended; record the acquisition or link the deal id.")
        else:
            pos.reasons.append(f"a {e.event_type.lower()} naming {e.grantee or e.grantor} matches no recorded grant")
        used.append(e)

    dated = [e.effective_date for e in used if e.effective_date]
    if as_of and dated and (as_of - max(dated)).days > max_age_days:
        pos.stale = True
        pos.reasons.append(f"latest supporting evidence is dated {max(dated).isoformat()}, older than "
                           f"{max_age_days} days before {as_of.isoformat()}")
        pos.questions.append("Is this rights evidence still current?")
        if pos.position == P_AVAILABILITY:
            pos.position = P_NONE
            pos.reasons.append("a stale availability statement is not counted")
    pos.event_ids = list(dict.fromkeys(e.event_id for e in used))
    pos.evidence = [_cite(e) for e in {e.event_id: e for e in used}.values()]
    return pos


__all__ = [
    "ENCUMBRANCE_POSITIONS", "EVENT_TYPES", "P_ACQUIRED", "P_AVAILABILITY", "P_CONFLICTING", "P_LICENSED",
    "P_NONE", "P_NOT_ENCUMBERED", "P_OPTION", "P_RETURNED", "P_SHARED", "P_UNSTATED", "REGIONS",
    "RightsEvent", "RightsImport", "RightsPosition", "RightsProfile", "import_rights", "parse_territory",
    "party_key", "rights_position",
]
