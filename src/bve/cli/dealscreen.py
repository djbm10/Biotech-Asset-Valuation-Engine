"""bve-dealscreen: buyer-specific BD screening workbench (MVP, UNVALIDATED).

Typical flow::

    bve-dealscreen import   --workspace W --landscape export.xlsx --profile vendor.yaml --buyer buyer.yaml
    bve-dealscreen screen   --workspace W
    bve-dealscreen queue    --workspace W
    bve-dealscreen show     --workspace W --asset SYN-0012
    bve-dealscreen research --workspace W --provider offline:evidence.json --unresolved
    bve-dealscreen decide   --workspace W --action APPROVE_FINALIST --subject SYN-0012 \\
                            --new-state APPROVED --reviewer jdoe --rationale "..."
    bve-dealscreen value    --workspace W --assumptions assumptions.yaml
    bve-dealscreen export   --workspace W --out W/deliverables/dealscreen.xlsx
    bve-dealscreen memo     --workspace W --out W/deliverables/bd_memo.md
    bve-dealscreen demo     --workspace W            # the whole synthetic walkthrough

Subjects can be given as an external ID (``SYN-0012``), a DealScreen asset id
(``ds:...``), a claim id, a finding id, or, for identity flags, the shared code.
"""

from __future__ import annotations

import argparse
import csv
import json
import resource
import sys
import time
from pathlib import Path
from typing import Any

import yaml

from bve.dealscreen import VALIDATION_WARNING
from bve.dealscreen.agent import ClinicalTrialsGovProvider, OfflineEvidenceProvider, Question
from bve.dealscreen.facts import TargetNormalizer
from bve.dealscreen.review import Action, DecisionRejected, ReviewerKind
from bve.dealscreen.workspace import Workspace, ontology_drug_authority, ontology_target_normalizer
from bve.se.resolution.registry import normalize_identity_name

EXAMPLES = Path(__file__).resolve().parents[3] / "examples" / "dealscreen"


def _normalizer(args: argparse.Namespace) -> TargetNormalizer:
    if getattr(args, "target_map", None):
        mapping = yaml.safe_load(Path(args.target_map).read_text())
        folded = {str(k).casefold(): v for k, v in mapping.items()}
        return lambda text: folded.get(text.strip().casefold())
    return ontology_target_normalizer()


def resolve_subject(ws: Workspace, action: Action, subject: str, field: str = "") -> str:
    """Map a human-friendly subject to the id the decision log records."""
    assets = ws.assets()
    by_ext = {a.external_id: a for a in assets}
    by_id = {a.asset_id: a for a in assets}
    asset = by_ext.get(subject) or by_id.get(subject)
    if action is Action.RESOLVE_IDENTITY_FLAG:
        key = normalize_identity_name(subject)
        for flag in ws.flags():
            if subject == flag.flag_id or key == flag.shared_value:
                return flag.flag_id
        raise DecisionRejected(f"no identity flag for {subject!r}")
    if action in (Action.CONFIRM_FINDING, Action.REJECT_FINDING):
        if asset is None:
            return subject
        matches = [f for f in ws.findings() if f.asset_id == asset.asset_id and (not field or f.field == field)]
        if not matches:
            raise DecisionRejected(f"no agent finding for {subject} field {field!r}")
        return min(matches, key=lambda f: f.finding_id).finding_id
    if action is Action.RETRACT_FACT:
        return subject
    if action in (Action.CONFIRM_CLAIM, Action.REJECT_CLAIM):
        if asset is None:
            return subject
        claims = asset.claims_for(field)
        if not claims:
            raise DecisionRejected(f"{subject} has no {field!r} claim")
        return claims[0].claim_id
    if asset is None:
        raise DecisionRejected(f"unknown asset {subject!r}")
    return asset.asset_id


def _decide(ws: Workspace, *, action: str, subject: str, new_state: str, reviewer: str, rationale: str,
            kind: ReviewerKind, field: str = "", question: str = "",
            assertion: dict[str, str] | None = None,
            normalizer: TargetNormalizer | None = None) -> dict[str, Any]:
    act = Action(action)
    subject_id = resolve_subject(ws, act, subject, field)
    detail: dict[str, Any] = {"question": question} if question else {}
    if act is Action.ASSERT_FACT:
        detail = {"field": field, **(assertion or {})}
    return ws.decision_log().record(
        action=act, subject_id=subject_id, new_state=new_state, reviewer_id=reviewer,
        rationale=rationale, reviewer_kind=kind, detail=detail,
        context=ws.decision_context(normalizer),
    )


def apply_fixture(ws: Workspace, path: Path, phase: str, *,
                  normalizer: TargetNormalizer | None = None) -> dict[str, Any]:
    """Replay a LABELLED synthetic/simulated reviewer file (reviewer kind SYNTHETIC_FIXTURE)."""
    applied, refused = [], []
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["phase"] != phase:
                continue
            try:
                rec = _decide(ws, action=row["action"], subject=row["external_id"], new_state=row["new_state"],
                              reviewer=row["reviewer_id"], rationale=row["rationale"],
                              kind=ReviewerKind.SYNTHETIC_FIXTURE, field=row.get("field", ""),
                              question=row.get("question", ""), normalizer=normalizer,
                              assertion={k: row.get(k, "") for k in
                                         ("value", "source_url", "source_title", "source_date",
                                          "evidence_span")})
                applied.append({"decision_id": rec["decision_id"], "action": rec["action"], "subject": row["external_id"]})
            except DecisionRejected as exc:
                refused.append({"action": row["action"], "subject": row["external_id"], "reason": str(exc)})
    return {"applied": applied, "refused": refused}


def _research_targets(ws: Workspace, args: argparse.Namespace) -> list[str]:
    screens = ws.screening()["screens"]
    if args.asset:
        by_ext = {a.external_id: a.asset_id for a in ws.assets()}
        return [by_ext.get(a, a) for a in args.asset]
    wanted = {"UNRESOLVED"} if args.unresolved else {"UNRESOLVED", "ELIGIBLE"}
    return [s["asset_id"] for s in screens if s["disposition"] in wanted]


def _provider(spec: str, normalizer: TargetNormalizer):
    if spec.startswith("offline:"):
        return OfflineEvidenceProvider(spec.split(":", 1)[1], normalizer)
    if spec == "ctgov":
        return ClinicalTrialsGovProvider(normalizer)
    raise SystemExit(f"unknown provider {spec!r} (use offline:<library.json> or ctgov)")


def _print_queue(ws: Workspace) -> None:
    screening = ws.screening()
    f = screening["funnel"]
    print(f"Funnel: {f['assets_screened']} screened = {f['eligible']} eligible + {f['unresolved']} unresolved "
          f"+ {f['excluded']} excluded")
    print("Unresolved queue (first 25):")
    for s in [s for s in screening["screens"] if s["disposition"] == "UNRESOLVED"][:25]:
        print(f"  #{s['rank']:<3} {s['program_name']:<22} {s['review_reasons'][0][:110]}")
    names = {s["asset_id"]: f"{s['program_name']} [{s['disposition']}]" for s in screening["screens"]}
    flags = ws.flags()
    if flags:
        print("Identity flags (records may be the same molecule; not merged):")
        for flag in flags:
            print(f"  {flag.kind}: {' / '.join(names.get(a, a) for a in flag.asset_ids)} ({flag.shared_value})")


def _show(ws: Workspace, subject: str) -> None:
    assets = {a.external_id: a for a in ws.assets()} | {a.asset_id: a for a in ws.assets()}
    asset = assets[subject]
    screen = {s["asset_id"]: s for s in ws.screening()["screens"]}[asset.asset_id]
    rows = {r.row_number: r for r in ws.import_result().rows}
    print(json.dumps({
        "asset_id": asset.asset_id, "external_id": asset.external_id, "program": asset.program_name,
        "disposition": screen["disposition"], "rank": screen["rank"],
        "decisions": [{k: d[k] for k in ("requirement_id", "status", "rationale", "next_action",
                                         "supporting_or_contradictory_claim_ids")} for d in screen["decisions"]],
        "commercial": screen["commercial"], "unreadable_claims": screen["unreadable_claims"],
        "identity_flags": screen["identity_flag_ids"],
        "indication_readings": screen.get("indication_readings", []),
        "source_rows": {n: rows[n].raw for n in asset.row_numbers},
        "findings": [f.model_dump(mode="json") for f in ws.findings() if f.asset_id == asset.asset_id],
    }, indent=2, default=str))


def run_demo(args: argparse.Namespace) -> dict[str, Any]:
    from bve.dealscreen.evaluate import evaluate
    from bve.dealscreen.memo import write_memo
    from bve.dealscreen.workbook import export_workbook

    started = time.perf_counter()
    examples = Path(args.examples)
    ws = Workspace(args.workspace)
    if (ws.root / "import.json").exists():
        raise SystemExit(f"{ws.root} already holds a workspace; use a new directory")
    normalizer = _normalizer(args)
    timings: dict[str, float] = {}

    def step(name: str, t0: float) -> float:
        timings[name] = round(time.perf_counter() - t0, 2)
        print(f"[{timings[name]:>6.2f}s] {name}")
        return time.perf_counter()

    t = time.perf_counter()
    authority = None if args.target_map else ontology_drug_authority()
    result = ws.import_landscape(examples / args.landscape, examples / "profile_synthetic_vendor.yaml",
                                 examples / "buyer_tl1a_ibd.yaml", drug_authority=authority)
    t = step("import", t)
    ws.screen(normalizer)
    initial_screen = (ws.root / "screening.json").read_bytes()
    (ws.root / "screening_initial.json").write_bytes(initial_screen)
    first = evaluate(ws, examples / "ground_truth.json", stage="initial screen")
    t = step("screen", t)
    provider = OfflineEvidenceProvider(examples / "evidence_library.json", normalizer)
    screens = ws.screening()["screens"]
    unresolved = [s["asset_id"] for s in screens if s["disposition"] == "UNRESOLVED"]
    eligible = [s["asset_id"] for s in screens if s["disposition"] == "ELIGIBLE"]
    findings = ws.research(provider, unresolved, [Question.TARGET, Question.STAGE, Question.MECHANISM])
    findings += ws.research(provider, eligible, [Question.US_RIGHTS])
    t = step("agent research (offline)", t)
    phase1 = apply_fixture(ws, examples / "reviewer_fixture.csv", "1")
    ws.screen(normalizer)
    phase2 = apply_fixture(ws, examples / "reviewer_fixture.csv", "2")
    second = evaluate(ws, examples / "ground_truth.json", stage="after confirmed findings",
                      after_research=True)
    t = step("synthetic review fixture + re-screen", t)
    valuations = ws.value_selected(examples / "valuation_assumptions.yaml", n_sims=args.n_sims,
                                   progress=lambda m: print(f"         {m}"))
    t = step("valuation (BVE CLI subprocesses)", t)
    out = ws.deliverables
    workbook = export_workbook(ws, out / "dealscreen_companion.xlsx")
    memo = write_memo(ws, out / "bd_memo.md")
    t = step("export workbook + memo", t)
    rerun = Workspace(ws.root / "_determinism_check")
    rerun.import_landscape(examples / args.landscape, examples / "profile_synthetic_vendor.yaml",
                           examples / "buyer_tl1a_ibd.yaml", drug_authority=authority)
    rerun.screen(normalizer)
    a = json.loads(initial_screen)
    b = json.loads((ws.root / "screening.json").read_text())
    deterministic_import = (rerun.root / "import.json").read_bytes() == (ws.root / "import.json").read_bytes()
    t = step("determinism re-run", t)
    report = {
        "validation": VALIDATION_WARNING,
        "manifest": result.manifest.model_dump(mode="json"),
        "funnel_initial": a["funnel"],
        "funnel_after_review": b["funnel"],
        "findings_proposed": len(findings),
        "fixture_phase_1": phase1,
        "fixture_phase_2": phase2,
        "valuations": {k: {"selected": v["selected"], "ready": v["readiness"]["ready"],
                           "missing": v["readiness"]["missing"], "warnings": v["readiness"]["warnings"],
                           "runs": {r["case"]: r["summary"] for r in v["runs"]}}
                       for k, v in valuations["assets"].items()},
        "deliverables": {"workbook": str(workbook), **memo},
        "evaluation_initial": first,
        "evaluation_after_review": second,
        "determinism": {"import_json_identical": deterministic_import,
                        "initial_screen_byte_identical_on_rerun":
                            (rerun.root / "screening.json").read_bytes() == initial_screen},
        "timings_seconds": timings,
        "total_seconds": round(time.perf_counter() - started, 2),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
    }
    (ws.root / "demo_report.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bve-dealscreen", description="BVE DealScreen (UNVALIDATED MVP)")
    sub = parser.add_subparsers(dest="command", required=True)

    def ws_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument("--workspace", required=True)

    def norm_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument("--target-map", help="YAML synonym->symbol map instead of the S&E ontology (fast, offline)")

    p = sub.add_parser("import"); ws_arg(p); norm_arg(p)
    p.add_argument("--landscape", required=True); p.add_argument("--profile", required=True)
    p.add_argument("--buyer", required=True); p.add_argument("--sheet")
    p.add_argument("--identity-authority", action="store_true", help="propose merges via the S&E ontology")
    p = sub.add_parser("screen"); ws_arg(p); norm_arg(p)
    p = sub.add_parser("queue"); ws_arg(p)
    p = sub.add_parser("show"); ws_arg(p); p.add_argument("--asset", required=True)
    p = sub.add_parser("research"); ws_arg(p); norm_arg(p)
    p.add_argument("--provider", required=True, help="offline:<library.json> or ctgov")
    p.add_argument("--asset", action="append"); p.add_argument("--unresolved", action="store_true")
    p.add_argument("--question", action="append", choices=[q.name for q in Question])
    p = sub.add_parser("decide"); ws_arg(p)
    p.add_argument("--action", required=True, choices=[a.value for a in Action])
    p.add_argument("--subject", required=True); p.add_argument("--field", default="")
    p.add_argument("--new-state", required=True); p.add_argument("--reviewer", required=True)
    p.add_argument("--rationale", required=True); p.add_argument("--question", default="")
    p.add_argument("--reviewer-kind", default="HUMAN", choices=[k.value for k in ReviewerKind],
                   help="HUMAN, or AI_PREPARED for an assistant's unapproved candidate list")
    p = sub.add_parser("assert", help="enter one cited field value for an asset"); ws_arg(p); norm_arg(p)
    p.add_argument("--asset", required=True); p.add_argument("--field", required=True)
    p.add_argument("--value", required=True); p.add_argument("--source-url", required=True)
    p.add_argument("--quote", required=True, help="the evidence span, verbatim")
    p.add_argument("--source-title", default=""); p.add_argument("--source-date", default="")
    p.add_argument("--reviewer", required=True); p.add_argument("--rationale", required=True)
    p.add_argument("--reviewer-kind", default="HUMAN", choices=[k.value for k in ReviewerKind])
    p = sub.add_parser("retract", help="withdraw an assertion by its decision id"); ws_arg(p)
    p.add_argument("--assertion", required=True); p.add_argument("--reviewer", required=True)
    p.add_argument("--rationale", required=True)
    p.add_argument("--reviewer-kind", default="HUMAN", choices=[k.value for k in ReviewerKind])
    p = sub.add_parser("apply-fixture", help="replay a LABELLED synthetic reviewer fixture"); ws_arg(p)
    p.add_argument("--file", required=True); p.add_argument("--phase", required=True)
    p = sub.add_parser("value"); ws_arg(p); p.add_argument("--assumptions", required=True)
    p.add_argument("--n-sims", type=int, default=5_000)
    p = sub.add_parser("export"); ws_arg(p); p.add_argument("--out", required=True)
    p.add_argument("--replace-own", action="store_true")
    p = sub.add_parser("memo"); ws_arg(p); p.add_argument("--out", required=True)
    p = sub.add_parser("demo"); ws_arg(p); norm_arg(p)
    p.add_argument("--examples", default=str(EXAMPLES)); p.add_argument("--landscape", default="landscape_200.xlsx")
    p.add_argument("--n-sims", type=int, default=5_000)
    args = parser.parse_args(argv)

    ws = Workspace(args.workspace)
    try:
        if args.command == "import":
            result = ws.import_landscape(Path(args.landscape), Path(args.profile), Path(args.buyer),
                                         sheet=args.sheet,
                                         drug_authority=ontology_drug_authority() if args.identity_authority else None,
                                         target_normalizer=_normalizer(args))
            print(json.dumps(result.manifest.model_dump(mode="json"), indent=2))
            for rej in result.rejected:
                print(f"REJECTED row {rej.row_number}: {'; '.join(rej.reasons)}")
            for dup in result.duplicates:
                print(f"DUPLICATE row {dup.row_number} = row {dup.duplicate_of_row}")
            names = {a.asset_id: f"{a.external_id} {a.program_name}" for a in result.assets}
            for flag in ws.flags():
                print(f"IDENTITY {flag.kind}: {' / '.join(names.get(a, a) for a in flag.asset_ids)} "
                      f"(shared {flag.shared_value}; not merged, review with `queue`)")
            refresh = ws.refresh()
            if refresh and refresh.get("current_dataset") == result.manifest.dataset_version:
                print(f"REFRESH: +{len(refresh['assets_added'])} / -{len(refresh['assets_removed'])} assets, "
                      f"{len(refresh['field_changes'])} with changed fields, "
                      f"{len(refresh['orphaned_decisions'])} ORPHANED decisions (see refresh_report.json)")
        elif args.command == "screen":
            ws.screen(_normalizer(args) if args.target_map else None)
            _print_queue(ws)
        elif args.command == "queue":
            _print_queue(ws)
        elif args.command == "show":
            _show(ws, args.asset)
        elif args.command == "research":
            questions = [Question[q] for q in (args.question or ["TARGET", "STAGE", "US_RIGHTS", "MECHANISM"])]
            new = ws.research(_provider(args.provider, _normalizer(args)), _research_targets(ws, args), questions)
            for f in new:
                print(f"{f.finding_id} {f.field}={f.proposed_value!r} <{f.source_url}> :: {f.evidence_span[:90]}")
            print(f"{len(new)} new proposed finding(s); none affect screening until confirmed.")
        elif args.command == "decide":
            rec = _decide(ws, action=args.action, subject=args.subject, new_state=args.new_state,
                          reviewer=args.reviewer, rationale=args.rationale, kind=ReviewerKind(args.reviewer_kind),
                          field=args.field, question=args.question)
            print(f"recorded {rec['decision_id']}: {rec['action']} {rec['subject_id']} "
                  f"{rec['old_state']} -> {rec['new_state']}. Re-run `screen` to apply fact changes.")
        elif args.command == "assert":
            rec = _decide(ws, action="ASSERT_FACT", subject=args.asset, new_state="ASSERTED",
                          reviewer=args.reviewer, rationale=args.rationale,
                          kind=ReviewerKind(args.reviewer_kind), field=args.field,
                          normalizer=_normalizer(args) if args.target_map else None,
                          assertion={"value": args.value, "source_url": args.source_url,
                                     "source_title": args.source_title, "source_date": args.source_date,
                                     "evidence_span": args.quote})
            print(f"recorded {rec['decision_id']}: {args.field}={args.value!r} on {rec['subject_id']}. "
                  "Re-run `screen` to apply it.")
        elif args.command == "retract":
            rec = _decide(ws, action="RETRACT_FACT", subject=args.assertion, new_state="RETRACTED",
                          reviewer=args.reviewer, rationale=args.rationale,
                          kind=ReviewerKind(args.reviewer_kind))
            print(f"recorded {rec['decision_id']}: retracted {args.assertion}. Re-run `screen`.")
        elif args.command == "apply-fixture":
            print(json.dumps(apply_fixture(ws, Path(args.file), args.phase), indent=2))
        elif args.command == "value":
            results = ws.value_selected(Path(args.assumptions), n_sims=args.n_sims)
            print(json.dumps(results, indent=2, default=str))
            if not any(e["runs"] for e in results["assets"].values()):
                print("No valuation was run: a valuation runs only for a finalist approved and selected for "
                      "valuation by a HUMAN reviewer whose inputs are READY (see readiness above).",
                      file=sys.stderr)
        elif args.command == "export":
            from bve.dealscreen.workbook import export_workbook

            print(export_workbook(ws, args.out, replace_own=args.replace_own))
        elif args.command == "memo":
            from bve.dealscreen.memo import write_memo

            print(json.dumps(write_memo(ws, args.out), indent=2))
        elif args.command == "demo":
            report = run_demo(args)
            print(json.dumps({k: report[k] for k in ("funnel_initial", "funnel_after_review", "deliverables",
                                                     "total_seconds", "peak_rss_mb")}, indent=2))
    except DecisionRejected as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
