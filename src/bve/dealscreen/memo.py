"""One-page BD decision memo, built only from the workspace's saved results."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from bve.dealscreen import VALIDATION_GRADE, VALIDATION_WARNING
from bve.dealscreen.groups import distinct_count, identity_groups
from bve.dealscreen.rights_reader import AVAILABLE, RIGHTS_STATUS_WORDS
from bve.dealscreen.rights_words import (
    FIELD_STATEMENT,
    POSITION_WORDS,
    evidence_label,
    evidence_parties,
    evidence_quote,
    evidence_when,
    unapplied_row_words,
)
from bve.dealscreen.transaction import STALE_NOTE, TIER_WORDS
from bve.dealscreen.workspace import Workspace

_REQ_LABEL = {
    "target.expression": "target not the specified target",
    "modality.required": "modality outside the allowed set",
    "biology.mechanism_direction": "mechanism unsuitable (e.g. agonist)",
    "strategy.therapeutic_area": "therapeutic area outside scope",
    "strategy.indication": "indication outside scope",
    "evidence.phase_constraint": "below the minimum clinical phase",
    "evidence.minimum_stage": "below the minimum development stage",
    "evidence.human_poc": "human proof-of-concept requirement not met",
    "evidence.evaluable_patients": "too few evaluable patients",
}
#: Gates in words for "lacks evidence" lists (review R1v4 O-13). A buyer-declared gate not listed keeps its id.
_GATE_WORDS = {
    "target.expression": "target",
    "modality.required": "modality",
    "biology.mechanism_direction": "mechanism direction",
    "strategy.therapeutic_area": "therapeutic area",
    "strategy.indication": "indication",
    "evidence.phase_constraint": "clinical phase",
    "evidence.minimum_stage": "development stage",
    "evidence.human_poc": "human proof of concept",
    "evidence.evaluable_patients": "evaluable patients",
}


STAGE_LABEL = {0: "Discovery", 1: "Preclinical", 2: "Phase 1", 3: "Phase 2", 4: "Phase 3",
               5: "Registration", 6: "Phase 4 or marketed"}


MARKET_LABEL = {
    "US_MARKETED": "Marketed in U.S. per source",
    "MARKETED_NO_US_STATEMENT": "Marketed or approved per source (no U.S. statement)",
    "PHASE4_STUDY_ONLY": "Phase 4 study (approval jurisdiction not stated)",
}


def stage_label(screen: dict[str, Any]) -> str:
    """Stage in words; stage order 6 is split by market evidence (cycle A5 K1)."""
    if screen.get("stage_order") == 6 and screen.get("market_status") in MARKET_LABEL:
        return MARKET_LABEL[screen["market_status"]]
    if screen.get("stage_order") == 6:
        return "Phase 4 or marketed (no market evidence in source)"
    return STAGE_LABEL.get(screen.get("stage_order"), "stage unknown")  # type: ignore[arg-type]


def _m(value: float | None) -> str:
    return "n/a" if value is None else f"${value:,.0f}M"


def _compliance() -> float:
    from bve.cli.dealscreen_value import _compliance_default

    return _compliance_default()


_ACTIVITY_NOTE = {
    "INACTIVE": "; source status suggests development stopped (verify)",
    "MARKETED": "; marketed per source",
    "UNKNOWN": "; development activity not evidenced in source",
    "CONFLICTING": "; sources disagree on development status",
}


def build_memo(ws: Workspace) -> str:
    spec = ws.buyer()
    screening = ws.screening()
    funnel = screening["funnel"]
    screens = {s["asset_id"]: s for s in screening["screens"]}
    log = ws.decision_log()
    valuations = ws.valuations().get("assets", {})
    assumptions_path = ws.inputs / "valuation_assumptions.yaml"
    assumptions = yaml.safe_load(assumptions_path.read_text()) if assumptions_path.exists() else {}
    externals = {a.asset_id: a.external_id for a in ws.assets()}
    manifest = ws.import_result().manifest
    data_note = ("Synthetic landscape" if manifest.license_status == "synthetic" else
                 f"Landscape built from {manifest.license_status} sources ({manifest.allowed_use})")

    finalists = sorted(log.state.finalists, key=lambda a: screens[a]["rank"] or 10**6)
    kinds = {rec["reviewer_kind"] for rec in log.state.finalists.values()}
    eligible = [s for s in screens.values() if s["disposition"] == "ELIGIBLE"]
    rights = Counter(s["commercial"]["us_rights_status"] for s in eligible)
    exclusions = funnel["excluded_by_first_failed_requirement"]

    lines = [
        f"# BD screening memo: {spec.problem.buyer.name}",
        "",
        (f"> **{VALIDATION_GRADE}.** {VALIDATION_WARNING} {data_note}; hypothetical "
         "financial inputs. This memo is not an investment or transaction recommendation."),
        "",
        f"**Need screened.** {' '.join(spec.statement.split())}",
        "",
        f"**Funnel.** {funnel['assets_screened']} programs imported → {funnel['eligible']} scientifically "
        f"eligible, {funnel['unresolved']} unresolved (need diligence), {funnel['excluded']} excluded. "
        "Main exclusion reasons: "
        + ", ".join(f"{_REQ_LABEL.get(k, k)} ({v})" for k, v in sorted(exclusions.items(), key=lambda kv: -kv[1]))
        + ". Eligible means every hard gate passed on cited source claims (target "
        "expression, allowed modality, required biology, area, indication and phase). Unresolved means at least one gate lacks or has conflicting evidence.",
        "",
        _rights_summary(funnel["eligible"], eligible, rights),
        "",
    ]
    groups = identity_groups(ws.flags(), log)
    eligible_set = {s["asset_id"] for s in eligible}
    open_flagged = {a for f in ws.flags()
                    if log.state.identity_resolutions.get(f.flag_id, {}).get("state")
                    not in {"SAME_MOLECULE", "DIFFERENT_MOLECULE", "KEEP_SEPARATE"}
                    for a in f.asset_ids if a in eligible_set and len(set(f.asset_ids) & eligible_set) > 1}
    if open_flagged:
        funnel_line = next(i for i, line in enumerate(lines) if line.startswith("**Funnel.**"))
        lines[funnel_line] += (f" ({len(open_flagged)} of the eligible records share open identity flags "
                               "and may be the same molecule; see identity flags.)")
    eligible_ids = [s["asset_id"] for s in eligible]
    if any(a in groups for a in eligible_ids):
        lines += [
            (f"**Distinct molecules.** {len(eligible_ids)} eligible records = "
             f"at most {distinct_count(eligible_ids, groups)} distinct molecules after human-confirmed "
             "identity (records are not merged; open identity flags and unflagged duplicates are not "
             "counted as the same molecule)."),
            "",
        ]
    declared = [s for s in eligible if s.get("transaction_rank")]
    if declared:
        tiers = Counter(s["transaction"]["tier"] for s in declared)
        lines.append("**Transaction view (buyer-declared preferences; separate from science).** "
                     + ", ".join(f"{TIER_WORDS.get(k, k)} ({v})" for k, v in sorted(tiers.items()))
                     + ". No tier is a statement that rights are available; only a cited source can say "
                     "that, and it is still unverified:")
        shown = sorted(declared, key=lambda s: s["transaction_rank"])[:10]
        lines += [_transaction_line(s) for s in shown]
        if any(_no_record(s["transaction"]) for s in shown):
            lines.append("  (\"no rights record\": ask who holds rights in the buyer territory and whether any are "
                         "licensed, optioned or shared; the registry sponsor is a first contact, not the owner.)")
        listed = {s["asset_id"] for s in shown}
        others = [s for s in screens.values() if s["asset_id"] not in listed
                  and (s.get("transaction") or {}).get("evidence")]
        if others:
            lines.append(f"Rights evidence also exists for {len(others)} program(s) not listed above (see the "
                         "workbook): " + "; ".join(_other_line(s) for s in sorted(others, key=_other_order)) + ".")
        lines.append("")
    issues = _import_issue_lines(screening.get("rights_import_issues") or {}, tiers=bool(declared))
    if issues:
        lines += [*issues, ""]
    isoforms = sorted({r["observed"] + " → " + r["read_as"] for s in eligible for r in s.get("target_readings", [])})
    if isoforms:
        lines += [(f"**Target names read as genes.** {', '.join(isoforms)}: the target authority is gene-level, "
                   "so an isoform-specific claim is not checked; verify isoform selectivity in diligence."), ""]
    readings = [s for s in eligible if s.get("indication_readings")]
    if readings:
        lines += [
            f"**Indication wording read by rule.** {len(readings)} eligible program(s) have a qualified "
            "indication name read as its NCIt parent (DealScreen policy v1): "
            + "; ".join(f"{s['program_name']} ('{r['observed']}' as '{r['read_as']}')"
                        for s in readings for r in s["indication_readings"][:1])
            + ". Check the source wording if the qualifier matters to the buyer.",
            "",
        ]
    if kinds == {"HUMAN"}:
        heading = f"**Finalists: {len(finalists)} approved by a human analyst**"
    elif "AI_PREPARED" in kinds:
        heading = (f"**Candidates: {len(finalists)} prepared by an AI assistant, NOT approved by a "
                   "human analyst**")
    elif kinds == {"SYNTHETIC_FIXTURE"}:
        heading = (f"**Finalists: {len(finalists)} approved by the labelled SYNTHETIC reviewer "
                   "fixture, not a real analyst**")
    elif not finalists:
        heading = "**Finalists: none recorded**"
    else:
        heading = f"**Finalists: {len(finalists)} ({', '.join(sorted(kinds))} reviewers)**"
    lines.append(heading + " (rank order by declared preferences, reasons per program in the workbook "
                           "Screening sheet; rights shown separately):")
    for asset_id in finalists:
        s = screens[asset_id]
        flag = "" if s["disposition"] == "ELIGIBLE" else " (open scientific question)"
        twins = sorted({screens[o]["program_name"] for o in screens if o != asset_id
                        and set(screens[o].get("identity_flag_ids", [])) & set(s.get("identity_flag_ids", []))
                        and not (asset_id in groups and groups.get(o) == groups[asset_id])})
        same = sorted(screens[o]["program_name"] for o in screens
                      if o != asset_id and asset_id in groups and groups.get(o) == groups[asset_id])
        twin = (f"; same molecule as {', '.join(same)} (human-confirmed, {groups[asset_id]})" if same else "")
        twin += (f"; **identity flag: may be the same molecule as {', '.join(twins)} (not merged; do not "
                 "count separately until reviewed)**") if twins else ""
        twin += _ACTIVITY_NOTE.get(s.get("activity", ""), "")
        lines.append(f"- {s['program_name']} ({s['company']}): {stage_label(s)}{flag}; {_finalist_rights(s)}{twin}")
    lines.append("")

    lines.append("**Preliminary valuations** (BVE engine via CLI; hypothetical analyst inputs; $M rNPV):")
    not_ready = []
    for asset_id, entry in valuations.items():
        s = screens[asset_id]
        runs = {r["case"]: r for r in entry["runs"]}
        if not entry.get("selected") or not runs:
            if not entry["readiness"]["ready"]:
                not_ready.append(f"{s['program_name']} ({len(entry['readiness']['missing'])} missing)")
            continue
        checks = {case: r.get("scenario_check") or {"reliable": False, "status": "NOT CHECKED"}
                  for case, r in runs.items()}
        if not all(c["reliable"] for c in checks.values()):
            lines.append(f"- {s['program_name']}: valuation BLOCKED (unexplained scenario ordering); "
                         "not shown.")
            continue
        base = runs["standalone"]["summary"]
        deals = "; ".join(f"{case} {_m(r['summary']['rnpv_millions'])}"
                          for case, r in runs.items() if case != "standalone")
        block = (assumptions or {}).get("assets", {}).get(externals[asset_id], {})
        market = block.get("market", {})
        lines.append(
            f"- {s['program_name']}: bear / base / bull {_m(base['bear_rnpv_millions'])} / "
            f"{_m(base['base_rnpv_millions'])} / {_m(base['bull_rnpv_millions'])} before deal terms"
            + (f"; to the buyer after terms: {deals}" if deals else "")
            + f". Drivers: {market.get('addressable_patients_annual', 0):,} patients × "
            f"${market.get('net_price_per_patient_usd', 0):,.0f} × {market.get('peak_penetration', 0):.0%} "
            f"peak share × {_compliance():.2f} compliance (engine default); P(approval) "
            f"{base['cumulative_success_probability']:.0%}."
            + (" Scenarios are out of label order because the program is cost-dominated at these inputs "
               "(value-destroying, not a computation error)."
               if any(c["status"] != "ORDERED" for c in checks.values()) else "")
        )
    if not_ready:
        lines.append(f"- NOT READY FOR VALUATION (no invented inputs): {', '.join(not_ready)}.")
    if not any(e.get("runs") for e in valuations.values()):
        lines.append("- No valuation was run. A valuation runs only for a finalist that a HUMAN reviewer "
                     "approved and selected for valuation, with READY inputs.")
    lines.append("")

    assertions = list(log.state.assertions.values())
    if assertions:
        asserters = sorted({a["reviewer_kind"] for a in assertions})
        overrides = sum(len(s.get("overrides", [])) for s in screens.values())
        changed = [s for s in screens.values() if s.get("assertion_effects")]
        overturned = [s["program_name"] for s in screens.values()
                      if any(e["overturns_source_fail"] for e in s.get("assertion_effects", []))]
        idle = [s for s in screens.values() if s.get("analyst_assertions") and not s.get("assertion_effects")]
        # Rights-field assertions change no gate; they feed the transaction view (review R1v3, memo "no effect").
        feeds = [s for s in idle if any(a["field"] in _RIGHTS_FIELDS for a in s["analyst_assertions"])]
        quiet = [s["program_name"] for s in idle if s not in feeds]
        lines.append(
            f"**Analyst-entered facts.** {len(assertions)} cited assertion(s) by {', '.join(asserters)} "
            f"reviewer(s) changed gate decisions for {len(changed)} program(s); {overrides} override a "
            "different source value"
            + (f"; **source FAILs overturned: {', '.join(overturned)}**" if overturned else "")
            + (f"; no effect on: {', '.join(quiet)}" if quiet else "")
            + ("; rights assertions changed no gate but feed the transaction view for: "
               + ", ".join(f"{s['program_name']} ({_tier_words(s)})" for s in feeds) if feeds else "")
            + ". Citations are in the Diligence sheet.")
        lines.append("")
    unresolved = [s for s in screens.values() if s["disposition"] == "UNRESOLVED"]
    open_gates = Counter(
        d["requirement_id"] for s in unresolved for d in s["decisions"]
        if (d["analyst_override"] or d["status"]) == "UNKNOWN"
    )
    rights_open = [screens[a]["program_name"] for a in finalists
                   if (screens[a].get("transaction") or {}).get("rights_position") != _AVAILABILITY_POSITION]
    lines.append("**Investigate next.**")
    finding_state = log.state.findings
    pending = [f for f in ws.findings()
               if f.provider.startswith("ai_proposal") and finding_state.get(f.finding_id, "PROPOSED") == "PROPOSED"]
    if pending:
        lines.append(f"- {len(pending)} cited fact(s) proposed by an AI assistant await human confirmation "
                     "(they change nothing until confirmed; re-check each quote at its URL).")
    if finalists:
        lines.append(f"- Confirm ownership and U.S. rights for {len(rights_open)} of {len(finalists)} listed "
                     f"programs ({len(finalists) - len(rights_open)} with availability stated).")
    else:
        lines.append("- Confirm ownership and rights in the buyer territory for any program you shortlist; the "
                     "rights questions are in the workbook.")
    conflicted = [s["program_name"] for s in eligible
                  if (s.get("transaction") or {}).get("rights_position") == "CONFLICTING_EVIDENCE"]
    if conflicted:
        lines.append(f"- Resolve the conflicting rights evidence for {', '.join(conflicted)} (questions above).")
    for asset_id in finalists:
        unknown = [d["requirement_id"] for d in screens[asset_id]["decisions"]
                   if (d["analyst_override"] or d["status"]) == "UNKNOWN"]
        if unknown:
            lines.append(f"- {screens[asset_id]['program_name']}: resolve the "
                         f"{', '.join(_GATE_WORDS.get(u, u) for u in unknown)} gate{'s' if len(unknown) > 1 else ''}.")
    if unresolved:
        lines.append(f"- Work the {len(unresolved)}-program unresolved queue; gates lacking evidence: "
                     + ", ".join(f"{_GATE_WORDS.get(k, k)} ({v})" for k, v in open_gates.most_common()) + ".")
    lines.append("- Replace hypothetical market and deal inputs with owned, sourced assumptions.")
    return "\n".join(lines) + "\n"


def write_memo(ws: Workspace, path: str | Path) -> dict[str, Any]:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = build_memo(ws)
    target.write_text(text, encoding="utf-8")
    out = {"markdown": str(target), "words": len(text.split())}
    try:
        from bve.reporting.export import markdown_to_docx

        docx = target.with_suffix(".docx")
        markdown_to_docx(text, docx, title="BD screening memo")
        out["docx"] = str(docx)
    except Exception as exc:  # noqa: BLE001 - docx is a convenience copy
        out["docx_error"] = str(exc)
    return out


_GENERIC_REASONS = ("no rights or deal record", "availability not evidenced")
#: Analyst-assertable fields that feed the transaction view, not a gate.
_RIGHTS_FIELDS = frozenset({"us_rights", "us_rights_holder", "partnerships"})
_AVAILABILITY_POSITION = "AVAILABILITY_STATED_BY_SOURCE_UNVERIFIED"


def _tier_words(s: dict[str, Any]) -> str:
    tier = (s.get("transaction") or {}).get("tier", "NOT_DECLARED")
    return TIER_WORDS.get(tier, tier)


def _import_issue_lines(issues: dict[str, Any], *, tiers: bool) -> list[str]:
    """Rights rows applied to no program, with what each names (review R1v3 E3-ids; R1v4 O-9, R-lost): never only
    on the import console. ``tiers``: transaction preferences are declared, so the guard on the top tiers applies."""
    out: list[str] = []
    unlinked = issues.get("unlinked_rows") or []
    if unlinked:
        near = any(u.get("near_programs") for u in unlinked)
        out.append(f"**Rights rows attached to no program.** {len(unlinked)} accepted row(s) name a program id that "
                   "matches no landscape program: "
                   + "; ".join(f"row {u['row']} ({unapplied_row_words(u)})" for u in unlinked[:5])
                   + ("; and more in the workbook" if len(unlinked) > 5 else "")
                   + ". Correct the id, or confirm the program is outside this landscape"
                   + ("; a program whose id is close is kept out of the top two transaction tiers until then"
                      if near and tiers else "") + ".")
    rejected = issues.get("unattributed_rejected_rows") or []
    if rejected:
        out.append(f"**Rejected rights rows not attached to any program.** {len(rejected)} row(s): "
                   + "; ".join(f"row {u['row']} ({unapplied_row_words(u)}; rejected: {'; '.join(u['reasons'])})"
                               for u in rejected[:5])
                   + ("; and more in the workbook" if len(rejected) > 5 else "")
                   + ". Any program may be affected"
                   + (", so no program is placed in the top two transaction tiers until they are corrected and "
                      "re-imported." if tiers else "; correct them and re-import the rights file."))
    return out


def _no_record(t: dict[str, Any]) -> bool:
    return t.get("rights_position") == "NO_RIGHTS_EVIDENCE" and not t.get("evidence")


_MEMO_EVIDENCE = 3  # evidence rows shown per program; the workbook has all of them
_MEMO_QUOTE = 200  # characters of each quote shown; the workbook shows up to 1,000


def _position_words(t: dict[str, Any]) -> str:
    code = t.get("rights_position") or "NO_RIGHTS_EVIDENCE"
    return POSITION_WORDS.get(code, code.replace("_", " ").lower()) + (" (stale evidence)" if t.get("stale") else "")


def _evidence_line(e: dict[str, Any]) -> str:
    quote = evidence_quote(e, _MEMO_QUOTE)
    return (f"  - evidence ({evidence_label(e)}): {evidence_when(e)} {e.get('type_words') or e['type'].lower()}, "
            f"{evidence_parties(e)}, {e.get('territory') or 'territory not stated'} <{e['source']}>"
            + (f' "{quote}"' if quote else ""))


def _transaction_line(s: dict[str, Any]) -> str:
    """One ranked program in the transaction view: tier, position, why, evidence (with row and quote) and what
    to ask. Tiers and positions are in words; the codes are in the workbook."""
    t = s["transaction"]
    head = f"- #{s['transaction_rank']} {s['program_name']}: {TIER_WORDS.get(t['tier'], t['tier'])}"
    if _no_record(t):
        why = [r for r in t["reasons"] + t["notes"] if not r.startswith(_GENERIC_REASONS)]
        return (f"{head}; no rights record" + (f" ({'; '.join(why)})" if why else "")
                + f"; first contact: registry sponsor '{s['company']}'")
    why = [x for x in t["reasons"] + t["notes"] if x != STALE_NOTE]  # the position words already say "stale"
    out = [f"{head}; rights position: {_position_words(t)} ({'; '.join(why)})"]
    evidence = t.get("evidence", [])
    out += [_evidence_line(e) for e in evidence[:_MEMO_EVIDENCE]]
    if len(evidence) > _MEMO_EVIDENCE:
        out.append(f"  - and {len(evidence) - _MEMO_EVIDENCE} more evidence row(s) in the workbook")
    if t.get("diligence_questions"):
        out.append(f"  - ask: {' '.join(t['diligence_questions'])}")
    return "\n".join(out)


def _other_order(s: dict[str, Any]) -> tuple[int, int, str]:
    order = {"ELIGIBLE": 0, "UNRESOLVED": 1}.get(s["disposition"], 2)
    return order, s.get("transaction_rank") or 10**6, s["program_name"]


def _finalist_rights(s: dict[str, Any]) -> str:
    """A finalist's rights in a few words: the position from the rights file when it has rows for the program, else
    the landscape field as read. A field that says "unknown" never hides a recorded third-party grant."""
    t = s.get("transaction") or {}
    if any(e.get("type") != FIELD_STATEMENT for e in t.get("evidence", [])):
        return f"rights position: {_position_words(t)}"
    return f"U.S. rights {s['commercial']['display'].lower()}"


def _other_line(s: dict[str, Any]) -> str:
    """A program with rights evidence outside the top ten: position, holder, newest dated evidence, the first
    reason for the position (not a buyer-preference match), the first check that keeps it out of the top tiers, how
    many more reasons the workbook holds, and where the evidence is (review R1v3 AC10, R1v4 O-11)."""
    t = s["transaction"]
    where = (f"eligible, transaction #{s['transaction_rank']}" if s["disposition"] == "ELIGIBLE"
             and s.get("transaction_rank") else s["disposition"].lower())
    holder = t.get("rights_holder_per_evidence")
    evidence = t.get("evidence", [])
    rows = ", ".join(str(e.get("row")) for e in evidence if e.get("type") != FIELD_STATEMENT)
    fields = sorted({evidence_label(e) for e in evidence if e.get("type") == FIELD_STATEMENT})
    dates = [str(e.get("date") or e.get("source_date")) for e in evidence if e.get("date") or e.get("source_date")]
    reasons = [r for r in (t.get("position_reasons") or t.get("reasons", [])) if not r.startswith(_GENERIC_REASONS)]
    blockers = list(t.get("top_tier_blockers") or [])
    why = reasons[:1] + [f"not counted for the top tiers: {b}" for b in blockers[:1]]
    more = len(reasons) + len(blockers) - len(why)
    return (f"{s['program_name']} ({where}): {_position_words(t)}" + (f", {holder}" if holder else "")
            + (f", newest evidence {max(dates)}" if dates else ", no dated evidence")
            + (f" ({'; '.join(why)})" if why else "")
            + (f" (and {more} more reason(s) in the workbook)" if more else "")
            + (f" [rights rows {rows}]" if rows else "") + (f" [{', '.join(fields)}]" if fields else ""))


def _rights_summary(n_eligible: int, eligible: list[dict[str, Any]], rights: Counter[str]) -> str:
    """Cycle R1: summarise rights from the cited evidence when there is any, else from the landscape field. Every
    sentence is computed: the availability sentence counts the programs it describes (review R1v4 O-8, O-13)."""
    txns = [s.get("transaction") or {} for s in eligible]
    positions = Counter(t.get("rights_position", "NO_RIGHTS_EVIDENCE") for t in txns)
    holders = sum(1 for s, t in zip(eligible, txns, strict=True)
                  if t.get("rights_holder_per_evidence") or s["commercial"].get("us_rights_holder"))
    if any(t.get("evidence") for t in txns):
        body = ("the rights position in the buyer territory per cited evidence is: "
                + ", ".join(f"{POSITION_WORDS.get(k, k)} ({v})" for k, v in sorted(positions.items())))
    else:
        body = "the landscape U.S.-rights field reads: " + ", ".join(
            f"{RIGHTS_STATUS_WORDS.get(k, k)} ({v})" for k, v in sorted(rights.items()))
    held = (f" A holder or labeler is named in cited evidence for {holders} (an FDA labeler is not the owner, and "
            "neither says whether rights are available)." if holders else "")
    available = [t for t in txns if t.get("rights_position") == _AVAILABILITY_POSITION]
    checked = [t for t in available
               if not (t.get("top_tier_blockers") or t.get("stale") or t.get("rights_rows_not_applied"))]
    if available:
        stated = (f" A source states availability for {len(available)} (read by rule, unverified); {len(checked)} "
                  "pass every rights check (a recent dated statement, attributed to the program's company or to no "
                  "other party, contradicted by no other cited evidence and by no rights row left unapplied)"
                  + (f" and {len(available) - len(checked)} fail one (see the workbook)"
                     if len(checked) < len(available) else "") + ".")
    elif rights.get(AVAILABLE):
        stated = (" None reaches the availability position: a vendor field reading \"available\" is unverified and "
                  "not counted.")
    else:
        stated = " None reaches the availability position."
    return f"**Rights are a separate question.** Of the {n_eligible} eligible programs, {body}.{held}{stated}"
