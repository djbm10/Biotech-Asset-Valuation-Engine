"""ClinicalTrials.gov REST v2 backend for the trial universe interface.

This is the default backend: it needs no local infrastructure, so a fresh clone can run
broad discovery immediately. AACT (:mod:`bve.se.universe.aact`) trades that convenience
for bulk throughput and serves the identical :class:`TrialRecord`.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from bve.se.schemas.contracts import SearchOutcome
from bve.se.universe.provider import (
    CLINICALTRIALS_GOV,
    PayloadKind,
    TrialIntervention,
    TrialQuery,
    TrialRecord,
    TrialUniverseResult,
    normalize_phases,
    normalize_token,
    parse_registry_date,
    write_snapshot,
)

BACKEND_NAME = "ctgov_rest"
BACKEND_VERSION = "v2"


TrialSearch = Callable[..., list[dict[str, Any]]]


def _text(module: dict[str, Any], key: str) -> str | None:
    value = module.get(key)
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def _struct_date(module: dict[str, Any], key: str) -> Any:
    value = module.get(key)
    if isinstance(value, dict):
        return value.get("date")
    return value


def normalize_study(protocol: dict[str, Any]) -> TrialRecord | None:
    """Translate one CT.gov ``protocolSection`` into a backend-neutral record.

    Returns ``None`` for a payload with no NCT id — an unidentifiable trial cannot be
    deduplicated or cited, so it is dropped rather than given a synthetic id.
    """

    identification = protocol.get("identificationModule", {}) or {}
    nct_id = _text(identification, "nctId")
    if not nct_id:
        return None

    description = protocol.get("descriptionModule", {}) or {}
    status = protocol.get("statusModule", {}) or {}
    design = protocol.get("designModule", {}) or {}
    conditions_module = protocol.get("conditionsModule", {}) or {}
    sponsors = protocol.get("sponsorCollaboratorsModule", {}) or {}
    arms = protocol.get("armsInterventionsModule", {}) or {}

    interventions: list[TrialIntervention] = []
    for raw in arms.get("interventions", []) or []:
        name = str(raw.get("name", "")).strip()
        if not name:
            continue
        other_names = raw.get("otherNames") or []
        if not isinstance(other_names, list):
            other_names = [str(other_names)]
        interventions.append(
            TrialIntervention(
                name=name,
                intervention_type=normalize_token(raw.get("type")),
                description=_text(raw, "description"),
                other_names=[str(item).strip() for item in other_names if str(item).strip()],
            )
        )

    enrollment_info = design.get("enrollmentInfo", {}) or {}
    enrollment = enrollment_info.get("count")

    return TrialRecord(
        trial_id=nct_id,
        registry=CLINICALTRIALS_GOV,
        url=f"https://clinicaltrials.gov/study/{nct_id}",
        brief_title=_text(identification, "briefTitle"),
        official_title=_text(identification, "officialTitle"),
        brief_summary=_text(description, "briefSummary"),
        detailed_description=_text(description, "detailedDescription"),
        conditions=[str(item).strip() for item in conditions_module.get("conditions", []) or [] if str(item).strip()],
        phases=normalize_phases(design.get("phases")),
        overall_status=normalize_token(status.get("overallStatus")),
        study_type=normalize_token(design.get("studyType")),
        enrollment=int(enrollment) if isinstance(enrollment, (int, float, str)) and str(enrollment).isdigit() else None,
        lead_sponsor=_text(sponsors.get("leadSponsor", {}) or {}, "name"),
        collaborators=[
            str((item or {}).get("name", "")).strip()
            for item in sponsors.get("collaborators", []) or []
            if str((item or {}).get("name", "")).strip()
        ],
        interventions=interventions,
        start_date=parse_registry_date(_struct_date(status, "startDateStruct")),
        primary_completion_date=parse_registry_date(_struct_date(status, "primaryCompletionDateStruct")),
        completion_date=parse_registry_date(_struct_date(status, "completionDateStruct")),
        last_update_date=parse_registry_date(_struct_date(status, "lastUpdatePostDateStruct")),
    )


def _quote(term: str) -> str:
    """Render one term as a single Essie literal.

    Embedded quotes are stripped rather than escaped: Essie has no escape sequence, so a
    term containing one would otherwise close the literal early and let the remainder --
    including a bare OR -- be read as query syntax.
    """

    return '"' + term.replace('"', " ").strip() + '"'


def build_intervention_expression(facets: list[list[str]]) -> str:
    """Render AND-ed facets of OR-ed aliases as an Essie expression.

    Explicit operators, not whitespace. Whitespace between bare terms means AND to Essie,
    so an alias list joined by spaces asks for trials matching every spelling at once --
    which is why the pure-target batch of the PDCD1 sweep returned zero studies. Explicit
    quoting also lifts the word ceiling that prompted the old batching: the parser rejects
    long runs of bare words, but accepts the same aliases as quoted literals.
    """

    groups = [
        "(" + " OR ".join(_quote(t) for t in facet) + ")"
        for facet in facets
        if facet
    ]
    return " AND ".join(groups)


class ClinicalTrialsGovProvider:
    """Fetch trials from the CT.gov REST v2 API.

    ``search_fn`` is injectable so tests and replays never touch the network; the default
    is the existing :func:`bve.ingestion.clinicaltrials_gov.search_studies` client rather
    than a second HTTP implementation.
    """

    backend_name = BACKEND_NAME

    def __init__(
        self,
        search_fn: TrialSearch | None = None,
        *,
        page_size: int = 250,
        snapshot_root: Path | None = None,
    ) -> None:
        if search_fn is None:
            from bve.ingestion.clinicaltrials_gov import search_studies

            search_fn = search_studies
        self.search_fn = search_fn
        self.page_size = page_size
        self.snapshot_root = snapshot_root

    def fetch(self, query: TrialQuery) -> TrialUniverseResult:
        # One request carrying the query's own boolean structure. The earlier version
        # split terms by word count and unioned the responses, which is how a PDCD1
        # sweep came back with 11,144 trials whose only match was the word "vaccine".
        base: dict[str, Any] = {
            # Transport paging and the caller's record bound are separate settings: a
            # page size must never become a silent ceiling on the universe.
            "page_size": self.page_size,
            # One past the bound: the extra record is what makes truncation detectable
            # rather than inferred from an exact-size coincidence.
            "max_records": None if query.max_records is None else query.max_records + 1,
        }
        if query.conditions:
            base["condition"] = " ".join(query.conditions)
        if query.sponsors:
            base["sponsor"] = " ".join(query.sponsors)
        if query.statuses:
            base["status_filter"] = list(query.statuses)

        expression = build_intervention_expression(query.facets())
        if expression:
            base["intervention"] = expression
        try:
            protocols = list(self.search_fn(**base))
        except Exception as exc:  # a partial universe must not look like a complete one
            return self._failure(str(exc))

        records: list[TrialRecord] = []
        seen: set[str] = set()
        truncated = False
        for protocol in protocols:
            if query.max_records is not None and len(records) >= query.max_records:
                truncated = True
                break
            record = normalize_study(protocol)
            if record is None:
                continue
            # CT.gov can still repeat a study across pages.
            if record.trial_id in seen:
                continue
            seen.add(record.trial_id)
            record = record.model_copy(
                update={
                    "snapshot": write_snapshot(
                        protocol,
                        backend=self.backend_name,
                        snapshot_root=self.snapshot_root,
                        payload_kind=PayloadKind.CTGOV_PROTOCOL_JSON,
                    ),
                    # Preserved verbatim so the existing CT.gov extractor can read it
                    # without a second fetch. Acquisition has moved here; interpretation
                    # has not, and the payload kind says which parser is entitled to it.
                    "raw_payload": protocol,
                }
            )
            if not query.applies(record):
                continue
            records.append(record)

        return TrialUniverseResult(
            records=records,
            outcome=SearchOutcome.SUCCESS if records else SearchOutcome.NO_EVIDENCE_FOUND,
            backend=self.backend_name,
            backend_version=BACKEND_VERSION,
            truncated=truncated,
        )

    def _failure(self, error: str) -> TrialUniverseResult:
        return TrialUniverseResult(
            outcome=SearchOutcome.FAILED,
            backend=self.backend_name,
            backend_version=BACKEND_VERSION,
            error=error,
        )
