"""AACT (CTTI) backend for the trial universe interface.

AACT is a daily relational mirror of ClinicalTrials.gov. It serves the same registry as
the REST backend but supports whole-universe sweeps that the API rate-limits, so it is the
backend for broad discovery once a workstation has a local mirror.

The connection is injectable and psycopg is imported lazily: a clone without a database
gets a ``FAILED`` result naming the missing dependency, never an import error at startup
and never a silently empty universe.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
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
    payload_digest,
    write_snapshot,
)

BACKEND_NAME = "aact"
DSN_ENV_VAR = "BVE_AACT_DSN"

#: One row per (study, intervention). Interventions are regrouped in Python rather than
#: aggregated in SQL so the query stays portable across AACT snapshot vintages.
STUDY_SQL = """
SELECT s.nct_id,
       i.id AS intervention_id,
       s.brief_title,
       s.official_title,
       s.overall_status,
       s.study_type,
       s.phase,
       s.enrollment,
       s.start_date,
       s.primary_completion_date,
       s.completion_date,
       s.last_update_posted_date,
       bs.description AS brief_summary,
       dd.description AS detailed_description,
       sp.name AS lead_sponsor,
       i.name AS intervention_name,
       i.intervention_type,
       i.description AS intervention_description
FROM studies s
LEFT JOIN brief_summaries bs ON bs.nct_id = s.nct_id
LEFT JOIN detailed_descriptions dd ON dd.nct_id = s.nct_id
LEFT JOIN sponsors sp ON sp.nct_id = s.nct_id AND sp.lead_or_collaborator = 'lead'
LEFT JOIN interventions i ON i.nct_id = s.nct_id
WHERE s.nct_id IN (
    SELECT nct_id FROM interventions WHERE {term_clause}
)
"""

CONDITIONS_SQL = "SELECT nct_id, name FROM conditions WHERE nct_id = ANY(%s)"

#: CT.gov REST returns intervention synonyms inline; AACT keeps them in a side table.
#: Without this join the two backends would disagree on ``TrialIntervention.other_names``.
OTHER_NAMES_SQL = (
    "SELECT intervention_id, name FROM intervention_other_names WHERE nct_id = ANY(%s)"
)

Connector = Callable[[], Any]


def _term_clause(terms: Sequence[str]) -> tuple[str, list[str]]:
    """Build an ILIKE disjunction over intervention names.

    Parameterized rather than interpolated: alias values come from an upstream ontology
    snapshot, which is data, not trusted SQL.
    """

    if not terms:
        return "TRUE", []
    clause = " OR ".join(["name ILIKE %s"] * len(terms))
    return clause, [f"%{term}%" for term in terms]


def _rows_to_records(
    rows: Sequence[dict[str, Any]],
    conditions_by_trial: dict[str, list[str]],
    other_names_by_intervention: dict[str, list[str]],
    *,
    snapshot_root: Any,
) -> list[TrialRecord]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        nct_id = str(row.get("nct_id") or "").strip()
        if nct_id:
            grouped.setdefault(nct_id, []).append(row)

    records: list[TrialRecord] = []
    for nct_id, trial_rows in grouped.items():
        head = trial_rows[0]
        interventions: list[TrialIntervention] = []
        seen: set[str] = set()
        for row in trial_rows:
            name = str(row.get("intervention_name") or "").strip()
            if not name or name.casefold() in seen:
                continue
            seen.add(name.casefold())
            interventions.append(
                TrialIntervention(
                    name=name,
                    intervention_type=normalize_token(row.get("intervention_type")),
                    description=(str(row["intervention_description"]).strip() or None)
                    if row.get("intervention_description")
                    else None,
                    other_names=other_names_by_intervention.get(
                        str(row.get("intervention_id")), []
                    ),
                )
            )

        phase = head.get("phase")
        enrollment = head.get("enrollment")
        record = TrialRecord(
            trial_id=nct_id,
            registry=CLINICALTRIALS_GOV,
            url=f"https://clinicaltrials.gov/study/{nct_id}",
            brief_title=(str(head["brief_title"]).strip() or None) if head.get("brief_title") else None,
            official_title=(str(head["official_title"]).strip() or None) if head.get("official_title") else None,
            brief_summary=(str(head["brief_summary"]).strip() or None) if head.get("brief_summary") else None,
            detailed_description=(str(head["detailed_description"]).strip() or None)
            if head.get("detailed_description")
            else None,
            conditions=conditions_by_trial.get(nct_id, []),
            phases=normalize_phases(phase),
            overall_status=normalize_token(head.get("overall_status")),
            study_type=normalize_token(head.get("study_type")),
            enrollment=int(enrollment) if isinstance(enrollment, int) else None,
            lead_sponsor=(str(head["lead_sponsor"]).strip() or None) if head.get("lead_sponsor") else None,
            interventions=interventions,
            start_date=parse_registry_date(head.get("start_date")),
            primary_completion_date=parse_registry_date(head.get("primary_completion_date")),
            completion_date=parse_registry_date(head.get("completion_date")),
            last_update_date=parse_registry_date(head.get("last_update_posted_date")),
        )
        snapshot = write_snapshot(
            {"nct_id": nct_id, "rows": trial_rows, "digest": payload_digest(trial_rows)},
            backend=BACKEND_NAME,
            snapshot_root=snapshot_root,
        )
        records.append(record.model_copy(update={"snapshot": snapshot}))
    return records


class AACTProvider:
    """Serve trials from a local AACT mirror.

    ``connector`` returns a DB-API connection whose cursors yield ``dict``-like rows
    (``psycopg.rows.dict_row`` or ``psycopg2.extras.RealDictCursor``). Injecting it keeps
    the SQL testable without a live PostgreSQL instance.
    """

    backend_name = BACKEND_NAME

    def __init__(
        self,
        connector: Connector | None = None,
        *,
        dsn: str | None = None,
        snapshot_root: Any = None,
        snapshot_release: str | None = None,
    ) -> None:
        self.dsn = dsn or os.environ.get(DSN_ENV_VAR)
        self.connector = connector or self._default_connector
        self.snapshot_root = snapshot_root
        #: AACT refreshes daily, so the mirror date is part of the run's reproducibility
        #: token — the same query against a later mirror is a different universe.
        self.snapshot_release = snapshot_release

    def _default_connector(self) -> Any:
        if not self.dsn:
            raise RuntimeError(
                f"no AACT connection configured; set {DSN_ENV_VAR} or pass a connector"
            )
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "psycopg is required for the AACT backend (pip install psycopg[binary])"
            ) from exc
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def fetch(self, query: TrialQuery) -> TrialUniverseResult:
        clause, params = _term_clause(query.terms)
        try:
            connection = self.connector()
        except Exception as exc:
            return self._failure(str(exc))

        try:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(STUDY_SQL.format(term_clause=clause), params)
                    rows = [dict(row) for row in cursor.fetchall()]
                    trial_ids = sorted({str(row.get("nct_id")) for row in rows if row.get("nct_id")})
                    conditions_by_trial: dict[str, list[str]] = {}
                    other_names_by_intervention: dict[str, list[str]] = {}
                    if trial_ids:
                        cursor.execute(CONDITIONS_SQL, (trial_ids,))
                        for row in cursor.fetchall():
                            entry = dict(row)
                            name = str(entry.get("name") or "").strip()
                            if name:
                                conditions_by_trial.setdefault(str(entry["nct_id"]), []).append(name)
                        cursor.execute(OTHER_NAMES_SQL, (trial_ids,))
                        for row in cursor.fetchall():
                            entry = dict(row)
                            name = str(entry.get("name") or "").strip()
                            if name:
                                other_names_by_intervention.setdefault(
                                    str(entry["intervention_id"]), []
                                ).append(name)
        except Exception as exc:
            return self._failure(str(exc))

        records = _rows_to_records(
            rows,
            conditions_by_trial,
            other_names_by_intervention,
            snapshot_root=self.snapshot_root,
        )
        records = [record for record in records if query.applies(record)]
        records.sort(key=lambda record: record.trial_id)
        truncated = len(records) > query.max_records
        records = records[: query.max_records]

        return TrialUniverseResult(
            records=records,
            outcome=SearchOutcome.SUCCESS if records else SearchOutcome.NO_EVIDENCE_FOUND,
            backend=self.backend_name,
            backend_version=self.snapshot_release,
            truncated=truncated,
        )

    def _failure(self, error: str) -> TrialUniverseResult:
        return TrialUniverseResult(
            outcome=SearchOutcome.FAILED,
            backend=self.backend_name,
            backend_version=self.snapshot_release,
            error=error,
        )
