"""Rights evidence: vocabulary and import of a deals/rights export (cycle R1).

Vendor deal databases are exported separately from pipeline databases. This module reads such an export
through a YAML profile and keeps every event's provenance (file hash, row, URL, verbatim quote, date).
``rights_position`` derives what the evidence says for one buyer territory; ``rights_territory`` reads
territory text and party names.

Rules:

- Nothing is inferred from an empty field, a trial sponsor, an FDA labeler or a collaborator list. Only
  rows in the rights file are evidence.
- Absence of a known grant is never availability. Availability is only ever "stated by a source".
- Unknown vendor labels for deal type, status or exclusivity reject the row; they are never guessed.
- A territory that cannot be parsed is ``None`` (unstated), never "worldwide".
- A date keeps its precision: "2024" is a year, not 1 January 2024.
"""

from __future__ import annotations

import calendar
import csv
import hashlib
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from bve.dealscreen.rights_territory import parse_territory, party_key

# --- canonical vocabulary -------------------------------------------------------------------------------

LICENSE = "LICENSE"
OPTION = "OPTION"
OPTION_EXERCISED = "OPTION_EXERCISED"
OPTION_LAPSED = "OPTION_LAPSED"
CO_DEVELOPMENT = "CO_DEVELOPMENT"
#: An option to co-promote (share commercialisation), not an option over the rights themselves.
CO_PROMOTION_OPTION = "CO_PROMOTION_OPTION"
ACQUISITION = "ACQUISITION"
TERMINATION = "TERMINATION"
RIGHTS_RETURNED = "RIGHTS_RETURNED"
AVAILABILITY_STATED = "AVAILABILITY_STATED"
EVENT_TYPES = frozenset({LICENSE, OPTION, OPTION_EXERCISED, OPTION_LAPSED, CO_DEVELOPMENT, CO_PROMOTION_OPTION,
                         ACQUISITION, TERMINATION, RIGHTS_RETURNED, AVAILABILITY_STATED})
#: How each event type reads in reasons and evidence lines.
EVENT_WORDS = {
    LICENSE: "license", OPTION: "option", OPTION_EXERCISED: "option exercise", OPTION_LAPSED: "option lapse",
    CO_DEVELOPMENT: "co-development", CO_PROMOTION_OPTION: "co-promotion option", ACQUISITION: "acquisition",
    TERMINATION: "termination", RIGHTS_RETURNED: "rights return", AVAILABILITY_STATED: "availability statement",
}
#: Event types that must name at least one party.
NAMED_PARTY_TYPES = frozenset({LICENSE, OPTION, CO_DEVELOPMENT, CO_PROMOTION_OPTION, ACQUISITION,
                               AVAILABILITY_STATED})
STATUSES = frozenset({"ACTIVE", "TERMINATED", "EXPIRED", "COMPLETED", "UNKNOWN"})
EXCLUSIVITY = frozenset({"EXCLUSIVE", "NON_EXCLUSIVE", "UNSTATED"})

RIGHTS_FIELDS: tuple[str, ...] = (
    "deal_id", "external_id", "event_type", "exclusivity", "grantee", "grantor", "territory",
    "event_date", "status", "related_deal_id", "source_reference", "evidence_quote", "source_date",
)
REQUIRED_RIGHTS_FIELDS: tuple[str, ...] = ("deal_id", "external_id", "event_type", "source_reference")

# --- dates ----------------------------------------------------------------------------------------------

Precision = Literal["day", "month", "year"]
DEFAULT_DATE_FORMATS: tuple[str, ...] = ("%Y-%m-%d", "%Y-%m", "%Y")


def _precision(fmt: str) -> Precision:
    if "%d" in fmt or "%j" in fmt:
        return "day"
    if "%m" in fmt or "%b" in fmt or "%B" in fmt:
        return "month"
    return "year"


def parse_date(text: str, formats: list[str] | tuple[str, ...] = DEFAULT_DATE_FORMATS) -> tuple[date, Precision] | None:
    """A date and the precision it was written with ("2024" is a year, not 1 January 2024)."""
    for fmt in formats:
        try:
            return datetime.strptime(text.strip(), fmt).date(), _precision(fmt)
        except ValueError:
            continue
    return None


def period_end(d: date, precision: Precision) -> date:
    if precision == "year":
        return date(d.year, 12, 31)
    if precision == "month":
        return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])
    return d


def date_text(d: date | None, precision: Precision) -> str | None:
    if d is None:
        return None
    return {"year": f"{d.year}", "month": f"{d.year}-{d.month:02d}"}.get(precision, d.isoformat())


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
    date_formats: list[str] = Field(default_factory=lambda: list(DEFAULT_DATE_FORMATS))

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
    event_date: date | None = None  # first day of the stated day, month or year
    event_date_precision: Precision = "day"
    status: str = "UNKNOWN"
    related_deal_id: str | None = None
    source_system: str
    dataset_version: str
    row_number: int
    source_reference: str
    evidence_quote: str | None = None
    source_date: date | None = None
    source_date_precision: Precision = "day"

    @property
    def window(self) -> tuple[date, date] | None:
        """When the event happened, as far as the record says: the stated event date's period, else the source
        date's period (an event is taken to happen when it is first reported), else None (undated)."""
        if self.event_date:
            return self.event_date, period_end(self.event_date, self.event_date_precision)
        if self.source_date:
            return self.source_date, period_end(self.source_date, self.source_date_precision)
        return None

    @property
    def evidence_date(self) -> date | None:
        """When the evidence was stated, for staleness: the source date, else the event date."""
        return self.source_date or self.event_date

    @property
    def evidence_date_text(self) -> str | None:
        return self.source_date_text or self.event_date_text

    @property
    def event_date_text(self) -> str | None:
        return date_text(self.event_date, self.event_date_precision)

    @property
    def source_date_text(self) -> str | None:
        return date_text(self.source_date, self.source_date_precision)

    @property
    def when(self) -> str:
        """The event date as written, else when it was reported, else "undated"."""
        if self.event_date:
            return self.event_date_text or ""
        return f"reported {self.source_date_text}" if self.source_date else "undated"

    @property
    def words(self) -> str:
        return EVENT_WORDS.get(self.event_type, self.event_type.lower())


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


def _day(parsed: tuple[date, Precision] | None) -> date | None:
    return parsed[0] if parsed else None


def _prec(parsed: tuple[date, Precision] | None) -> Precision:
    return parsed[1] if parsed else "day"


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
            dates: dict[str, tuple[date, Precision] | None] = {}
            for key in ("event_date", "source_date"):
                dates[key] = parse_date(f[key], profile.date_formats) if f.get(key) else None
                if f.get(key) and dates[key] is None:
                    reasons.append(f"unreadable {key} {f[key]!r}")
            if etype in NAMED_PARTY_TYPES and not (f.get("grantee") or f.get("grantor")):
                reasons.append("a grant or availability statement must name a party")
            if reasons:
                # the mapped fields as written, so outputs can say what a rejected row named (review R1v4 O-9)
                rejected.append({"row_number": n, "external_id": f.get("external_id") or None, "reasons": reasons,
                                 "type_as_written": f.get("event_type") or None, "grantee": f.get("grantee") or None,
                                 "grantor": f.get("grantor") or None, "territory": f.get("territory") or None,
                                 "event_date": f.get("event_date") or None, "raw": dict(row)})
                continue
            regions = parse_territory(f.get("territory"))
            events.append(RightsEvent(
                event_id=f"rx:{sha[:8]}:{n}", deal_id=f["deal_id"], external_id=f["external_id"],
                event_type=etype or "", exclusivity=excl, grantee=f.get("grantee") or None,
                grantor=f.get("grantor") or None, territory_as_written=f.get("territory") or None,
                territory=sorted(regions) if regions is not None else None,
                event_date=_day(dates["event_date"]), event_date_precision=_prec(dates["event_date"]),
                status=status, related_deal_id=f.get("related_deal_id") or None,
                source_system=profile.source_system, dataset_version=version, row_number=n,
                source_reference=f["source_reference"], evidence_quote=f.get("evidence_quote") or None,
                source_date=_day(dates["source_date"]), source_date_precision=_prec(dates["source_date"])))
    return RightsImport(dataset_version=version, source_file=path.name, source_sha256=sha,
                        profile_name=profile.name, license_status=profile.license_status,
                        allowed_use=profile.allowed_use, events=events, rejected=rejected)


__all__ = [
    "ACQUISITION", "AVAILABILITY_STATED", "CO_DEVELOPMENT", "CO_PROMOTION_OPTION", "EVENT_TYPES", "EVENT_WORDS",
    "LICENSE", "OPTION", "OPTION_EXERCISED", "OPTION_LAPSED", "RIGHTS_RETURNED", "TERMINATION", "RightsEvent",
    "RightsImport", "RightsProfile", "date_text", "import_rights", "parse_date", "parse_territory", "party_key",
    "period_end",
]
