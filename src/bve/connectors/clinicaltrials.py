"""
ClinicalTrials.gov source connector.

Wraps ``bve.ingestion.clinicaltrials_gov`` (the frozen data-fetch layer) and
normalizes study protocol records into ``RawDocument`` objects for the
intelligence pipeline.

Query logic
-----------
- If ``entity_hints.nct_id`` is set → fetches that single study by NCT ID.
- Otherwise → searches by ``entity_hints.drug_name`` (free-text intervention search).

Both paths return normalized ``RawDocument`` objects with ``source="clinicaltrials_gov"``.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from bve.connectors.base import FetchResult
from bve.intelligence.extraction.raw_document import EntityHints, RawDocument


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ClinicalTrialsConnector:
    """
    Fetches trial protocol records from ClinicalTrials.gov v2 REST API.

    Parameters
    ----------
    status_filter:
        Only return studies whose overall status is in this set.
        Default: all statuses (no filter).
    """

    def __init__(
        self,
        status_filter: Optional[set[str]] = None,
    ) -> None:
        self._status_filter = status_filter

    @property
    def source_type(self) -> str:
        return "clinicaltrials_gov"

    def fetch(
        self,
        entity_hints: EntityHints,
        since: Optional[datetime] = None,
        limit: int = 50,
    ) -> FetchResult:
        now = _utcnow()
        docs: list[RawDocument] = []
        errors: list[str]       = []

        try:
            from bve.ingestion.clinicaltrials_gov import (
                fetch_trial_by_nct,
                search_studies,
            )
        except ImportError as exc:
            return FetchResult(
                source=self.source_type,
                fetch_errors=[f"Import error: {exc}"],
            )

        if entity_hints.nct_id:
            # Fetch by specific NCT ID
            try:
                raw = fetch_trial_by_nct(entity_hints.nct_id.strip().upper())
                if raw:
                    doc = self._to_document(raw, entity_hints, now)
                    if doc:
                        docs.append(doc)
            except Exception as exc:
                errors.append(f"fetch_trial_by_nct({entity_hints.nct_id}): {exc}")
        elif entity_hints.drug_name:
            # Search by drug name
            try:
                results = search_studies(entity_hints.drug_name, max_results=min(limit, 20))
                for raw in results:
                    try:
                        doc = self._to_document(raw, entity_hints, now)
                        if doc:
                            # Apply date filter
                            if since and doc.published_at and doc.published_at < since:
                                continue
                            docs.append(doc)
                            if len(docs) >= limit:
                                break
                    except Exception as exc:
                        errors.append(f"to_document: {exc}")
            except Exception as exc:
                errors.append(f"search_studies({entity_hints.drug_name!r}): {exc}")
        else:
            errors.append("entity_hints must have nct_id or drug_name to query ClinicalTrials.gov")

        return FetchResult(
            documents=docs,
            fetch_errors=errors,
            source=self.source_type,
            fetched_at=now,
        )

    def _to_document(
        self,
        raw: dict,
        entity_hints: EntityHints,
        retrieved_at: datetime,
    ) -> Optional[RawDocument]:
        try:
            proto   = raw.get("protocolSection", raw)
            id_mod  = proto.get("identificationModule", {})
            stat_mod = proto.get("statusModule", {})
            desc_mod = proto.get("descriptionModule", {})
            design_mod = proto.get("designModule", {})
            arms_mod = proto.get("armsInterventionsModule", {})
            outcomes_mod = proto.get("outcomesModule", {})
            conditions_mod = proto.get("conditionsModule", {})

            nct_id  = id_mod.get("nctId", "")
            title   = id_mod.get("briefTitle") or id_mod.get("officialTitle") or nct_id
            status  = stat_mod.get("overallStatus", "UNKNOWN")
            phases  = design_mod.get("phases", [])
            conditions = conditions_mod.get("conditions", [])
            interventions = arms_mod.get("interventions", [])
            drug_names = [
                i.get("name", "") for i in interventions
                if i.get("interventionType", "").upper() == "DRUG"
            ]

            # Apply status filter if configured
            if self._status_filter and status not in self._status_filter:
                return None

            # Primary outcomes
            primary_outcomes = outcomes_mod.get("primaryOutcomes", [])
            outcome_text = "; ".join(
                o.get("measure", "") for o in primary_outcomes[:3] if o.get("measure")
            )

            text_parts = [
                f"NCT ID: {nct_id}",
                f"Title: {title}",
                f"Status: {status}",
                f"Phases: {', '.join(phases)}",
                f"Conditions: {', '.join(conditions[:5])}",
                f"Interventions (drugs): {', '.join(drug_names[:5])}",
                f"Primary outcomes: {outcome_text}" if outcome_text else "",
                "",
                desc_mod.get("briefSummary", ""),
            ]
            raw_text = "\n".join(t for t in text_parts if t)

            # Parse published_at from last update date
            last_update = stat_mod.get("lastUpdatePostDateStruct", {}).get("date")
            start_date  = stat_mod.get("startDateStruct", {}).get("date")
            date_str    = last_update or start_date
            published_at: Optional[datetime] = None
            if date_str:
                for fmt in ("%Y-%m-%d", "%Y-%m"):
                    try:
                        published_at = datetime.strptime(date_str[:10], fmt).replace(
                            tzinfo=timezone.utc
                        )
                        break
                    except ValueError:
                        continue

            drug_hint = drug_names[0] if drug_names else entity_hints.drug_name
            hints = EntityHints(
                asset_id=entity_hints.asset_id,
                company_id=entity_hints.company_id,
                drug_name=drug_hint,
                indication=entity_hints.indication,
                ticker=entity_hints.ticker,
                nct_id=nct_id or None,
            )

            return RawDocument.from_text(
                id=str(uuid.uuid4()),
                source=self.source_type,
                title=title,
                raw_text=raw_text,
                entity_hints=hints,
                retrieved_at=retrieved_at,
                source_url=(
                    f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else None
                ),
                published_at=published_at,
            )
        except Exception:
            return None
