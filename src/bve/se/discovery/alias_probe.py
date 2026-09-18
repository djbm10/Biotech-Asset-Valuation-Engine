"""Retrieval transport for the frozen alias-admission probe.

``alias_admission`` fixes the *rule*; this fixes one way of gathering the sample it
judges. ClinicalTrials.gov is used because it is the one source every configuration of
this pipeline reaches, so an admission decision made here is available to every run.

The sample is deterministic and as-of bounded -- studies first submitted after the
as-of date are dropped, the remainder is ordered by NCT id and truncated -- so the same
source release yields the same decision, which is what makes an adaptive search plan
reproducible.
"""

from __future__ import annotations

from bve.se.acquisition.http import get_json
from bve.se.discovery.alias_admission import MAX_PROBE_DOCUMENTS

CTGOV_STUDIES_URL = "https://clinicaltrials.gov/api/v2/studies"

#: Well above ``MAX_PROBE_DOCUMENTS`` so as-of filtering still leaves a full sample, and
#: well below the response-body limit that a 1000-study page exceeded for high-volume
#: aliases. ``PD-1`` matches thousands of trials; the oversized page simply failed, which
#: the policy then read -- correctly but uselessly -- as "probe unavailable".
PROBE_PAGE_SIZE = 400


def _study_text(protocol: dict) -> str:
    ident = protocol.get("identificationModule", {})
    arms = protocol.get("armsInterventionsModule", {})
    parts = [
        ident.get("briefTitle"),
        ident.get("officialTitle"),
        protocol.get("descriptionModule", {}).get("briefSummary"),
        " ".join(i.get("name", "") for i in arms.get("interventions", [])),
        " ".join(protocol.get("conditionsModule", {}).get("conditions", []) or []),
    ]
    return " ".join(part for part in parts if part)


def ctgov_probe_fetcher(as_of_date: str):
    """``fetcher(alias) -> [(nct_id, text)] | None`` for ``probe_and_admit``.

    Returns ``None`` on any retrieval error. A probe that could not run is not weak
    evidence of ambiguity or of dominance -- it is no evidence, and the policy fails
    closed on it.
    """

    def fetch(alias: str) -> list[tuple[str, str]] | None:
        try:
            payload = get_json(
                CTGOV_STUDIES_URL,
                params={"query.term": alias, "pageSize": PROBE_PAGE_SIZE},
            )
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        documents: list[tuple[str, str]] = []
        for study in payload.get("studies", []):
            protocol = study.get("protocolSection", {})
            nct = protocol.get("identificationModule", {}).get("nctId")
            submitted = protocol.get("statusModule", {}).get("studyFirstSubmitDate", "")
            if not nct or (submitted and submitted > as_of_date):
                continue
            documents.append((nct, _study_text(protocol)))
        documents.sort(key=lambda pair: pair[0])
        return documents[:MAX_PROBE_DOCUMENTS]

    return fetch
