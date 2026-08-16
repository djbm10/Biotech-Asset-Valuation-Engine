"""Source-agnostic trial universe interface (M9B).

The rest of the S&E pipeline must not be able to tell whether a trial arrived from the
ClinicalTrials.gov REST API, an AACT mirror, or a frozen CI fixture. Everything below the
:class:`TrialUniverseProvider` boundary speaks a backend-specific dialect; everything above
it speaks :class:`TrialRecord`.

Providers own *acquisition* — build the query, page, snapshot, record provenance — and
nothing else. Interpreting a record is a separate concern with its own abstraction to
come; keeping the two apart is what lets a new backend be added without a second S&E
pipeline growing beside the first.

Three rules keep that boundary honest:

* A raw upstream payload travels upward only inside a content-addressed, kind-tagged
  envelope. It is opaque: the only code entitled to read it is an extractor that matches
  its :class:`PayloadKind`. Anything else reaching into ``raw_payload`` for a backend's
  field names has reintroduced the coupling this boundary exists to prevent.
* Every record carries enough normalized metadata to be discovered, deduplicated and
  cited without opening the envelope at all.
* ``TrialUniverseResult.backend`` exists for provenance only — it belongs in the run
  manifest, never in an ``if``.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import Field, field_validator

from bve.se.schemas.contracts import SearchOutcome, StrictModel

#: Registry the record originated from. Distinct from the *backend* that served it: AACT
#: and the CT.gov REST API are two backends over the one ``clinicaltrials_gov`` registry.
CLINICALTRIALS_GOV = "clinicaltrials_gov"


class PayloadKind(str, Enum):
    """The shape of a preserved raw payload, so an extractor can refuse what it cannot read.

    AACT serves relational rows, not CT.gov's nested ``protocolSection`` JSON, so the two
    backends cannot share one parser even though they serve one registry. Tagging the
    shape lets downstream dispatch explicitly instead of guessing from ``backend`` — and
    lets a parser fail loudly when handed a payload it was not written for.
    """

    CTGOV_PROTOCOL_JSON = "CTGOV_PROTOCOL_JSON"
    AACT_RELATIONAL_RECORD = "AACT_RELATIONAL_RECORD"


def parse_registry_date(value: Any) -> date | None:
    """Parse the partial dates registries publish (``2024``, ``2024-05``, ``2024-05-01``).

    Missing precision resolves to the first of the period rather than raising: a trial
    that reports only ``2024-05`` still has to sort against as-of cutoffs.
    """

    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    match = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", text)
    if not match:
        return None
    year, month, day = match.group(1), match.group(2) or "01", match.group(3) or "01"
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def normalize_token(value: Any) -> str | None:
    """Fold a registry vocabulary term to one spelling (``Recruiting`` → ``RECRUITING``).

    The REST API publishes screaming snake case and AACT publishes title case for the
    same controlled vocabularies. Without this, a downstream status or study-type filter
    would silently return different trials depending on the backend.
    """

    if value is None:
        return None
    text = re.sub(r"[^A-Za-z0-9]+", "_", str(value).strip()).strip("_").upper()
    return text or None


def normalize_phases(value: Any) -> list[str]:
    """Fold either backend's phase spelling into canonical tokens.

    REST gives ``["PHASE1", "PHASE2"]``; AACT gives the single string
    ``"Phase 1/Phase 2"``. Both must become ``["PHASE1", "PHASE2"]`` so a phase filter is
    backend-independent.
    """

    if value is None:
        return []
    raw = value if isinstance(value, (list, tuple)) else re.split(r"[/,]", str(value))
    phases: list[str] = []
    for item in raw:
        token = normalize_token(item)
        if not token:
            continue
        token = token.replace("EARLY_PHASE_", "EARLY_PHASE").replace("PHASE_", "PHASE")
        if token in {"NA", "N_A", "NOT_APPLICABLE"}:
            token = "NA"
        if token not in phases:
            phases.append(token)
    return phases


def payload_digest(payload: Any) -> str:
    """Stable digest over a raw upstream payload, independent of key ordering."""

    serialized = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode()).hexdigest()


class TrialSnapshot(StrictModel):
    """Immutable reference to the raw upstream payload a record was derived from."""

    content_hash: str
    snapshot_path: str | None = None
    #: Backend that produced the payload. Recorded so a stored snapshot can be re-parsed
    #: years later by the same reader that wrote it.
    backend: str
    #: Shape of the payload, which is what decides who may parse it. ``backend`` does not:
    #: two backends can serve one shape, and one backend could later serve two.
    payload_kind: PayloadKind = PayloadKind.CTGOV_PROTOCOL_JSON

    @property
    def snapshot_id(self) -> str:
        return f"snapshot:{self.content_hash}"


class TrialIntervention(StrictModel):
    name: str
    intervention_type: str | None = None
    description: str | None = None
    other_names: list[str] = Field(default_factory=list)

    def searchable_text(self) -> str:
        return " ".join(
            part
            for part in (self.name, self.intervention_type, self.description, *self.other_names)
            if part
        )


class TrialRecord(StrictModel):
    """One trial, normalized away from whichever backend supplied it."""

    trial_id: str
    registry: str = CLINICALTRIALS_GOV
    url: str | None = None

    brief_title: str | None = None
    official_title: str | None = None
    brief_summary: str | None = None
    detailed_description: str | None = None

    conditions: list[str] = Field(default_factory=list)
    phases: list[str] = Field(default_factory=list)
    overall_status: str | None = None
    study_type: str | None = None
    enrollment: int | None = None

    lead_sponsor: str | None = None
    collaborators: list[str] = Field(default_factory=list)
    interventions: list[TrialIntervention] = Field(default_factory=list)

    start_date: date | None = None
    primary_completion_date: date | None = None
    completion_date: date | None = None
    last_update_date: date | None = None

    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    snapshot: TrialSnapshot | None = None

    #: The preserved upstream payload, opaque above this boundary. Only an extractor that
    #: matches ``snapshot.payload_kind`` may read it; discovery works off the normalized
    #: fields above. Kept in-process so existing source-specific extraction can run
    #: without a second fetch, while acquisition has already moved behind the provider.
    raw_payload: Any | None = None

    @field_validator("trial_id")
    @classmethod
    def require_trial_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("trial_id must not be blank")
        return stripped

    def searchable_text(self) -> str:
        """Every free-text field a term match should see, in one string.

        Downstream matching uses this instead of re-serializing a backend payload, which
        is what previously made term matching depend on CT.gov's JSON shape.
        """

        parts: list[str] = [
            self.trial_id,
            self.brief_title or "",
            self.official_title or "",
            self.brief_summary or "",
            self.detailed_description or "",
            self.lead_sponsor or "",
            *self.collaborators,
            *self.conditions,
            *(intervention.searchable_text() for intervention in self.interventions),
        ]
        return "\n".join(part for part in parts if part)


class TrialQuery(StrictModel):
    """A backend-neutral request for trials.

    ``terms`` is expected to be already alias-expanded by the ontology layer; providers
    do not perform biomedical reasoning, they translate.
    """

    terms: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    sponsors: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)
    #: Records last updated after this date are dropped, so a replay cannot see the future.
    as_of_date: date | None = None
    max_records: int = Field(default=1000, gt=0)

    def applies(self, record: TrialRecord) -> bool:
        """Cutoff check shared by every backend so no-lookahead does not depend on SQL."""

        if self.as_of_date is None:
            return True
        observed = record.last_update_date or record.start_date
        return observed is None or observed <= self.as_of_date


class TrialUniverseResult(StrictModel):
    """Provider response. ``backend``/``backend_version`` are provenance, not control flow."""

    records: list[TrialRecord] = Field(default_factory=list)
    outcome: SearchOutcome = SearchOutcome.SUCCESS
    backend: str
    backend_version: str | None = None
    error: str | None = None
    #: True when ``max_records`` cut the result short, so a caller can report an
    #: incomplete universe instead of silently claiming coverage.
    truncated: bool = False

    @property
    def snapshot_ids(self) -> list[str]:
        return list(
            dict.fromkeys(
                record.snapshot.snapshot_id for record in self.records if record.snapshot
            )
        )

    def provenance(self) -> str:
        """Manifest token, e.g. ``ctgov_rest_v2`` or ``aact__2026-07-30``."""

        return (
            f"{self.backend}__{self.backend_version}" if self.backend_version else self.backend
        )


@runtime_checkable
class TrialUniverseProvider(Protocol):
    """Fetch trials for a query. Implementations must not raise for upstream failures.

    A failed backend returns ``SearchOutcome.FAILED`` with ``error`` set. Swallowing the
    failure as an empty success would let a network blip masquerade as "no such trials".
    """

    backend_name: str

    def fetch(self, query: TrialQuery) -> TrialUniverseResult: ...


def write_snapshot(
    payload: Any,
    *,
    backend: str,
    snapshot_root: Path | None,
    payload_kind: PayloadKind = PayloadKind.CTGOV_PROTOCOL_JSON,
) -> TrialSnapshot:
    """Persist a raw upstream payload and return its reference.

    With no ``snapshot_root`` the digest is still computed, so evidence identity is
    stable whether or not this run chose to keep the bytes.
    """

    content = json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n"
    digest = hashlib.sha256(content.encode()).hexdigest()
    path_value: str | None = None
    if snapshot_root is not None:
        snapshot_root.mkdir(parents=True, exist_ok=True)
        path = snapshot_root / f"{digest}.json"
        if not path.exists():
            path.write_text(content)
        path_value = str(path)
    return TrialSnapshot(
        content_hash=digest,
        snapshot_path=path_value,
        backend=backend,
        payload_kind=payload_kind,
    )
