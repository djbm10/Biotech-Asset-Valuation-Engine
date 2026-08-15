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
        # CT.gov ORs whitespace-separated terms within a query field, so the expanded
        # alias list becomes one intervention query rather than N round trips.
        kwargs: dict[str, Any] = {"page_size": min(self.page_size, query.max_records)}
        if query.terms:
            kwargs["intervention"] = " ".join(query.terms)
        if query.conditions:
            kwargs["condition"] = " ".join(query.conditions)
        if query.sponsors:
            kwargs["sponsor"] = " ".join(query.sponsors)
        if query.statuses:
            kwargs["status_filter"] = list(query.statuses)

        try:
            protocols = self.search_fn(**kwargs)
        except Exception as exc:  # upstream failure must not look like an empty universe
            return self._failure(str(exc))

        records: list[TrialRecord] = []
        truncated = False
        for protocol in protocols:
            if len(records) >= query.max_records:
                truncated = True
                break
            record = normalize_study(protocol)
            if record is None:
                continue
            record = record.model_copy(
                update={
                    "snapshot": write_snapshot(
                        protocol, backend=self.backend_name, snapshot_root=self.snapshot_root
                    )
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
