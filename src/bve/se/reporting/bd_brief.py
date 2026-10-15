"""A BD screening brief composed from one finished development run.

The shortlist answers "which assets did the run find"; the audit memo answers "what did the
run do". Neither is organized the way a BD / external-innovation reader works: start from the
strategic gap, look at the candidates side by side, see which facts are actually supported,
then decide what to investigate next. This module recomposes records the run already wrote
(``problem.yaml``, ``shortlist.json`` and, when present, ``result.json``) into that shape.

It changes no decision. Eligibility is the gate engine's disposition, the target is the
attribution status, and the order is the shortlist's declared order. What it adds is
*classification of display*: every fact is labelled SUPPORTED, UNVERIFIED, UNKNOWN or
CONTRADICTORY, and the diligence questions are derived from which of those labels a candidate
carries. Two rules are fixed:

* a modality read from surrounding trial text, or a target known only from the search
  context, is never shown as SUPPORTED;
* a prose-derived ``human_poc_present`` fact is shown as an UNVERIFIED public claim with its
  passage, never as clinical proof (``human_poc_precision_first_v1.md``: no validated
  confirmation route exists).

No score is computed. A development demonstration, not a validated product.
"""

from __future__ import annotations

import html
import json
import re
from collections import Counter
from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from bve.se.reporting.shortlist import display_name

__all__ = [
    "BDBrief",
    "CandidateCard",
    "EvidenceStatus",
    "build_bd_brief",
    "load_run",
    "render_html",
    "render_markdown",
    "usefulness_checks",
]

DEFAULT_LIMIT = 10
#: Authority modality classes whose manufacturing is itself a diligence topic.
_COMPLEX_MODALITIES = {"CELL_THERAPY", "GENE_THERAPY", "GENE", "CELL"}
_AUTHORITY_RECORD = re.compile(r"molecule type of (\S+(?: [A-Z0-9-]+)*?) \(")
_FAIL_REASON = re.compile(r"^(\S+) FAIL: (.*)$")
_ENTAILMENT = "Citation does not entail material claim"
_HUMAN_POC_REQUIREMENT = "evidence.human_poc"


class EvidenceStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    UNVERIFIED = "UNVERIFIED"
    UNKNOWN = "UNKNOWN"
    CONTRADICTORY = "CONTRADICTORY"


class Source(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    url: str | None = None
    passage: str | None = None


class Assessed(BaseModel):
    """One displayed fact with its evidence status and the reason for that status."""

    model_config = ConfigDict(frozen=True)

    value: str | None
    status: EvidenceStatus
    basis: str
    sources: tuple[Source, ...] = ()


class GateRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    requirement: str
    status: str
    rationale: str


class Question(BaseModel):
    model_config = ConfigDict(frozen=True)

    area: str
    question: str
    grounded_on: str


class CandidateCard(BaseModel):
    model_config = ConfigDict(frozen=True)

    asset_id: str
    name: str
    position: int
    eligibility: str
    disposition: str
    why: str
    company: Assessed
    target: Assessed
    modality: Assessed
    stage: Assessed
    human_efficacy: Assessed
    discovery_modality: str | None = None
    authority_record: str | None = None
    gates: tuple[GateRow, ...] = ()
    failed_requirements: tuple[str, ...] = ()
    unentailed_claims: int = 0
    questions: tuple[Question, ...] = ()
    change_triggers: tuple[str, ...] = ()
    duplicate_of: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()


class StrategicGap(BaseModel):
    model_config = ConfigDict(frozen=True)

    question: str
    rationale: str
    targets: tuple[str, ...]
    modalities: tuple[str, ...]
    indications: tuple[str, ...]
    therapeutic_areas: tuple[str, ...]
    minimum_stage: str | None
    enforced: tuple[str, ...]
    not_enforced: tuple[str, ...]


class BDBrief(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    run_id: str
    problem_id: str
    as_of_date: str
    run_status: str
    gap: StrategicGap
    candidates: tuple[CandidateCard, ...]
    excluded: tuple[CandidateCard, ...]
    counts: dict[str, int]
    blind_spots: tuple[str, ...]
    summary: tuple[str, ...]
    engine_eligible: tuple[str, ...]
    review_first: tuple[str, ...]
    unresolved: tuple[str, ...]
    held_back_notable: tuple[str, ...]
    next_action: str
    limitations: tuple[str, ...]
    inputs: dict[str, str]


# --------------------------------------------------------------------------- loading


def load_run(run_dir: Path, *, limit: int = DEFAULT_LIMIT) -> dict:
    """Read the run's own artifacts; ``result.json`` is reduced to the shown assets."""

    problem = yaml.safe_load((run_dir / "problem.yaml").read_text())
    shortlist = json.loads((run_dir / "shortlist.json").read_text())
    shown = {e["asset_id"] for e in shortlist["entries"][:limit]} | {
        e["asset_id"] for e in shortlist["excluded"]
    }
    run = {"problem": problem, "shortlist": shortlist, "result": None}
    result_path = run_dir / "result.json"
    if result_path.exists():
        result = json.loads(result_path.read_text())
        facts = [
            f
            for f in result["facts"]
            if f["subject_id"] in shown and f["fact_type"] == "human_poc_present"
        ]
        claim_ids = {
            c for f in facts for c in f["supporting_claim_ids"] + f["contradicting_claim_ids"]
        }
        claims = {c["claim_id"]: c for c in result["claims"] if c["claim_id"] in claim_ids}
        doc_ids = {c["source_document_id"] for c in claims.values()}
        run["result"] = {
            "gates": {
                g["subject_id"]: g for g in result["gate_evaluations"] if g["subject_id"] in shown
            },
            "poc_facts": facts,
            "claims": claims,
            "documents": {
                d["document_id"]: d
                for d in result["source_documents"]
                if d["document_id"] in doc_ids
            },
        }
    return run


# --------------------------------------------------------------------------- assessment


def _fact(entry: dict, label: str) -> dict:
    return next((f for f in entry["facts"] if f["label"] == label), {})


def _sources(fact: dict, limit: int = 3) -> tuple[Source, ...]:
    out = []
    for c in fact.get("citations", [])[:limit]:
        label = c.get("native_id") or c.get("source_family") or "authority record"
        if c.get("origin") == "STRUCTURED_AUTHORITY":
            native = c.get("native_id") or ""
            record = f" record {native}" if native and len(native) < 20 else ""
            label = f"{c.get('source_family')} {c.get('effective_date') or ''}{record}".strip()
        if c.get("structured_field"):
            label = f"{label} ({c['structured_field']})"
        out.append(Source(label=label, url=c.get("url"), passage=c.get("evidence_span")))
    return tuple(out)


def _company(entry: dict) -> Assessed:
    fact = _fact(entry, "Company")
    if not fact.get("value"):
        return Assessed(
            value=None, status=EvidenceStatus.UNKNOWN, basis="no company named in this corpus"
        )
    return Assessed(
        value=fact["value"],
        status=EvidenceStatus.UNVERIFIED,
        basis="trial sponsors/collaborators named in registry records; the rights holder is not established",
        sources=_sources(fact),
    )


def _target(entry: dict, requested: tuple[str, ...]) -> Assessed:
    fact = _fact(entry, "Target")
    status = entry["target_status"]
    sources = _sources(fact)
    if status == "CONFIRMED_TARGET":
        return Assessed(
            value=entry["target_id"],
            status=EvidenceStatus.SUPPORTED,
            basis="drug-to-target authority records (ChEMBL / Open Targets) name the requested target",
            sources=sources,
        )
    if status == "CONFIRMED_OTHER_TARGET":
        others = sorted(
            {(c.get("structured_field") or "").split("-> ")[-1] for c in fact.get("citations", [])}
            - {""}
        )
        return Assessed(
            value=", ".join(others) or "another target",
            status=EvidenceStatus.CONTRADICTORY,
            basis=f"authority records name a different target than requested ({', '.join(requested)})",
            sources=sources,
        )
    return Assessed(
        value=None,
        status=EvidenceStatus.UNKNOWN,
        basis=(
            f"found while searching {', '.join(requested)}, but no authority record names its target; "
            "the search context is not evidence"
        ),
    )


def _modality(entry: dict, requested: tuple[str, ...]) -> tuple[Assessed, str | None, str | None]:
    authority = _fact(entry, "Authority modality")
    discovery = _fact(entry, "Modality").get("value")
    note = authority.get("note") or ""
    match = _AUTHORITY_RECORD.search(note)
    record = match.group(1) if match else None
    value = authority.get("value")
    if not value:
        assessed = Assessed(
            value=None,
            status=EvidenceStatus.UNKNOWN,
            basis="no authority record of this asset's drug; the trial-text modality hint is not evidence",
        )
    elif not requested:
        assessed = Assessed(
            value=value, status=EvidenceStatus.SUPPORTED, basis=f"{note}; no modality was requested"
        )
    elif value in requested:
        assessed = Assessed(value=value, status=EvidenceStatus.SUPPORTED, basis=note)
    else:
        assessed = Assessed(
            value=value,
            status=EvidenceStatus.CONTRADICTORY,
            basis=f"{note}; requested {', '.join(requested) or 'no modality'}",
        )
    return assessed, discovery, record


def _stage(entry: dict) -> Assessed:
    fact = _fact(entry, "Phase")
    if not fact.get("value"):
        return Assessed(
            value=None, status=EvidenceStatus.UNKNOWN, basis="no development stage was established"
        )
    return Assessed(
        value=fact["value"],
        status=EvidenceStatus.SUPPORTED,
        basis=(
            f"most advanced stage across {len(fact.get('citations', []))} registry/publication records; "
            "individual trials may be earlier"
        ),
        sources=_sources(fact),
    )


def _human_efficacy(asset_id: str, result: dict | None) -> Assessed:
    if result is None:
        return Assessed(
            value=None,
            status=EvidenceStatus.UNKNOWN,
            basis="result.json not available for this run",
        )
    facts = [f for f in result["poc_facts"] if f["subject_id"] == asset_id]
    if not facts:
        return Assessed(
            value=None,
            status=EvidenceStatus.UNKNOWN,
            basis="no human efficacy statement was extracted; absence of extraction is not absence of data",
        )
    fact = facts[0]
    sources = []
    for cid in fact["supporting_claim_ids"][:3]:
        claim = result["claims"].get(cid)
        if not claim:
            continue
        doc = result["documents"].get(claim["source_document_id"], {})
        sources.append(
            Source(
                label=f"{doc.get('publisher', 'source')} ({claim.get('locator') or 'locator unavailable'})",
                url=doc.get("source_url"),
                passage=_clean_passage(claim.get("supporting_passage") or ""),
            )
        )
    if fact["contradicting_claim_ids"]:
        return Assessed(
            value="conflicting statements",
            status=EvidenceStatus.CONTRADICTORY,
            basis="extracted efficacy statements conflict; read both passages",
            sources=tuple(sources),
        )
    return Assessed(
        value="efficacy statement in public text",
        status=EvidenceStatus.UNVERIFIED,
        basis=(
            "legacy prose-derived human_poc_present; there is no validated confirmation route, so this "
            "is an unverified public claim for analyst reading, not established clinical proof"
        ),
        sources=tuple(sources),
    )


def _clean_passage(text: str) -> str:
    text = re.sub(r'^\s*"?[a-z_]+"\s*:\s*"', "", text.strip())
    return text.rstrip('",').strip()


def _gates(asset_id: str, result: dict | None) -> tuple[GateRow, ...]:
    if result is None or asset_id not in result["gates"]:
        return ()
    rows = []
    for d in result["gates"][asset_id]["decisions"]:
        status = d.get("analyst_override") or d["status"]
        rows.append(
            GateRow(requirement=d["requirement_id"], status=status, rationale=d["rationale"])
        )
    return tuple(rows)


# --------------------------------------------------------------------------- diligence


def _questions(
    card: dict, gap: StrategicGap, requested_targets: tuple[str, ...]
) -> tuple[Question, ...]:
    """Questions follow from the gaps a card actually has, in Harvey's order of value."""

    target, modality, stage, poc = (
        card["target"],
        card["modality"],
        card["stage"],
        card["human_efficacy"],
    )
    trials = [s.label.split(" ")[0] for s in stage.sources if s.label.startswith("NCT")]
    trial = trials[0] if trials else "the most advanced registered trial"
    out: list[Question] = []
    if target.status is EvidenceStatus.UNKNOWN:
        out.append(
            Question(
                area="Biology / target",
                question=f"Does the construct bind {' and '.join(requested_targets)}, and is it the only antigen it binds? "
                "Confirm from a product description, label or company disclosure.",
                grounded_on="target is known only from the search context",
            )
        )
    elif target.status is EvidenceStatus.CONTRADICTORY:
        out.append(
            Question(
                area="Biology / target",
                question=f"Authority records name {target.value}; is there any public basis for activity against "
                f"{', '.join(requested_targets)}, or is this background therapy in the trial?",
                grounded_on="authority target differs from the request",
            )
        )
    if modality.status is EvidenceStatus.CONTRADICTORY:
        out.append(
            Question(
                area="Target engagement / format",
                question=f"The authority record classes this as {modality.value}, not {', '.join(gap.modalities)}. "
                "Is it the product format the buyer is looking for?",
                grounded_on="authority modality differs from the request",
            )
        )
    elif modality.status is EvidenceStatus.UNKNOWN:
        out.append(
            Question(
                area="Target engagement / format",
                question="What is the product format (construct, autologous vs allogeneic, co-stimulatory domain or "
                "antibody format)?",
                grounded_on="no authority modality record",
            )
        )
    if poc.status in (EvidenceStatus.UNVERIFIED, EvidenceStatus.CONTRADICTORY):
        out.append(
            Question(
                area="Clinical readout",
                question="Do the quoted efficacy passages hold up: is the disease the requested indication, "
                "and which population, line of therapy, n, endpoint and comparator? Is the result attributable "
                "to this product rather than a regimen?",
                grounded_on="unverified prose efficacy statement",
            )
        )
    elif stage.status is EvidenceStatus.SUPPORTED:
        out.append(
            Question(
                area="Clinical readout",
                question=f"What primary endpoint and readout timing does {trial} declare, and has any result been "
                "posted or presented?",
                grounded_on=f"registered {stage.value} activity, no extracted efficacy data",
            )
        )
    if modality.value in _COMPLEX_MODALITIES or (card.get("discovery_modality") or "").startswith(
        "CAR"
    ):
        out.append(
            Question(
                area="Safety / dosing",
                question="What dose levels, CRS/neurotoxicity rates and lymphodepletion regimen are reported in the "
                "cited trials? (not extracted by the engine)",
                grounded_on="cell-therapy product class",
            )
        )
        out.append(
            Question(
                area="Manufacturing / scale-up",
                question="Autologous or allogeneic? Vein-to-vein time, manufacturing success rate, CMC site and "
                "capacity to supply a commercial launch.",
                grounded_on="cell-therapy product class",
            )
        )
    if card["company"].status is not EvidenceStatus.SUPPORTED:
        out.append(
            Question(
                area="Rights",
                question="Is it already approved, marketed or partnered, and who holds development and "
                "commercial rights by territory? Registry sponsors are not owners, and approval is not "
                "represented in this brief.",
                grounded_on="ownership not established",
            )
        )
    return tuple(out)


def _change_triggers(card: dict, gates: tuple[GateRow, ...]) -> tuple[str, ...]:
    out = [
        f"{g.requirement}: a source that settles this would move the candidate from Unknown"
        for g in gates
        if g.status == "UNKNOWN"
    ]
    if card["target"].status is EvidenceStatus.UNKNOWN and not any("target" in t for t in out):
        out.append("target: an authority record or product description naming the antigen")
    return tuple(out)


# --------------------------------------------------------------------------- assembly


def _gap(problem: dict, context: dict) -> StrategicGap:
    sg = problem["strategic_gap"]
    targets = tuple(t["label"] for t in (sg.get("target_expression") or {}).get("targets", []))
    floor = sg.get("evidence_floor") or {}
    enforced = [
        f"target ({(sg.get('target_expression') or {}).get('operator', 'ANY')} of {', '.join(targets)})",
        f"modality: {', '.join(sg.get('modalities') or []) or 'none'}",
        f"therapeutic area: {', '.join(sg.get('therapeutic_areas') or []) or 'none'}",
        f"indication: {', '.join(sg.get('indications') or []) or 'none'}",
        f"minimum stage: {floor.get('minimum_stage') or 'none'}",
    ]
    if floor.get("human_poc_required"):
        enforced.append(
            "human proof-of-concept required — but the gate reads prose efficacy statements and has "
            "no validated confirmation route, so a PASS is an unverified claim"
        )
    not_enforced = list(context.get("unenforced_requirements") or [])
    caps = sg.get("capability_constraints") or {}
    if not any(caps.values()):
        not_enforced.append(
            "No manufacturing, delivery or commercial constraint was expressible in this run."
        )
    if not any((sg.get("clinical_effect_bar") or {}).values()):
        not_enforced.append(
            "No clinical effect bar (endpoint, effect size, comparator) was enforced."
        )
    if not floor.get("human_poc_required"):
        not_enforced.append(
            "Human proof-of-concept was not required (and has no validated confirmation route)."
        )
    if not sg.get("acceptable_deal_routes"):
        not_enforced.append("Deal route, rights and geography were not enforced.")
    return StrategicGap(
        question=context.get("question") or f"Find external assets for {', '.join(targets)}",
        rationale=context.get("rationale") or "No business rationale was supplied with this run.",
        targets=targets,
        modalities=tuple(sg.get("modalities") or ()),
        indications=tuple(sg.get("indications") or ()),
        therapeutic_areas=tuple(sg.get("therapeutic_areas") or ()),
        minimum_stage=floor.get("minimum_stage"),
        enforced=tuple(enforced),
        not_enforced=tuple(not_enforced),
    )


_ELIGIBILITY = {"ELIGIBLE": "Meets", "EXCLUDED": "Fails", "UNRESOLVED": "Unknown"}


def _eligibility(disposition: str, gates: tuple[GateRow, ...], efficacy: Assessed) -> str:
    label = _ELIGIBILITY.get(disposition, "Unknown")
    poc_pass = any(g.requirement == _HUMAN_POC_REQUIREMENT and g.status == "PASS" for g in gates)
    if label == "Meets" and poc_pass and efficacy.status is not EvidenceStatus.SUPPORTED:
        # The gate is unchanged; the reader is told what its PASS rests on.
        return "Meets (relies on unverified human-PoC)"
    return label


def _card(entry: dict, gap: StrategicGap, result: dict | None) -> CandidateCard:
    modality, discovery, record = _modality(entry, gap.modalities)
    parts = {
        "company": _company(entry),
        "target": _target(entry, gap.targets),
        "modality": modality,
        "stage": _stage(entry),
        "human_efficacy": _human_efficacy(entry["asset_id"], result),
        "discovery_modality": discovery,
    }
    gates = _gates(entry["asset_id"], result)
    if parts["target"].status is EvidenceStatus.UNKNOWN and any(
        g.requirement == "target.expression" and g.status == "PASS" for g in gates
    ):
        # Two engine layers disagree; show both rather than pick one.
        parts["target"] = parts["target"].model_copy(
            update={
                "basis": parts["target"].basis
                + ". The target gate nevertheless PASSED on a construct-level "
                "fact read from text; treat as unconfirmed until an authority or product source names it"
            }
        )
    if parts["modality"].status is EvidenceStatus.SUPPORTED and any(
        g.requirement == "modality.required" and g.status == "UNKNOWN" for g in gates
    ):
        parts["modality"] = parts["modality"].model_copy(
            update={
                "basis": parts["modality"].basis
                + ". The modality gate is nevertheless UNKNOWN (it reads a different, text-derived "
                "fact); the authority class is shown, the gate is unchanged"
            }
        )
    conflicts = tuple(
        f"{label}: shown {a.status.value}, engine gate {g.status}"
        for label, a, req in (
            ("Target", parts["target"], "target.expression"),
            ("Modality", parts["modality"], "modality.required"),
            ("Human efficacy", parts["human_efficacy"], _HUMAN_POC_REQUIREMENT),
        )
        for g in gates
        if g.requirement == req
        and (
            (g.status == "PASS" and a.status is not EvidenceStatus.SUPPORTED)
            or (g.status == "UNKNOWN" and a.status is EvidenceStatus.SUPPORTED)
        )
    )
    failed = tuple(
        f"{m.group(1)}: {m.group(2)}"
        for r in entry["review_reasons"]
        if (m := _FAIL_REASON.match(r))
    ) or tuple(f"{g.requirement}: {g.rationale}" for g in gates if g.status == "FAIL")
    return CandidateCard(
        asset_id=entry["asset_id"],
        name=display_name(entry["name"]),
        position=entry["position"],
        eligibility=_eligibility(entry["disposition"], gates, parts["human_efficacy"]),
        disposition=entry["disposition"],
        why=entry["why"][0] if entry["why"] else "",
        authority_record=record,
        conflicts=conflicts,
        gates=gates,
        failed_requirements=failed,
        unentailed_claims=sum(r.startswith(_ENTAILMENT) for r in entry["review_reasons"]),
        questions=_questions(parts, gap, gap.targets),
        change_triggers=_change_triggers(parts, gates),
        **parts,
    )


def _with_duplicates(cards: list[CandidateCard]) -> tuple[CandidateCard, ...]:
    by_record = Counter(c.authority_record for c in cards if c.authority_record)
    out = []
    for c in cards:
        same = (
            tuple(
                o.name
                for o in cards
                if o is not c and c.authority_record and o.authority_record == c.authority_record
            )
            if by_record.get(c.authority_record, 0) > 1
            else ()
        )
        out.append(c.model_copy(update={"duplicate_of": same}))
    return tuple(out)


def build_bd_brief(
    run: dict, *, context: dict | None = None, limit: int = DEFAULT_LIMIT, inputs=None
) -> BDBrief:
    context = context or {}
    problem, shortlist, result = run["problem"], run["shortlist"], run["result"]
    gap = _gap(problem, context)
    cards = _with_duplicates([_card(e, gap, result) for e in shortlist["entries"][:limit]])
    excluded = tuple(_card(e, gap, result) for e in shortlist["excluded"])
    review_first = tuple(
        c.name
        for c in cards
        if c.eligibility != "Fails"
        and c.target.status is EvidenceStatus.SUPPORTED
        and c.modality.status is not EvidenceStatus.CONTRADICTORY
    )
    engine_eligible = tuple(c.name for c in cards if c.eligibility.startswith("Meets"))
    unresolved = tuple(
        c.name for c in cards if c.eligibility == "Unknown" and c.name not in review_first
    )
    held_back = tuple(
        display_name(e["name"])
        for e in shortlist.get("deferred", [])
        if e["target_status"] == "CONFIRMED_TARGET"
    )
    unknown_gates = Counter(g.requirement for c in cards for g in c.gates if g.status == "UNKNOWN")
    if unknown_gates:
        req, n = unknown_gates.most_common(1)[0]
        next_action = (
            f"Resolve `{req}` by reading the cited sources: it is UNKNOWN for {n} of {len(cards)} shown "
            "candidates and is what keeps them out of the eligible set."
            + (" Start with the candidates under 'review first'." if review_first else "")
            + (
                " Human-PoC has no validated automatic route, so this is manual reading of the "
                "cited passages and registry results."
                if req == _HUMAN_POC_REQUIREMENT
                else ""
            )
        )
    elif not cards:
        next_action = "The run returned no reviewable candidates; the search cannot answer this question as posed."
    else:
        next_action = (
            "Work through the per-candidate diligence questions, starting with 'review first'."
        )
    counts = dict(shortlist.get("counts", {}))
    n_target = sum(c.target.status is EvidenceStatus.SUPPORTED for c in cards)
    n_conflict = sum(bool(c.conflicts) for c in cards)
    summary = (
        f"The engine found {counts.get('total_candidates', len(cards))} candidate names; "
        f"{counts.get('eligible', 0)} passed every gate. {len(cards)} reviewable candidates are shown.",
        f"Of those, {n_target} have the requested target confirmed by an authority record; "
        f"{len(cards) - n_target} are on the list only because they were found while searching for it.",
        "No human efficacy is confirmed for any candidate: efficacy passages are unverified quotations.",
        f"{n_conflict} candidates have an engine gate that disagrees with the displayed evidence status "
        "(flagged on each card).",
        "Approval status and rights holders are not represented; check whether each candidate is "
        "already marketed or partnered before treating it as an external opportunity.",
    )
    limitations = (
        "Development demonstration on a frozen non-holdout run; not a validated scientific product.",
        f"Run status {shortlist.get('run_status')}: sources marked as blind spots were never searched; "
        "absent assets may simply be unseen.",
        "Eligibility is the engine's gate disposition. 'Review first' only means the target is "
        "authority-supported and the modality is not contradicted; it is not a recommendation or score.",
        "Human-PoC has no validated automatic confirmation route; efficacy passages are shown for reading only.",
        "Company lists are registry sponsors and collaborators, not rights holders.",
        "Stage is the most advanced trial phase seen in registry/publication records; marketing "
        "approval is not represented, so approved products appear at their latest trial phase.",
        "Trade names and INNs are not consolidated; the same product can appear twice "
        "(same authority record is flagged).",
        f"{counts.get('low_support', 0)} low-support nominations were held back by the engine and are not shown.",
    )
    return BDBrief(
        title=context.get("title") or f"BD screening brief — {problem['problem_id']}",
        run_id=shortlist["run_id"],
        problem_id=shortlist["problem_id"],
        as_of_date=shortlist["as_of_date"],
        run_status=shortlist.get("run_status", ""),
        gap=gap,
        candidates=cards,
        excluded=excluded,
        counts=counts,
        blind_spots=tuple(shortlist.get("blind_spots", ())),
        summary=summary,
        engine_eligible=engine_eligible,
        review_first=review_first,
        unresolved=unresolved,
        held_back_notable=held_back,
        next_action=next_action,
        limitations=limitations,
        inputs=dict(inputs or {}),
    )


# --------------------------------------------------------------------------- checks


def usefulness_checks(brief: BDBrief) -> dict[str, bool]:
    """Mechanical development checks of the seven usefulness questions."""

    cards = brief.candidates
    facts = [f for c in cards for f in (c.target, c.modality, c.stage, c.company, c.human_efficacy)]
    return {
        "1_strategic_question_stated": bool(brief.gap.question and brief.gap.targets),
        "2_candidates_named": bool(cards) and all(c.name for c in cards),
        "3_sources_openable": all(
            any(s.url for f in (c.stage, c.company) for s in f.sources) for c in cards
        ),
        "4_status_on_every_fact": all(isinstance(f.status, EvidenceStatus) for f in facts),
        "5_inclusion_reason_every_candidate": all(c.why for c in cards)
        and all(c.failed_requirements for c in brief.excluded),
        "6_followup_every_candidate": all(c.questions for c in cards),
        "7_no_unsupported_conclusions": all(
            c.human_efficacy.status is not EvidenceStatus.SUPPORTED for c in cards
        )
        and not any(f.status is EvidenceStatus.SUPPORTED and f.value is None for f in facts),
    }


# --------------------------------------------------------------------------- rendering

_BADGE = {
    EvidenceStatus.SUPPORTED: "✅ Supported",
    EvidenceStatus.UNVERIFIED: "⚠️ Unverified",
    EvidenceStatus.UNKNOWN: "❔ Unknown",
    EvidenceStatus.CONTRADICTORY: "❌ Contradictory",
}


def _md_sources(sources: tuple[Source, ...]) -> str:
    return ", ".join(f"[{s.label}]({s.url})" if s.url else s.label for s in sources) or "—"


def _cell(a: Assessed) -> str:
    return f"{a.value or '—'}<br>{_BADGE[a.status]}"


def render_markdown(brief: BDBrief) -> str:
    g = brief.gap
    lines = [
        f"# {brief.title}",
        "",
        f"> Development demonstration. Run `{brief.run_id}`, as of {brief.as_of_date}, "
        f"run status **{brief.run_status}**. Not a validated product; no scores.",
        "",
        "## Summary",
        "",
        *[f"- {x}" for x in brief.summary],
        "",
        "## A. Strategic gap",
        "",
        f"**Question:** {g.question}",
        "",
        f"**Why:** {g.rationale}",
        "",
        "**What the engine enforced:**",
        "",
        *[f"- {x}" for x in g.enforced],
        "",
        "**What the engine could not understand or enforce:**",
        "",
        *[f"- {x}" for x in g.not_enforced],
        "",
        "## B. Asset landscape",
        "",
        f"{brief.counts.get('total_candidates', 0)} candidates found; {brief.counts.get('eligible', 0)} passed "
        f"every gate, {brief.counts.get('review', 0)} need review, {brief.counts.get('excluded', 0)} excluded, "
        f"{brief.counts.get('low_support', 0)} held back for low support. Showing the first "
        f"{len(brief.candidates)} reviewable candidates in the engine's declared order.",
        "",
        "| # | Asset | Eligibility | Target | Modality (authority) | Stage | Human efficacy | Sponsors (registry) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for c in brief.candidates:
        sponsors = (c.company.value or "—").split(", ")
        sponsor = ", ".join(sponsors[:2]) + (f" +{len(sponsors) - 2}" if len(sponsors) > 2 else "")
        lines.append(
            f"| {c.position} | **{c.name}** | {c.eligibility}{' ⚠️' if c.conflicts else ''} | {_cell(c.target)} | {_cell(c.modality)} | "
            f"{_cell(c.stage)} | {_badge_only(c.human_efficacy)} | {sponsor} |"
        )
    lines += ["", "## C–D. Evidence, uncertainty and technical diligence", ""]
    for c in brief.candidates:
        lines += _md_card(c)
    lines += [
        "## E. Analyst conclusion",
        "",
        "**Passed every engine gate** (read the gate basis before relying on it):",
        "",
        *([f"- {n}" for n in brief.engine_eligible] or ["- _None._"]),
        "",
        "**Review first** (target authority-supported, modality not contradicted; still Unknown on at least one gate):",
        "",
        *([f"- {n}" for n in brief.review_first] or ["- _None._"]),
        "",
        "**Unresolved** (target or modality not established):",
        "",
        *([f"- {n}" for n in brief.unresolved] or ["- _None._"]),
        "",
        f"**Excluded by the engine** ({brief.counts.get('excluded', 0)}; first {len(brief.excluded)} shown, "
        "alphabetical):",
        "",
    ]
    for c in brief.excluded:
        lines.append(
            f"- {c.name} — {'; '.join(r[:140] for r in c.failed_requirements) or 'reason not recorded'}"
        )
    if brief.held_back_notable:
        lines += [
            "",
            "**Held back for low support but authority-confirmed on at least one requested target** (check manually):",
            "",
            *[f"- {n}" for n in brief.held_back_notable],
        ]
    lines += ["", f"**Next research action:** {brief.next_action}", "", "## Limitations", ""]
    lines += [f"- {x}" for x in brief.limitations]
    if brief.blind_spots:
        lines += [
            "",
            "**Sources never searched:** " + "; ".join(_blind(b) for b in brief.blind_spots),
        ]
    if brief.inputs:
        lines += [
            "",
            "**Inputs:**",
            "",
            *[f"- `{k}` sha256 `{v}`" for k, v in sorted(brief.inputs.items())],
        ]
    return "\n".join(lines) + "\n"


def _blind(text: str) -> str:
    m = re.search(r"'([^']+)'", text)
    return m.group(1) if m else text


def _badge_only(a: Assessed) -> str:
    return _BADGE[a.status]


def _md_card(c: CandidateCard) -> list[str]:
    lines = [f"### {c.position}. {c.name} — {c.eligibility}", "", f"*Why it appeared:* {c.why}", ""]
    if c.conflicts:
        lines += [
            f"**⚠️ Engine disagreement:** {'; '.join(c.conflicts)}. Do not rely on either signal alone.",
            "",
        ]
    if c.duplicate_of:
        lines += [
            f"*Possible duplicate:* same authority record ({c.authority_record}) as {', '.join(c.duplicate_of)}.",
            "",
        ]
    lines += ["| Fact | Value | Status | Basis | Sources |", "|---|---|---|---|---|"]
    for label, a in (
        ("Target", c.target),
        ("Modality", c.modality),
        ("Stage", c.stage),
        ("Sponsors", c.company),
        ("Human efficacy", c.human_efficacy),
    ):
        value = (a.value or "—")[:120]
        lines.append(
            f"| {label} | {value} | {_BADGE[a.status]} | {a.basis} | {_md_sources(a.sources)} |"
        )
    if c.discovery_modality:
        lines += ["", f"*Modality hint from trial text (not evidence):* {c.discovery_modality}"]
    passages = [s for s in c.human_efficacy.sources if s.passage]
    if passages:
        lines += ["", "*Efficacy passages for analyst reading (unverified):*", ""]
        lines += [
            f"> {s.passage} — [{s.label}]({s.url})" if s.url else f"> {s.passage}" for s in passages
        ]
    if c.gates:
        gate_text = "; ".join(f"{g.requirement} {g.status}" for g in c.gates)
        lines += ["", f"*Gate results:* {gate_text}"]
    if c.unentailed_claims:
        lines += [
            "",
            f"*{c.unentailed_claims} extracted claims failed the citation-entailment check and are not relied on.*",
        ]
    lines += ["", "**Diligence questions** (most value-changing first):", ""]
    lines += [
        f"{i}. **{q.area}** — {q.question} _(because: {q.grounded_on})_"
        for i, q in enumerate(c.questions, 1)
    ]
    if c.change_triggers:
        lines += ["", "*What would change the assessment:* " + "; ".join(c.change_triggers)]
    return lines + [""]


_CSS = """
body{font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;max-width:1150px;margin:2em auto;padding:0 1em;color:#222;line-height:1.45}
table{border-collapse:collapse;width:100%;margin:.6em 0;font-size:.92em}th,td{border:1px solid #ccc;padding:.35em .5em;vertical-align:top;text-align:left}
th{background:#f3f3f3}.banner{background:#fff4d6;border:1px solid #e0c060;padding:.6em 1em}
.SUPPORTED{color:#11703a;font-weight:600}.UNVERIFIED{color:#9a6400;font-weight:600}.UNKNOWN{color:#666;font-weight:600}.CONTRADICTORY{color:#b00020;font-weight:600}
details{border:1px solid #ddd;margin:.5em 0;padding:.3em .8em;border-radius:4px}summary{cursor:pointer;font-weight:600}
blockquote{border-left:3px solid #e0c060;margin:.4em 0;padding:.2em .8em;background:#fffbea}.small{font-size:.88em;color:#555}
"""


def _h(text: object) -> str:
    return html.escape(str(text), quote=True)


def _h_badge(a: Assessed) -> str:
    return f'<span class="{a.status.value}">{_h(_BADGE[a.status])}</span>'


def _h_sources(sources: tuple[Source, ...]) -> str:
    return (
        ", ".join(
            f'<a href="{_h(s.url)}" target="_blank" rel="noopener">{_h(s.label)}</a>'
            if s.url
            else _h(s.label)
            for s in sources
        )
        or "—"
    )


def _h_list(items) -> str:
    return (
        "<ul>" + "".join(f"<li>{_h(x)}</li>" for x in items) + "</ul>"
        if items
        else "<p><em>None.</em></p>"
    )


def render_html(brief: BDBrief) -> str:
    g = brief.gap
    out = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>{_h(brief.title)}</title><style>{_CSS}</style></head><body>",
        f"<h1>{_h(brief.title)}</h1>",
        f"<p class='banner'>Development demonstration. Run <code>{_h(brief.run_id)}</code>, as of "
        f"{_h(brief.as_of_date)}, run status <b>{_h(brief.run_status)}</b>. Not a validated product; no scores.</p>",
        "<h2>Summary</h2>" + _h_list(brief.summary),
        "<h2>A. Strategic gap</h2>",
        f"<p><b>Question:</b> {_h(g.question)}</p><p><b>Why:</b> {_h(g.rationale)}</p>",
        "<p><b>What the engine enforced:</b></p>" + _h_list(g.enforced),
        "<p><b>What the engine could not understand or enforce:</b></p>" + _h_list(g.not_enforced),
        "<h2>B. Asset landscape</h2>",
        f"<p>{brief.counts.get('total_candidates', 0)} candidates found; {brief.counts.get('eligible', 0)} passed "
        f"every gate, {brief.counts.get('review', 0)} need review, {brief.counts.get('excluded', 0)} excluded, "
        f"{brief.counts.get('low_support', 0)} held back for low support. Showing the first {len(brief.candidates)} "
        "reviewable candidates in the engine's declared order.</p>",
        "<table><tr><th>#</th><th>Asset</th><th>Eligibility</th><th>Target</th><th>Modality (authority)</th>"
        "<th>Stage</th><th>Human efficacy</th><th>Sponsors (registry)</th><th>Sources</th></tr>",
    ]
    for c in brief.candidates:
        out.append(
            f"<tr><td>{c.position}</td><td><a href='#{_h(c.asset_id)}'><b>{_h(c.name)}</b></a></td>"
            f"<td>{_h(c.eligibility)}{' ⚠️' if c.conflicts else ''}</td>"
            f"<td>{_h(c.target.value or '—')}<br>{_h_badge(c.target)}</td>"
            f"<td>{_h(c.modality.value or '—')}<br>{_h_badge(c.modality)}</td>"
            f"<td>{_h(c.stage.value or '—')}<br>{_h_badge(c.stage)}</td>"
            f"<td>{_h_badge(c.human_efficacy)}</td>"
            f"<td class='small'>{_h(c.company.value or '—')}</td>"
            f"<td class='small'>{_h_sources(c.stage.sources[:2])}</td></tr>"
        )
    out.append("</table><h2>C–D. Evidence, uncertainty and technical diligence</h2>")
    for c in brief.candidates:
        out.append(_h_card(c))
    out += [
        "<h2>E. Analyst conclusion</h2>",
        "<p><b>Passed every engine gate</b> (read the gate basis before relying on it):</p>",
        _h_list(brief.engine_eligible),
        "<p><b>Review first</b> (target authority-supported, modality not contradicted; still Unknown on at least one gate):</p>",
        _h_list(brief.review_first),
        "<p><b>Unresolved</b> (target or modality not established):</p>",
        _h_list(brief.unresolved),
        f"<p><b>Excluded by the engine</b> ({brief.counts.get('excluded', 0)}; first {len(brief.excluded)} shown, alphabetical):</p>",
        _h_list(
            [
                f"{c.name} — {'; '.join(r[:140] for r in c.failed_requirements) or 'reason not recorded'}"
                for c in brief.excluded
            ]
        ),
    ]
    if brief.held_back_notable:
        out += [
            "<p><b>Held back for low support but authority-confirmed on at least one requested target</b> (check manually):</p>",
            _h_list(brief.held_back_notable),
        ]
    out += [
        f"<p><b>Next research action:</b> {_h(brief.next_action)}</p>",
        "<h2>Limitations</h2>",
        _h_list(brief.limitations),
    ]
    if brief.blind_spots:
        out.append(
            "<p><b>Sources never searched:</b> "
            + _h("; ".join(_blind(b) for b in brief.blind_spots))
            + "</p>"
        )
    if brief.inputs:
        out.append(
            "<p class='small'><b>Inputs:</b> "
            + _h("; ".join(f"{k} sha256 {v}" for k, v in sorted(brief.inputs.items())))
            + "</p>"
        )
    out.append("</body></html>")
    return "\n".join(out) + "\n"


def _h_card(c: CandidateCard) -> str:
    rows = "".join(
        f"<tr><td>{label}</td><td>{_h((a.value or '—')[:160])}</td><td>{_h_badge(a)}</td>"
        f"<td class='small'>{_h(a.basis)}</td><td class='small'>{_h_sources(a.sources)}</td></tr>"
        for label, a in (
            ("Target", c.target),
            ("Modality", c.modality),
            ("Stage", c.stage),
            ("Sponsors", c.company),
            ("Human efficacy", c.human_efficacy),
        )
    )
    parts = [
        f"<details id='{_h(c.asset_id)}' open><summary>{c.position}. {_h(c.name)} — {_h(c.eligibility)}</summary>",
        f"<p><i>Why it appeared:</i> {_h(c.why)}</p>",
    ]
    if c.conflicts:
        parts.append(
            f"<p class='UNVERIFIED'>Engine disagreement: {_h('; '.join(c.conflicts))}. Do not rely on either signal alone.</p>"
        )
    if c.duplicate_of:
        parts.append(
            f"<p><i>Possible duplicate:</i> same authority record ({_h(c.authority_record)}) as {_h(', '.join(c.duplicate_of))}.</p>"
        )
    parts.append(
        "<table><tr><th>Fact</th><th>Value</th><th>Status</th><th>Basis</th><th>Sources</th></tr>"
        + rows
        + "</table>"
    )
    if c.discovery_modality:
        parts.append(
            f"<p class='small'><i>Modality hint from trial text (not evidence):</i> {_h(c.discovery_modality)}</p>"
        )
    passages = [s for s in c.human_efficacy.sources if s.passage]
    if passages:
        parts.append("<p><i>Efficacy passages for analyst reading (unverified):</i></p>")
        parts += [
            f"<blockquote>{_h(s.passage)} — {_h_sources((s,))}</blockquote>" for s in passages
        ]
    if c.gates:
        parts.append(
            "<p class='small'><i>Gate results:</i> "
            + _h("; ".join(f"{g.requirement} {g.status}" for g in c.gates))
            + "</p>"
        )
    if c.unentailed_claims:
        parts.append(
            f"<p class='small'>{c.unentailed_claims} extracted claims failed the citation-entailment check and are not relied on.</p>"
        )
    parts.append("<p><b>Diligence questions</b> (most value-changing first):</p><ol>")
    parts += [
        f"<li><b>{_h(q.area)}</b> — {_h(q.question)} <span class='small'>(because: {_h(q.grounded_on)})</span></li>"
        for q in c.questions
    ]
    parts.append("</ol>")
    if c.change_triggers:
        parts.append(
            "<p class='small'><i>What would change the assessment:</i> "
            + _h("; ".join(c.change_triggers))
            + "</p>"
        )
    parts.append("</details>")
    return "\n".join(parts)
