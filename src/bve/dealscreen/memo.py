"""One-page BD decision memo, built only from the workspace's saved results."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from bve.dealscreen import VALIDATION_GRADE, VALIDATION_WARNING
from bve.dealscreen.workspace import Workspace

_REQ_LABEL = {
    "target.expression": "target not the specified target",
    "modality.required": "modality outside the allowed set",
    "biology.mechanism_direction": "mechanism unsuitable (e.g. agonist)",
    "strategy.therapeutic_area": "therapeutic area outside scope",
    "evidence.phase_constraint": "below the minimum clinical phase",
}


STAGE_LABEL = {0: "Discovery", 1: "Preclinical", 2: "Phase 1", 3: "Phase 2", 4: "Phase 3",
               5: "Registration", 6: "Phase 4 or marketed"}


def _m(value: float | None) -> str:
    return "n/a" if value is None else f"${value:,.0f}M"


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
        f"**Rights are a separate question.** Of the {funnel['eligible']} eligible programs, U.S. rights "
        "status is: " + ", ".join(f"{k.replace('_', ' ').lower()} {v}" for k, v in sorted(rights.items()))
        + ". No program is shown as available without an explicit source statement.",
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
    else:
        heading = f"**Finalists: {len(finalists)} ({', '.join(sorted(kinds))} reviewers)**"
    lines.append(heading + " (rank order by declared preferences; rights shown separately):")
    for asset_id in finalists:
        s = screens[asset_id]
        flag = "" if s["disposition"] == "ELIGIBLE" else " (open scientific question)"
        lines.append(f"- {s['program_name']} ({s['company']}): {STAGE_LABEL.get(s['stage_order'], 'stage unknown')}"
                     f"{flag}; U.S. rights {s['commercial']['display'].lower()}")
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
            f"peak share; P(approval) {base['cumulative_success_probability']:.0%}."
            + (" Scenarios are out of label order because the program is cost-dominated at these inputs "
               "(value-destroying, not a computation error)."
               if any(c["status"] != "ORDERED" for c in checks.values()) else "")
        )
    if not_ready:
        lines.append(f"- NOT READY FOR VALUATION (no invented inputs): {', '.join(not_ready)}.")
    lines.append("")

    unresolved = [s for s in screens.values() if s["disposition"] == "UNRESOLVED"]
    open_gates = Counter(
        d["requirement_id"] for s in unresolved for d in s["decisions"]
        if (d["analyst_override"] or d["status"]) == "UNKNOWN"
    )
    rights_open = [screens[a]["program_name"] for a in finalists
                   if screens[a]["commercial"]["us_rights_status"] != "AVAILABLE_ANALYST_CONFIRMED"]
    lines.append("**Investigate next.**")
    lines.append(f"- Confirm ownership and U.S. rights for {len(rights_open)} of {len(finalists)} listed "
                 "programs (none is analyst-confirmed).")
    for asset_id in finalists:
        unknown = [d["requirement_id"] for d in screens[asset_id]["decisions"]
                   if (d["analyst_override"] or d["status"]) == "UNKNOWN"]
        if unknown:
            lines.append(f"- {screens[asset_id]['program_name']}: resolve {', '.join(unknown)}.")
    if unresolved:
        lines.append(f"- Work the {len(unresolved)}-program unresolved queue; open gates: "
                     + ", ".join(f"{k} ({v})" for k, v in open_gates.most_common()) + ".")
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
