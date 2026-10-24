"""Bounded historical-name research leads, NOT identity admission or scientific evidence.

This opt-in workflow deliberately never imports the asset registry, resolver or gates.
Even an explicit naming relationship licenses retrieval only. An analyst must adjudicate
whether the retrieved intervention is the same product before using its development history.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlencode

from bve.se.acquisition.http import get_json

API = "https://clinicaltrials.gov/api/v2/studies"
CODE = r"(?:[A-Z]{2,10}-[0-9]{2,6}|[A-Z]{3,10}[0-9]{2,6})"
PAIR = re.compile(rf"\b({CODE})\s*\(\s*({CODE})\s*\)")
FORMER = re.compile(
    rf"\b([A-Za-z][A-Za-z0-9-]{{1,39}})\s*[,;(]?\s*"
    rf"(?:formerly|previously known as|also known as)\s+({CODE})\b",
    re.IGNORECASE,
)
UNSAFE_CONTEXT = re.compile(
    r"\b(?:not|distinct|different|combination|combined|versus|vs|co-administered)\b", re.IGNORECASE
)
TERM = re.compile(r"[A-Za-z][A-Za-z0-9-]{2,39}\Z")


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def safe_term(value: str) -> bool:
    return (
        isinstance(value, str)
        and bool(TERM.fullmatch(value))
        and value.casefold()
        not in {
            "and",
            "not",
            "placebo",
            "drug",
            "biological",
            "treatment",
            "control",
        }
    )


@dataclass(frozen=True)
class NamingLead:
    left: str
    right: str
    source_url: str
    source_sha256: str
    pointer: str
    passage: str
    basis: str
    status: str = "RETRIEVAL_LEAD_NOT_IDENTITY"


def company_naming_leads(text: str, url: str) -> list[NamingLead]:
    """Narrow explicit patterns, with offsets into the supplied visible-text snapshot."""
    if len(text.encode()) > 2 * 1024**2:
        raise ValueError("company document budget exceeded")
    if not url.startswith("https://"):
        raise ValueError("primary HTTPS source URL required")
    leads = []
    for pattern, basis in ((PAIR, "parenthetical code pair"), (FORMER, "explicit naming phrase")):
        for match in pattern.finditer(text):
            left, right = match.groups()
            if left.casefold() == right.casefold() or not safe_term(left) or not safe_term(right):
                continue
            context = text[max(0, match.start() - 80) : match.end() + 80]
            status = (
                "REVIEW_REQUIRED"
                if UNSAFE_CONTEXT.search(context)
                else "RETRIEVAL_LEAD_NOT_IDENTITY"
            )
            leads.append(
                NamingLead(
                    left,
                    right,
                    url,
                    hashlib.sha256(text.encode()).hexdigest(),
                    f"text[{match.start()}:{match.end()}]",
                    match.group(),
                    basis,
                    status,
                )
            )
    return leads


def registry_naming_leads(study: dict) -> list[NamingLead]:
    """One intervention's single code alias; never join co-interventions or alias lists."""
    protocol = study["protocolSection"]
    nct = protocol["identificationModule"]["nctId"]
    leads = []
    for i, intervention in enumerate(
        protocol.get("armsInterventionsModule", {}).get("interventions", [])
    ):
        name, others = intervention.get("name", ""), intervention.get("otherNames", [])
        if intervention.get("type") not in {"DRUG", "BIOLOGICAL"} or not safe_term(name):
            continue
        for j, other in enumerate(others):
            if not isinstance(other, str) or not safe_term(other):
                continue
            if not (re.fullmatch(CODE, name) or re.fullmatch(CODE, other)):
                continue
            status = "RETRIEVAL_LEAD_NOT_IDENTITY" if len(others) == 1 else "REVIEW_REQUIRED"
            leads.append(
                NamingLead(
                    name,
                    other,
                    f"https://clinicaltrials.gov/study/{nct}",
                    digest(study),
                    f"/protocolSection/armsInterventionsModule/interventions/{i}/otherNames/{j}",
                    json.dumps({"name": name, "otherName": other}, ensure_ascii=False),
                    "registry related naming metadata; not identity proof",
                    status,
                )
            )
    return leads


def _validate_study(study: dict) -> None:
    """Reject malformed structures before partial records can drive further queries."""
    protocol = study["protocolSection"]
    for key in (
        "identificationModule",
        "armsInterventionsModule",
        "statusModule",
        "designModule",
        "conditionsModule",
        "sponsorCollaboratorsModule",
    ):
        if key in protocol and not isinstance(protocol[key], dict):
            raise TypeError("malformed registry module")
    interventions = protocol.get("armsInterventionsModule", {}).get("interventions", [])
    if not isinstance(interventions, list):
        raise TypeError("malformed interventions")
    for intervention in interventions:
        if not isinstance(intervention, dict) or not isinstance(intervention.get("name", ""), str):
            raise TypeError("malformed intervention")
        others = intervention.get("otherNames", [])
        if not isinstance(others, list) or any(not isinstance(n, str) for n in others):
            raise TypeError("malformed related names")
    design = protocol.get("designModule", {})
    conditions = protocol.get("conditionsModule", {}).get("conditions", [])
    for values in (design.get("phases", []), conditions):
        if not isinstance(values, list) or any(not isinstance(v, str) for v in values):
            raise TypeError("malformed phase/condition list")
    for value in (
        design.get("enrollmentInfo", {}),
        protocol.get("statusModule", {}).get("lastUpdatePostDateStruct", {}),
        protocol.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}),
    ):
        if not isinstance(value, dict):
            raise TypeError("malformed registry details")


def _live_fetch(params: dict) -> dict:
    return get_json(API, params=params, timeout=(5, 20), max_bytes=2 * 1024**2)


def query_term(term: str, fetch: Callable[[dict], dict] = _live_fetch) -> dict:
    """At most two pages; completeness refers ONLY to this literal query at observation."""
    if not safe_term(term):
        raise ValueError("unsafe or non-specific query term")
    pages, studies, seen_tokens = [], {}, set()
    token = None
    total = None
    status = "TRUNCATED"
    error = None
    try:
        for _ in range(2):
            params = {"query.intr": f'"{term}"', "pageSize": 100, "countTotal": "true"}
            if token:
                params["pageToken"] = token
            payload = fetch(params)
            if len(json.dumps(payload).encode()) > 2 * 1024**2:
                raise ValueError("response byte budget exceeded")
            pages.append(
                {
                    "url": API + "?" + urlencode(params),
                    "sha256": digest(payload),
                    "payload": payload,
                }
            )
            if not isinstance(payload, dict) or type(payload.get("totalCount")) is not int:
                raise ValueError("missing registry count")
            if payload["totalCount"] < 0 or (total is not None and total != payload["totalCount"]):
                raise ValueError("invalid/changing registry count")
            total = payload["totalCount"]
            rows = payload.get("studies", [] if total == 0 else None)
            if not isinstance(rows, list):
                raise TypeError("malformed registry page")
            for study in rows:
                _validate_study(study)
                nct = study["protocolSection"]["identificationModule"]["nctId"]
                if not re.fullmatch(r"NCT\d{8}", nct):
                    raise ValueError("invalid trial identifier")
                if nct in studies and studies[nct] != study:
                    raise ValueError("conflicting duplicate trial")
                studies[nct] = study
            token = payload.get("nextPageToken")
            if not token:
                status = "QUERY_PAGES_COMPLETE" if len(studies) == total else "COUNT_MISMATCH"
                break
            if not isinstance(token, str) or token in seen_tokens:
                raise ValueError("invalid/repeated page token")
            seen_tokens.add(token)
    except Exception as exc:  # noqa: BLE001 — retain partial evidence at acquisition boundary
        status, error = "FAILED", type(exc).__name__
    return {
        "term": term,
        "status": status,
        "total_count": total,
        "error": error,
        "pages": pages,
        "studies": studies,
    }


def investigate_history(
    root: str,
    company_documents: list[dict],
    *,
    fetch: Callable[[dict], dict] = _live_fetch,
    known_claimants: dict[str, list[str]] | None = None,
) -> dict:
    """Three rounds, six terms, no automatic identity merges or scientific decisions.

    known_claimants is optional externally supplied collision evidence, NOT a resolver.
    Its absence means collisions are unassessed, never that a name is globally unique.
    """
    if not safe_term(root) or len(company_documents) > 10:
        raise ValueError("invalid root/document budget")
    claims = {k.casefold(): {v.casefold() for v in vs} for k, vs in (known_claimants or {}).items()}
    leads = [
        lead for doc in company_documents for lead in company_naming_leads(doc["text"], doc["url"])
    ]
    known, queried, queries, blocked = {root.casefold(): root}, set(), [], []
    records, query_terms, conflicts = {}, {}, set()
    for _ in range(3):
        pending = sorted(set(known) - queried)
        if not pending:
            break
        for key in pending:
            if len(queries) >= 6:
                break
            queried.add(key)
            result = query_term(known[key], fetch)
            queries.append(result)
            for nct, study in result["studies"].items():
                query_terms.setdefault(nct, []).append(known[key])
                if nct in records and records[nct] != study:
                    conflicts.add(nct)
                records[nct] = study
                # Partial/failed queries are retained, but cannot bootstrap further terms.
                if result["status"] == "QUERY_PAGES_COMPLETE":
                    leads.extend(registry_naming_leads(study))
        candidates: dict[str, tuple[str, set[str]]] = {}
        for lead in leads:
            if lead.status != "RETRIEVAL_LEAD_NOT_IDENTITY":
                continue
            for parent, child in ((lead.left, lead.right), (lead.right, lead.left)):
                if parent.casefold() not in queried or child.casefold() in known:
                    continue
                entry = candidates.setdefault(child.casefold(), (child, set()))
                entry[1].add(parent.casefold())
        for key, (child, parents) in sorted(candidates.items()):
            other_claimants = claims.get(key, set()) - {root.casefold()}
            if other_claimants or len(parents) > 1:
                blocked.append(
                    {
                        "term": child,
                        "reason": "ambiguous parents/other root claim",
                        "parents": sorted(parents),
                        "other_claimants": sorted(other_claimants),
                    }
                )
            elif len(known) < 6:
                known[key] = child
            else:
                blocked.append({"term": child, "reason": "term budget"})
    trials = []
    for nct, study in sorted(records.items()):
        protocol = study["protocolSection"]
        interventions = protocol.get("armsInterventionsModule", {}).get("interventions", [])
        exact = sorted(
            {
                name
                for i in interventions
                for name in [i.get("name", "")]
                if name.casefold() in queried
            }
        )
        status = protocol.get("statusModule", {})
        design = protocol.get("designModule", {})
        trials.append(
            {
                "nct_id": nct,
                "source_url": f"https://clinicaltrials.gov/study/{nct}",
                "study_sha256": digest(study),
                "query_terms": sorted(query_terms[nct]),
                "exact_intervention_names": exact,
                "attribution": "CONFLICTING_SNAPSHOTS"
                if nct in conflicts
                else "REQUIRES_IDENTITY_REVIEW"
                if exact
                else "UNATTRIBUTED_QUERY_HIT",
                "status": status.get("overallStatus", "UNKNOWN"),
                "why_stopped": status.get("whyStopped"),
                "last_update": status.get("lastUpdatePostDateStruct", {}).get("date"),
                "phase": design.get("phases", []),
                "enrollment": design.get("enrollmentInfo", {}),
                "conditions": protocol.get("conditionsModule", {}).get("conditions", []),
                "sponsor": protocol.get("sponsorCollaboratorsModule", {})
                .get("leadSponsor", {})
                .get("name"),
            }
        )
    unique_leads = {json.dumps(asdict(e), sort_keys=True): asdict(e) for e in leads}
    return {
        "root": root,
        "validation_grade": "UNVALIDATED",
        "warning": "Do not use for trade sizing or acquisition probability.",
        "asset_history_completeness": "UNKNOWN",
        "identity_merges": [],
        "scientific_eligibility": "NOT_EVALUATED",
        "collision_coverage": "NOT_EXHAUSTIVE",
        "queries": queries,
        "naming_leads": [unique_leads[k] for k in sorted(unique_leads)],
        "blocked_terms": blocked,
        "unqueried_terms": sorted(set(known) - queried),
        "trials": trials,
        "other_registries": "NOT_SEARCHED",
    }
