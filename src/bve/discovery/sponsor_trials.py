"""Fetch + parse a sponsor's CT.gov trials into typed records.

This is the only module in the discovery package that touches the network, and
even that is behind an injectable fetcher + an optional ``DiskCache``. The parser
(`parse_protocol`) is pure over a raw CT.gov ``protocolSection`` dict, so all
clustering/ranking logic downstream is testable fully offline.

CT.gov v2 protocol modules consumed here (not extracted by the existing
``ctgov_client``): ``armsInterventionsModule.interventions[]`` (drug names),
``sponsorCollaboratorsModule.leadSponsor`` (lead sponsor + class), and
``conditionsModule.conditions[]`` (indications).
"""
from __future__ import annotations

import re
from typing import Callable, Optional

from pydantic import BaseModel

from bve.ingestion.clinicaltrials_gov import search_studies

# CT.gov phase token → canonical stage string (registry vocab).
_PHASE_TOKEN_MAP: dict[str, str] = {
    "EARLY_PHASE1": "phase_1",
    "PHASE1": "phase_1",
    "PHASE2": "phase_2",
    "PHASE3": "phase_3",
    "PHASE4": "phase_3",  # treat Phase 4 as Phase 3, matching the valuation client
}
_PHASE_RANK: dict[str, int] = {"phase_1": 1, "phase_2": 2, "phase_3": 3}

# Intervention types that represent an investigational asset (vs. procedure/device).
_ASSET_INTERVENTION_TYPES = {"DRUG", "BIOLOGICAL", "GENETIC", "COMBINATION_PRODUCT"}

_PLACEBO_RE = re.compile(r"\b(placebo|sham|standard of care|best supportive care)\b", re.I)
_SPONSOR_NOISE_RE = re.compile(
    r"\b(inc|inc\.|incorporated|corp|corporation|co|company|ltd|limited|llc|"
    r"plc|sa|ag|nv|holdings|pharmaceuticals|pharmaceutical|pharma|"
    r"therapeutics|biosciences|bioscience|biotherapeutics|biopharma|"
    r"sciences|technologies|medicines|oncology|the)\b",
    re.I,
)


class TrialRecord(BaseModel, frozen=True):
    """One CT.gov trial reduced to the fields the ranker needs."""

    nct_id: str
    title: str = ""
    drug_names: tuple[str, ...] = ()
    primary_drug_aliases: tuple[str, ...] = ()  # CT.gov otherNames of the primary drug
    primary_intervention_type: str = ""  # CT.gov type of the primary drug (DRUG/BIOLOGICAL/…)
    phase: Optional[str] = None  # phase_1 | phase_2 | phase_3 | None
    status: str = ""
    start_date: Optional[str] = None
    primary_completion_date: Optional[str] = None
    enrollment: Optional[int] = None
    lead_sponsor: str = ""
    lead_sponsor_class: str = ""
    sponsor_is_lead: bool = False
    conditions: tuple[str, ...] = ()


def _phase_from_tokens(phases: list[str]) -> Optional[str]:
    """Reduce a CT.gov phase list (e.g. ["PHASE1","PHASE2"]) to the max stage."""
    mapped = [_PHASE_TOKEN_MAP[p] for p in phases if p in _PHASE_TOKEN_MAP]
    if not mapped:
        return None
    return max(mapped, key=lambda s: _PHASE_RANK[s])


def _extract_interventions(arms_mod: dict) -> list[tuple[str, tuple[str, ...], str]]:
    """Investigational interventions as (name, otherNames, type), placebo dropped.

    ``otherNames`` are CT.gov-supplied synonyms/code-names — a strong clustering
    signal. ``type`` is CT.gov's intervention classification (DRUG / BIOLOGICAL /
    GENETIC / …) — the best available signal for modality inference.
    """
    out: list[tuple[str, tuple[str, ...], str]] = []
    seen: set[str] = set()
    for iv in arms_mod.get("interventions", []):
        itype = iv.get("type", "").upper()
        if itype not in _ASSET_INTERVENTION_TYPES:
            continue
        name = (iv.get("name") or "").strip()
        if not name or _PLACEBO_RE.search(name):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        aliases = tuple(
            a.strip() for a in iv.get("otherNames", []) if a and a.strip()
        )
        out.append((name, aliases, itype))
    return out


def _normalize_sponsor(name: str) -> str:
    """Lower-case, strip corporate-suffix noise + punctuation for fuzzy comparison."""
    text = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    text = _SPONSOR_NOISE_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _sponsor_matches(lead_sponsor: str, company_name: Optional[str]) -> bool:
    """True when the trial's lead sponsor plausibly *is* the queried company."""
    if not company_name or not lead_sponsor:
        return False
    a, b = _normalize_sponsor(lead_sponsor), _normalize_sponsor(company_name)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return True
    # Token overlap (handles word-order / partial-name variants).
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.5


def parse_protocol(
    protocol: dict,
    company_name: Optional[str] = None,
) -> Optional[TrialRecord]:
    """Convert a raw CT.gov ``protocolSection`` dict → ``TrialRecord``.

    Returns None only when the record has no NCT id (unusable). Trials without a
    parseable phase are kept with ``phase=None`` — the clusterer/ranker decide
    what to do with them.
    """
    id_mod = protocol.get("identificationModule", {})
    nct_id = (id_mod.get("nctId") or "").strip()
    if not nct_id:
        return None

    status_mod = protocol.get("statusModule", {})
    design_mod = protocol.get("designModule", {})
    arms_mod = protocol.get("armsInterventionsModule", {})
    spons_mod = protocol.get("sponsorCollaboratorsModule", {})
    cond_mod = protocol.get("conditionsModule", {})

    lead = spons_mod.get("leadSponsor", {})
    lead_name = (lead.get("name") or "").strip()

    enrollment = design_mod.get("enrollmentInfo", {}).get("count")
    try:
        enrollment = int(enrollment) if enrollment is not None else None
    except (TypeError, ValueError):
        enrollment = None

    interventions = _extract_interventions(arms_mod)
    drug_names = tuple(name for name, _, _ in interventions)
    primary_aliases = interventions[0][1] if interventions else ()
    primary_type = interventions[0][2] if interventions else ""

    return TrialRecord(
        nct_id=nct_id,
        title=(id_mod.get("briefTitle") or "").strip(),
        drug_names=drug_names,
        primary_drug_aliases=primary_aliases,
        primary_intervention_type=primary_type,
        phase=_phase_from_tokens(design_mod.get("phases", [])),
        status=(status_mod.get("overallStatus") or "").strip(),
        start_date=status_mod.get("startDateStruct", {}).get("date"),
        primary_completion_date=status_mod.get("primaryCompletionDateStruct", {}).get("date"),
        enrollment=enrollment,
        lead_sponsor=lead_name,
        lead_sponsor_class=(lead.get("class") or "").strip(),
        sponsor_is_lead=_sponsor_matches(lead_name, company_name),
        conditions=tuple(c for c in cond_mod.get("conditions", []) if c),
    )


def _cache_key(company_name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", company_name.lower()).strip("_")
    return slug or "unknown"


def sponsor_query_candidates(company_name: str) -> list[str]:
    """Ordered CT.gov sponsor-query strings to try for one company, broadest last.

    ``query.spons`` matches the sponsor string literally-ish, so legal and
    descriptor suffixes ("Merus N.V.", "Argenx SE", "Terns Pharmaceuticals",
    "Annexon Biosciences") frequently miss because CT.gov indexes the bare core
    name. We therefore try the full name first, then a suffix-stripped form, then
    the distinctive leading token(s). Order matters: the most specific query wins
    so we don't over-broaden into another sponsor's trials when the full name works.
    """
    candidates: list[str] = []
    seen: set[str] = set()

    def _add(value: str) -> None:
        value = re.sub(r"\s+", " ", value).strip()
        if value and value.lower() not in seen:
            seen.add(value.lower())
            candidates.append(value)

    _add(company_name)
    base = re.sub(r"\([^)]*\)", " ", company_name)
    stripped = _SPONSOR_NOISE_RE.sub(" ", re.sub(r"[,.]", " ", base))
    _add(stripped)
    tokens = stripped.split()
    if tokens:
        _add(" ".join(tokens[:2]))
        if len(tokens[0]) >= 3:
            _add(tokens[0])
    return candidates


def fetch_sponsor_trials(
    company_name: str,
    *,
    fetcher: Callable[..., list[dict]] = search_studies,
    cache=None,
    page_size: int = 200,
    cache_only: bool = False,
) -> list[TrialRecord]:
    """Fetch + parse all of a sponsor's trials.

    ``fetcher`` defaults to ``clinicaltrials_gov.search_studies`` but is injectable
    for tests. When a ``DiskCache`` is supplied, raw protocols are cached under the
    ``ctgov`` namespace; ``cache_only=True`` forbids the network (returns whatever
    is cached, else empty).
    """
    protocols: Optional[list[dict]] = None
    key = _cache_key(company_name)

    if cache is not None:
        cached = cache.get("ctgov", key)
        if cached is not None:
            protocols = cached.get("protocols")

    if protocols is None:
        if cache_only:
            return []
        # Try progressively broader sponsor-name forms until one resolves trials;
        # legal/descriptor suffixes ("N.V.", "SE", "Pharmaceuticals") otherwise
        # miss CT.gov's bare-core sponsor index.
        protocols = []
        for candidate in sponsor_query_candidates(company_name):
            protocols = fetcher(sponsor=candidate, page_size=page_size)
            if protocols:
                break
        if cache is not None:
            cache.put("ctgov", key, {"protocols": protocols})

    records = []
    for proto in protocols or []:
        rec = parse_protocol(proto, company_name)
        if rec is not None:
            records.append(rec)
    return records
