"""Excel deliverable: a companion workbook, never an overwrite of an analyst's file.

If the target path exists and is not a DealScreen workbook (no README marker), export
refuses; it never edits an analyst workbook or its formulas. Replacing an earlier DealScreen
workbook also needs ``replace_own=True``.

Every number in "Valuation Scenarios" and "Deal Comparison" is copied from the saved
``valuation.json`` produced by the BVE CLI.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bve.dealscreen import DEALSCREEN_VERSION, VALIDATION_GRADE, VALIDATION_WARNING
from bve.dealscreen.groups import identity_groups
from bve.dealscreen.screening import explain_preference_key
from bve.dealscreen.valuation_handoff import _compliance_limitation
from bve.dealscreen.workspace import Workspace

MARKER = "BVE DealScreen companion workbook"
_HEADER_FILL = "1F3864"
_MILLIONS = '#,##0.0;[Red]-#,##0.0'


class WorkbookExists(FileExistsError):
    pass


def _is_dealscreen_workbook(path: Path) -> bool:
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(path, read_only=True)
    except Exception:  # noqa: BLE001 - unreadable means "not ours"
        return False
    try:
        if "README" not in workbook.sheetnames:
            return False
        first = workbook["README"]["A1"].value
        return isinstance(first, str) and first.startswith(MARKER)
    finally:
        workbook.close()


def _sheet(workbook, title: str, headers: list[str], rows: list[list[Any]], *,
           note: str | None = None, widths: dict[int, int] | None = None,
           money_cols: tuple[int, ...] = ()):
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    ws = workbook.create_sheet(title)
    start = 1
    if note:
        ws.cell(row=1, column=1, value=note).font = Font(italic=True, color="7F7F7F")
        start = 2
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=start, column=col, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=_HEADER_FILL)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    for r, row in enumerate(rows, start=start + 1):
        for c, value in enumerate(row, start=1):
            if isinstance(value, (list, tuple)):
                value = "; ".join(str(v) for v in value)
            elif isinstance(value, dict):
                value = "; ".join(f"{k}={v}" for k, v in value.items())
            cell = ws.cell(row=r, column=c, value=value)
            if c in money_cols and isinstance(value, (int, float)):
                cell.number_format = _MILLIONS
    ws.freeze_panes = ws.cell(row=start + 1, column=2)
    if rows:
        ws.auto_filter.ref = f"A{start}:{get_column_letter(len(headers))}{start + len(rows)}"
    for col in range(1, len(headers) + 1):
        width = (widths or {}).get(col) or min(48, max(10, len(str(headers[col - 1])) + 2))
        ws.column_dimensions[get_column_letter(col)].width = width
    return ws


def export_workbook(ws: Workspace, path: str | Path, *, replace_own: bool = False) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    target = Path(path)
    if target.exists():
        if not _is_dealscreen_workbook(target):
            raise WorkbookExists(
                f"{target} exists and is not a DealScreen workbook; it will not be modified. "
                "Choose a new path for the companion workbook."
            )
        if not replace_own:
            raise WorkbookExists(f"{target} exists; pass replace_own=True to replace this DealScreen workbook")

    imported = ws.import_result()
    screening = ws.screening()
    screens = screening["screens"]
    by_id = {s["asset_id"]: s for s in screens}
    assets = {a.asset_id: a for a in imported.assets}
    log = ws.decision_log()
    findings = ws.findings()
    valuations = ws.valuations()
    flags = ws.flags()
    spec = ws.buyer()

    wb = Workbook()
    readme = wb.worksheets[0]
    readme.title = "README"
    lines = [
        f"{MARKER} ({DEALSCREEN_VERSION})",
        f"Validation grade: {VALIDATION_GRADE}. {VALIDATION_WARNING}",
        f"Buyer need screened: {spec.statement}",
        (f"Dataset: {imported.manifest.dataset_version} ({imported.manifest.license_status}, "
         f"allowed use: {imported.manifest.allowed_use})"),
        "Imported values are SOURCE-PROVIDED vendor assertions, not BVE confirmation.",
        "Scientific disposition (Screening) and commercial rights status are independent.",
        ("Finalists exist only through logged analyst decisions; reviewer_kind SYNTHETIC_FIXTURE "
         "marks the demo's labelled synthetic reviewer, not a real analyst."),
        ("Valuation figures are copied from BVE's saved valuation.json files; deal cases use a "
         "PROTOTYPE CLI awaiting Lane 1 sign-off. Financial inputs are hypothetical."),
        "This workbook is a separate companion file; it does not modify any analyst workbook.",
        f"Generated: {datetime.now(UTC).isoformat(timespec='seconds')}",
    ]
    for i, line in enumerate(lines, start=1):
        readme.cell(row=i, column=1, value=line).font = Font(bold=(i <= 2))
    readme.column_dimensions["A"].width = 140

    # 1. Landscape ---------------------------------------------------------------------
    raw_headers: list[str] = []
    raw_rows: list[dict[str, str]] = [r.raw for r in imported.rows] + [r.raw for r in imported.rejected]
    for raw in raw_rows:
        for key in raw:
            if key not in raw_headers:
                raw_headers.append(key)
    row_asset = {n: a.asset_id for a in imported.assets for n in a.row_numbers}
    landscape_rows: list[list[Any]] = []
    for row in imported.rows:
        landscape_rows.append(["IMPORTED", row.row_number, row_asset.get(row.row_number), row.row_hash[:16],
                               *[row.raw.get(h, "") for h in raw_headers]])
    for rej in imported.rejected:
        landscape_rows.append([f"REJECTED: {' | '.join(rej.reasons)}", rej.row_number, None, rej.row_hash[:16],
                               *[rej.raw.get(h, "") for h in raw_headers]])
    for dup in imported.duplicates:
        landscape_rows.append([f"EXACT DUPLICATE of row {dup.duplicate_of_row}", dup.row_number, None,
                               dup.row_hash[:16], *[""] * len(raw_headers)])
    landscape_rows.sort(key=lambda r: r[1])
    _sheet(wb, "Landscape", ["Import status", "Source row", "DealScreen asset id", "Row hash",
                             *raw_headers], landscape_rows,
           note=f"Complete imported universe, raw values verbatim. Source system "
                f"{imported.manifest.source_system}; dataset {imported.manifest.dataset_version}.")

    # 2. Screening ---------------------------------------------------------------------
    requirement_ids: list[str] = []
    for s in screens:
        for d in s["decisions"]:
            if d["requirement_id"] not in requirement_ids:
                requirement_ids.append(d["requirement_id"])
    groups = identity_groups(ws.flags(), log)
    screening_rows = []
    order = {"ELIGIBLE": 0, "UNRESOLVED": 1, "EXCLUDED": 2}
    for s in sorted(screens, key=lambda s: (order[s["disposition"]], s["rank"] or 10**6, s["program_name"])):
        asset = assets[s["asset_id"]]
        statuses = {d["requirement_id"]: d["analyst_override"] or d["status"] for d in s["decisions"]}
        cited = sorted({c for d in s["decisions"] for c in d["supporting_or_contradictory_claim_ids"]})
        screening_rows.append([
            s["asset_id"], s["program_name"], ", ".join(asset.aliases), s["company"], asset.external_id,
            s["disposition"], s["rank"], s["machine_recommendation"],
            *[statuses.get(r, "n/a") for r in requirement_ids],
            " | ".join(s["review_reasons"]), ", ".join(s["target_symbols"]), s["modality"],
            s["stage_order"], s["activity"], s["n_trials"],
            s["commercial"]["display"], s["commercial"].get("holder_display", "UNKNOWN"),
            ", ".join(s["commercial"]["partnerships"]),
            ", ".join(s["identity_flag_ids"]), "; ".join(cited),
            "; ".join(f"{a['field']}={a['value']} ({a['reviewer_id']}, {a['reviewer_kind']}, {a['assertion_id']})"
                      for a in s.get("analyst_assertions", [])),
            "; ".join(f"{o['field']}: {o['asserted_value']} replaces {', '.join(o['superseded_claim_ids'])}"
                      for o in s.get("overrides", [])),
            _effects_text(s),
            "; ".join(f"'{r['observed']}' read as '{r['read_as']}' ({r['qualifier']})"
                      for r in s.get("indication_readings", [])),
            groups.get(s["asset_id"], ""),
            explain_preference_key(spec, s["preference_key"], s["activity"]) if s["rank"] else "",
            "; ".join(f"{u['field']} '{u['value']}': {u.get('reason', 'not readable by the field normalizer')}"
                      for u in s.get("unreadable_claims", [])),
        ])
    _sheet(wb, "Screening", [
        "Asset id", "Program", "Aliases", "Company (per source)", "External id", "Scientific disposition",
        "Preference rank", "Machine recommendation", *[f"Gate: {r}" for r in requirement_ids],
        "Why not ELIGIBLE", "Target symbols", "Modality", "Stage order", "Activity", "Registered trials",
        "U.S. licensing availability (independent of science)", "U.S. labeler/holder named in source (not owner, not availability)",
        "Partnerships (per source)", "Identity flags",
        "Cited claim ids (asset:field:value-hash; row in Landscape)", "Analyst assertions", "Source values overridden by analyst",
        "Gate changes caused by assertions",
        "Indication names read as their NCIt parent (DealScreen policy v1)",
        "Identity group (human-confirmed same molecule; records not merged)",
        "Rank reasons (compared left to right; rule unchanged by DealScreen)",
        "Source values not used, and why",
    ], screening_rows, note=f"Gate engine: bve.se GateEngine. {screening['ranking_rule']}",
        widths={2: 26, 6: 16})

    # 3. Diligence ---------------------------------------------------------------------
    finding_state = log.state.findings
    diligence_rows: list[list[Any]] = []
    for s in screens:
        if s["disposition"] == "EXCLUDED":
            continue
        for d in s["decisions"]:
            if (d["analyst_override"] or d["status"]) == "UNKNOWN":
                diligence_rows.append([s["asset_id"], s["program_name"], "GATE_UNKNOWN", d["requirement_id"],
                                       d["rationale"], d["next_action"],
                                       "; ".join(d["supporting_or_contradictory_claim_ids"]) or "no evidence",
                                       "Source-provided evidence missing or conflicting", "OPEN", ""])
        if s["commercial"]["us_rights_status"] not in {"AVAILABLE_ANALYST_CONFIRMED"}:
            diligence_rows.append([s["asset_id"], s["program_name"], "COMMERCIAL", "us_rights",
                                   s["commercial"]["display"], "; ".join(s["commercial"]["open_questions"]),
                                   "; ".join(s["commercial"]["us_rights_claim_ids"]) or "no rights record",
                                   ("Absence of a license record is not availability"
                                    if s["commercial"]["us_rights_status"] == "UNKNOWN"
                                    else "Source-provided statement; unverified by BVE"), "OPEN", ""])
    for flag in flags:
        state = log.state.identity_flags.get(flag.flag_id, "OPEN")
        for asset_id in flag.asset_ids:
            diligence_rows.append([asset_id, by_id[asset_id]["program_name"], f"IDENTITY_{flag.kind}",
                                   flag.flag_id, flag.basis, "Decide (human): SAME_MOLECULE, DIFFERENT_MOLECULE or UNSURE; records are never merged",
                                   f"shared value {flag.shared_value!r}; relationship {flag.relationship}",
                                   "Shared codes are not identity evidence", state, flag.flag_id])
    for f in findings:
        diligence_rows.append([f.asset_id, by_id[f.asset_id]["program_name"], "AGENT_FINDING", f.field,
                               f"{f.question} -> proposed {f.proposed_value!r}", "Confirm or reject",
                               f"{f.source_title} <{f.source_url}> ({f.document_date}); span: {f.evidence_span}",
                               " | ".join(f.limitations), finding_state.get(f.finding_id, "PROPOSED"),
                               f.finding_id])
    for a in log.state.assertions.values():
        diligence_rows.append([a["asset_id"], by_id[a["asset_id"]]["program_name"], "ANALYST_ASSERTION",
                               a["field"], f"{a['field']} = {a['value']!r}", a["rationale"],
                               (f"{a['source_title']} <{a['source_url']}> ({a['source_date']}); quote: "
                               f"{a['evidence_span']}"),
                               (f"Entered by {a['reviewer_id']} ({a['reviewer_kind']}); a cited source is not "
                               "proof that its claim is true"), "ACTIVE", a["assertion_id"]])
    for o in ws.refresh().get("orphaned_decisions", []):
        diligence_rows.append(["", "", "ORPHANED_DECISION_AFTER_REFRESH", o["subject"], o["decision"],
                               "Re-review against the refreshed landscape", o["reason"],
                               "Kept in the decision log; no longer applied", "OPEN", ""])
    for asset_id, questions in log.state.diligence_requests.items():
        for q in questions:
            diligence_rows.append([asset_id, by_id[asset_id]["program_name"], "DILIGENCE_REQUEST", "", q,
                                   "Analyst-requested", "decision log", "", "OPEN", ""])
    reviewer_actions: dict[str, str] = {}
    for r in log.records:
        label = f"{r['action']} by {r['reviewer_id']} ({r['reviewer_kind']}) [{r['decision_id']}]"
        reviewer_actions[r["subject_id"]] = label
        reviewer_actions[r["decision_id"]] = label
    for item in diligence_rows:
        # Column 10 holds the subject the log would name (finding or flag id) until filled.
        item[9] = reviewer_actions.get(item[9]) or reviewer_actions.get(item[3], "")
    _sheet(wb, "Diligence", ["Asset id", "Program", "Item type", "Requirement / field", "Question / status",
                             "Next action", "Provenance", "Confidence limitations", "State",
                             "Latest reviewer action"], diligence_rows,
           note="Open questions for non-excluded assets, identity flags and agent proposals. Agent "
                "findings change nothing until confirmed in the decision log.",
           widths={5: 60, 7: 60, 8: 45})

    # 4. Finalists ---------------------------------------------------------------------
    finalist_rows = []
    for asset_id, rec in sorted(log.state.finalists.items(), key=lambda kv: by_id[kv[0]]["rank"] or 10**6):
        s = by_id[asset_id]
        finalist_rows.append([asset_id, s["program_name"], s["company"], rec["state"], s["disposition"],
                              s["rank"], s["commercial"]["display"], rec["rationale"], rec["reviewer_id"],
                              rec["reviewer_kind"], rec["timestamp"], rec["decision_id"],
                              "yes" if asset_id in log.state.valuation_selected else "no"])
    _sheet(wb, "Finalists", ["Asset id", "Program", "Company (per source)", "Approval state",
                             "Scientific disposition", "Preference rank", "U.S. rights", "Rationale",
                             "Reviewer", "Reviewer kind", "Timestamp", "Decision id", "Selected for valuation"],
           finalist_rows, note=f"{finalist_count_text(log.state.finalists)} (maximum {spec.max_finalists}). "
                               "Only explicit logged decisions appear here; Reviewer kind says whether a human "
                               "approved (HUMAN), an AI listed an unapproved candidate (AI_PREPARED), or the "
                               "synthetic demo fixture decided (SYNTHETIC_FIXTURE).", widths={8: 60})

    # 5. Valuation Inputs --------------------------------------------------------------
    import yaml

    assumptions_path = ws.inputs / "valuation_assumptions.yaml"
    assumptions = yaml.safe_load(assumptions_path.read_text()) if assumptions_path.exists() else {}
    owner = (assumptions or {}).get("owner", "")
    label = (assumptions or {}).get("label", "")
    input_rows: list[list[Any]] = []
    for asset_id, entry in valuations.get("assets", {}).items():
        asset = assets[asset_id]
        readiness = entry["readiness"]
        block = (assumptions or {}).get("assets", {}).get(asset.external_id) or {}
        for key, value in _flatten(block):
            if key.startswith("deal_options"):
                continue
            input_rows.append([asset_id, asset.program_name, key, value, _unit(key),
                               f"{label} (owner: {owner})", readiness["ready"] and "READY" or "NOT READY"])
        for key in readiness["defaults_used"]:
            input_rows.append([asset_id, asset.program_name, key, "engine default", _unit(key),
                               "BVE engine default (bve-asset)", "READY" if readiness["ready"] else "NOT READY"])
        for item in readiness["missing"]:
            input_rows.append([asset_id, asset.program_name, item, "MISSING", "", "required input not supplied",
                               "NOT READY FOR VALUATION"])
        for warning in readiness["warnings"]:
            input_rows.append([asset_id, asset.program_name, "warning", warning, "", "DealScreen check", ""])
    _sheet(wb, "Valuation Inputs", ["Asset id", "Program", "Input", "Value", "Unit", "Source / owner",
                                    "Readiness"], input_rows,
           note="Financial assumptions are HYPOTHETICAL analyst inputs, not sourced facts "
                f"(landscape: {ws.import_result().manifest.license_status} data). Nothing here is derived "
                "from a drug's name, target or phase. " + _compliance_limitation(),
           widths={3: 40, 6: 48})

    # 6. Valuation Scenarios & 7. Deal Comparison --------------------------------------
    scenario_rows: list[list[Any]] = []
    deal_rows: list[list[Any]] = []
    for asset_id, entry in valuations.get("assets", {}).items():
        if not entry.get("selected"):
            continue
        runs = {r["case"]: r for r in entry["runs"]}
        standalone = runs.get("standalone", {}).get("summary", {}).get("rnpv_millions")
        for case, r in runs.items():
            sm = r["summary"]
            check = r.get("scenario_check") or {"status": "NOT CHECKED", "reliable": False, "explanation": ""}
            numbers: list[Any] = [sm["bear_rnpv_millions"], sm["base_rnpv_millions"], sm["bull_rnpv_millions"],
                                  sm["rnpv_millions"]]
            if not check["reliable"]:
                numbers = ["BLOCKED"] * 4  # fail closed: an unexplained result is not shown as a value
            scenario_rows.append([asset_id, assets[asset_id].program_name, case, *numbers,
                                  sm["cumulative_success_probability"], sm["peak_sales_millions"],
                                  sm["years_to_launch"], sm["mc_p10_millions"], sm["mc_p90_millions"],
                                  "PROTOTYPE (Lane 1 sign-off pending)" if r["prototype"] else "bve-asset",
                                  r["output_json"], check["status"], check["explanation"]])
            if case != "standalone":
                deal = r["deal_terms"] or {}
                milestones = sum(m["amount_millions"] for m in deal.get("milestones", []))
                deal_rows.append([asset_id, assets[asset_id].program_name, case, deal.get("label", case),
                                  deal.get("upfront_cost_millions", 0.0), milestones,
                                  deal.get("royalty_rate", 0.0), sm["rnpv_millions"], standalone,
                                  None if standalone is None else round(sm["rnpv_millions"] - standalone, 1),
                                  r["output_json"]])
        if not entry["runs"]:
            scenario_rows.append([asset_id, assets[asset_id].program_name, "NOT VALUED",
                                  None, None, None, None, None, None, None, None, None,
                                  "NOT READY FOR VALUATION", ""])
    _sheet(wb, "Valuation Scenarios", ["Asset id", "Program", "Case", "Bear rNPV ($M)", "Base rNPV ($M)",
                                       "Bull rNPV ($M)", "Engine rNPV ($M)", "P(approval)", "Peak sales ($M)",
                                       "Years to launch", "MC P10 ($M)", "MC P90 ($M)", "Computation path",
                                       "Source valuation.json", "Scenario ordering check",
                                       "Ordering explanation"], scenario_rows,
           note="Values copied from BVE ValuationOutput files (bull/base/bear from the engine's own "
                "scenario set). Hypothetical inputs; UNVALIDATED.", money_cols=(4, 5, 6, 7, 9, 11, 12),
           widths={14: 50, 15: 34, 16: 90})
    _sheet(wb, "Deal Comparison", ["Asset id", "Program", "Case", "Structure", "Upfront paid ($M)",
                                   "Milestones payable, face ($M)", "Royalty paid", "Buyer rNPV ($M)",
                                   "Standalone rNPV ($M)", "Difference vs standalone ($M)",
                                   "Source valuation.json"], deal_rows,
           note="Illustrative, hypothetical acquisition vs license terms run through DealEconomics in the "
                "unchanged engine. Not a recommendation.", money_cols=(5, 6, 8, 9, 10), widths={11: 70})

    # 8. Audit Trail -------------------------------------------------------------------
    m = imported.manifest
    audit_rows: list[list[Any]] = [
        ["import", "manifest", k, v, "", "", ""] for k, v in m.model_dump(mode="json").items()
    ]
    audit_rows += [["screening", "version", "screening", screening["version"], "", "", ""],
                   ["screening", "funnel", "funnel", screening["funnel"], "", "", ""],
                   ["validation", "grade", "DealScreen", VALIDATION_GRADE, "", "", VALIDATION_WARNING]]
    for r in log.records:
        audit_rows.append(["decision", r["decision_id"], r["action"], r["subject_id"],
                           f"{r['old_state']} -> {r['new_state']}",
                           f"{r['reviewer_id']} ({r['reviewer_kind']}) {r['timestamp']}",
                           f"{r['rationale']} [hash {r['hash'][:12]}]"])
    for asset_id, entry in valuations.get("assets", {}).items():
        for r in entry["runs"]:
            audit_rows.append(["valuation", asset_id, r["case"], " ".join(r["command"][2:4]),
                               r["summary"].get("git_commit"), r["summary"].get("analysis_date"),
                               r["output_json"]])
    _sheet(wb, "Audit Trail", ["Stage", "Item", "Field / action", "Value / subject", "State change",
                               "Who / when", "Detail"], audit_rows,
           note="Import manifest, screening version and funnel, every analyst decision (hash-chained), "
                "and every valuation run.", widths={4: 50, 7: 70})

    target.parent.mkdir(parents=True, exist_ok=True)
    wb.save(target)
    return target


def _flatten(data: Any, prefix: str = "") -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    if isinstance(data, dict):
        for k, v in data.items():
            out.extend(_flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(data, list):
        for i, v in enumerate(data):
            out.extend(_flatten(v, f"{prefix}[{i}]"))
    else:
        out.append((prefix, data))
    return out


def _unit(key: str) -> str:
    leaf = key.rsplit(".", 1)[-1]
    if leaf.endswith("_usd"):
        return "USD"
    if leaf.endswith("_millions"):
        return "USD millions"
    if leaf.endswith("_years") or leaf in {"years_to_peak", "patent_life_years"}:
        return "years"
    if leaf.endswith(("_rate", "penetration", "probability")):
        return "fraction"
    if leaf.endswith("_annual"):
        return "patients / year"
    return ""


def finalist_count_text(finalists: dict[str, dict[str, Any]]) -> str:
    """Counts by approval state and reviewer kind; "approved" only for HUMAN APPROVED (cycle A1 F4)."""
    counts: dict[str, int] = {}
    for rec in finalists.values():
        if rec["state"] == "APPROVED" and rec["reviewer_kind"] == "HUMAN":
            label = "approved by a human analyst"
        elif rec["state"] == "APPROVED":
            label = f"approved by {rec['reviewer_kind']} (not a human analyst)"
        else:
            label = f"{rec['state'].replace('_', ' ').lower()} ({rec['reviewer_kind']})"
        counts[label] = counts.get(label, 0) + 1
    if not counts:
        return "No finalists recorded"
    return "; ".join(f"{n} {label}" for label, n in sorted(counts.items()))


def _effects_text(screen: dict[str, Any]) -> str:
    if not screen.get("analyst_assertions"):
        return ""
    effects = screen.get("assertion_effects") or []
    if not effects:
        return "NO EFFECT: the assertions changed no gate"
    return "; ".join(
        ("OVERTURNS SOURCE FAIL " if e["overturns_source_fail"] else "")
        + f"{e['requirement_id']}: {e['without_assertions']} -> {e['with_assertions']}"
        for e in effects
    )
