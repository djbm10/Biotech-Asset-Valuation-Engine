"""
Weekly operational runner — seeds universe, runs actionable report, records decisions.

Usage:
    python -m bve.ops.weekly_runner seed       # first-time setup
    python -m bve.ops.weekly_runner report     # generate weekly actionable report
    python -m bve.ops.weekly_runner review     # run weekly review (after outcomes)
    python -m bve.ops.weekly_runner status     # show current positions + open claims
    python -m bve.ops.weekly_runner mna        # standalone M&A probability scan (top-10)
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Optional

from bve.intelligence.actionable_output import ActionableGenerator, ScoredCandidate
from bve.intelligence.decision_layer import DecisionLayer
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.thesis_tracker import ClaimType, ThesisTracker
from bve.intelligence.weekly_review import WeeklyReviewEngine

# ---------------------------------------------------------------------------
# Persistent DB path
# ---------------------------------------------------------------------------

DB_PATH = Path(__file__).parent.parent.parent.parent / "outputs" / "intelligence" / "ops.db"


def _get_store() -> KnowledgeStore:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return KnowledgeStore(str(DB_PATH))


# ---------------------------------------------------------------------------
# Universe definition
# ---------------------------------------------------------------------------

UNIVERSE = [
    # ticker, company_id, asset_id, indication, ranking_score, opportunity_score,
    # conviction_label, catalyst_description, claim_type, claim_assertion
    dict(
        ticker="VRTX",
        company_id="co-vrtx",
        asset_id="a-vrtx",
        indication="CF / pain / APOL1",
        ranking_score=0.58,
        opportunity_score=0.55,
        conviction="medium",
        catalyst="VX-548 NDA decision + non-opioid pain label expansion",
        claim_type=ClaimType.POS_ABOVE_THRESHOLD,
        claim_assertion="Pipeline PoS > market-implied; VX-548 label expansion underpriced",
    ),
    dict(
        ticker="REGN",
        company_id="co-regn",
        asset_id="a-regn",
        indication="oncology / immunology / eye",
        ranking_score=0.52,
        opportunity_score=0.40,
        conviction="medium",
        catalyst="Dupixent label expansions; EYLEA HD biosimilar competition",
        claim_type=ClaimType.COMPETITOR_FAILURE,
        claim_assertion="EYLEA biosimilar penetration slower than feared; pricing holds",
    ),
    dict(
        ticker="LLY",
        company_id="co-lly",
        asset_id="a-lly",
        indication="obesity / diabetes / Alzheimer's",
        ranking_score=0.45,
        opportunity_score=0.28,
        conviction="medium",
        catalyst="Zepbound share vs semaglutide; orforglipron oral data",
        claim_type=ClaimType.MARKET_REACTION_POSITIVE,
        claim_assertion="GLP-1 dominance persists but expectations leave little upside",
    ),
    dict(
        ticker="ALNY",
        company_id="co-alny",
        asset_id="a-alny",
        indication="RNAi — TTR / hypertension / NASH",
        ranking_score=0.72,
        opportunity_score=0.70,
        conviction="medium-high",
        catalyst="Alnylam zilebesiran Ph3 KARDIA-2 readout; vutrisiran label expansion",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="Zilebesiran meets primary BP endpoint in KARDIA-2",
    ),
    dict(
        ticker="CRSP",
        company_id="co-crsp",
        asset_id="a-crsp",
        indication="SCD / beta-thal / diabetes",
        ranking_score=0.55,
        opportunity_score=0.58,
        conviction="medium",
        catalyst="Casgevy commercial uptake trajectory; CTX310 IND data",
        claim_type=ClaimType.ENROLLMENT_ON_TRACK,
        claim_assertion="Casgevy treatment center activation on pace with 12-month guidance",
    ),
    dict(
        ticker="NTLA",
        company_id="co-ntla",
        asset_id="a-ntla",
        indication="in vivo gene editing — ATTR / HAE",
        ranking_score=0.62,
        opportunity_score=0.65,
        conviction="medium",
        catalyst="NTLA-2001 Ph1 durability data; NTLA-2002 HAE Ph3 start",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="NTLA-2001 durable TTR reduction at 12-month follow-up",
    ),
    dict(
        ticker="BEAM",
        company_id="co-beam",
        asset_id="a-beam",
        indication="base editing — SCD / AML / immunology",
        ranking_score=0.42,
        opportunity_score=0.48,
        conviction="low-medium",
        catalyst="BEAM-101 SCD Ph1/2 initial efficacy; BEAM-201 AML IND",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="BEAM-101 achieves HbF induction with clean safety at 6 months",
    ),
    dict(
        ticker="SRPT",
        company_id="co-srpt",
        asset_id="a-srpt",
        indication="DMD gene therapy",
        ranking_score=0.68,
        opportunity_score=0.75,
        conviction="medium-high",
        catalyst="Elevidys full approval confirmation; SRP-9003 (LGMD2E) Ph3 data",
        claim_type=ClaimType.REGULATORY_PATHWAY,
        claim_assertion="Elevidys receives broad label conversion (not restricted to ambulatory)",
    ),
    dict(
        ticker="VKTX",
        company_id="co-vktx",
        asset_id="a-vktx",
        indication="obesity / NASH",
        ranking_score=0.70,
        opportunity_score=0.78,
        conviction="medium-high",
        catalyst="VK2735 oral Ph2 readout; subcutaneous Ph3 enrollment completion",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="VK2735 oral meets >10% weight loss primary endpoint in Ph2",
    ),
    dict(
        ticker="RXRX",
        company_id="co-rxrx",
        asset_id="a-rxrx",
        indication="AI-enabled rare disease / oncology",
        ranking_score=0.38,
        opportunity_score=0.42,
        conviction="low-medium",
        catalyst="First AI-generated IND → Ph1 data; Recursion-Nvidia compute milestones",
        claim_type=ClaimType.POS_ABOVE_THRESHOLD,
        claim_assertion="At least one Recursion-originated compound reaches Ph1 dose escalation",
    ),
    dict(
        ticker="MRNA",
        company_id="co-mrna",
        asset_id="a-mrna",
        indication="mRNA — flu / RSV / cancer vaccines",
        ranking_score=0.50,
        opportunity_score=0.52,
        conviction="medium",
        catalyst="mRNA-1283 next-gen COVID/flu combo Ph3; individualized cancer vaccine Ph3",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="mRNA-4157 (ICV) meets RFS endpoint in KEYNOTE-942 registrational",
    ),
    dict(
        ticker="BMRN",
        company_id="co-bmrn",
        asset_id="a-bmrn",
        indication="rare disease — PKU / hemophilia / achondroplasia",
        ranking_score=0.54,
        opportunity_score=0.50,
        conviction="medium",
        catalyst="Roctavian haemophilia A label durability data; BMN 333 achondroplasia Ph3",
        claim_type=ClaimType.ENROLLMENT_ON_TRACK,
        claim_assertion="Roctavian durability holds at 3-year follow-up; no label change needed",
    ),
    # ------------------------------------------------------------------
    # Expansion cohort — added Run 10
    # ------------------------------------------------------------------
    # --- Tier A: medium-high conviction, active catalysts ---
    dict(
        ticker="KYMR",
        company_id="co-kymr",
        asset_id="a-kymr",
        indication="protein degradation — STAT6 / IRAKIMiD / MDM2",
        ranking_score=0.65,
        opportunity_score=0.68,
        conviction="medium-high",
        catalyst="KT-474 STAT6 degrader Ph2 atopic derm readout; KT-333 STAT3 lymphoma data",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="KT-474 achieves ≥50% EASI reduction vs placebo in Ph2 atopic derm",
    ),
    dict(
        ticker="ARVN",
        company_id="co-arvn",
        asset_id="a-arvn",
        indication="PROTAC protein degradation — ER+ breast cancer / AR prostate cancer",
        ranking_score=0.63,
        opportunity_score=0.66,
        conviction="medium-high",
        catalyst="ARV-471 VERITAC-2 Ph3 PFS readout in ER+/HER2- breast cancer",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="ARV-471 meets PFS primary endpoint in VERITAC-2 vs exemestane",
    ),
    dict(
        ticker="RVMD",
        company_id="co-rvmd",
        asset_id="a-rvmd",
        indication="RAS oncology — KRAS G12C/D, pan-RAS",
        ranking_score=0.61,
        opportunity_score=0.64,
        conviction="medium",
        catalyst="RMC-6236 pan-RAS Ph1/2 PDAC expansion cohort ORR; RMC-9805 KRAS G12D IND",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="RMC-6236 achieves ≥20% ORR in KRAS-mutant PDAC expansion cohort",
    ),
    dict(
        ticker="MDGL",
        company_id="co-mdgl",
        asset_id="a-mdgl",
        indication="NASH / MASH — resmetirom",
        ranking_score=0.60,
        opportunity_score=0.62,
        conviction="medium",
        catalyst="Rezdiffra (resmetirom) Rx uptake trajectory; label expansion to F2 fibrosis",
        claim_type=ClaimType.MARKET_REACTION_POSITIVE,
        claim_assertion="Rezdiffra achieves ≥40,000 prescriptions in first full year post-launch",
    ),
    dict(
        ticker="IMVT",
        company_id="co-imvt",
        asset_id="a-imvt",
        indication="FcRn — myasthenia gravis / thyroid eye disease / warm AIHA",
        ranking_score=0.56,
        opportunity_score=0.58,
        conviction="medium",
        catalyst="Batoclimab ASCEND+ Ph3 MG readout; nipocalimab competitive read-across",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="Batoclimab meets MG-ADL responder rate ≥50% in ASCEND+ vs placebo",
    ),
    # --- Tier B: weak / speculative, low conviction ---
    dict(
        ticker="FULC",
        company_id="co-fulc",
        asset_id="a-fulc",
        indication="rare muscle disease — FSHD / SMA",
        ranking_score=0.38,
        opportunity_score=0.36,
        conviction="low-medium",
        catalyst="Losmapimod Ph3 FSHD MRI/functional read; RO7204239 collaboration milestone",
        claim_type=ClaimType.ENROLLMENT_ON_TRACK,
        claim_assertion="Losmapimod Ph3 hits MRI fat fraction primary endpoint (p<0.05)",
    ),
    dict(
        ticker="FATE",
        company_id="co-fate",
        asset_id="a-fate",
        indication="iPSC-derived NK / T-cell therapy — AML / myeloma",
        ranking_score=0.33,
        opportunity_score=0.30,
        conviction="low",
        catalyst="FT576 iPSC-NK myeloma Ph1 ORR update; partnership decision from J&J",
        claim_type=ClaimType.POS_ABOVE_THRESHOLD,
        claim_assertion="FT576 achieves ≥30% ORR in RRMM monotherapy arm",
    ),
    dict(
        ticker="OCUL",
        company_id="co-ocul",
        asset_id="a-ocul",
        indication="rare retinal disease — LCA10 / RP",
        ranking_score=0.30,
        opportunity_score=0.28,
        conviction="low",
        catalyst="OCU400 (LCA10/RP) Ph2/3 best-corrected visual acuity data",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="OCU400 shows ≥15-letter BCVA improvement in ≥40% of LCA10 patients",
    ),
    dict(
        ticker="SRRK",
        company_id="co-srrk",
        asset_id="a-srrk",
        indication="musculoskeletal — spinal muscular atrophy / cachexia",
        ranking_score=0.36,
        opportunity_score=0.34,
        conviction="low-medium",
        catalyst="Apitegromab TOPAZ Ph3 SMA motor function data; NDA readiness review",
        claim_type=ClaimType.ENROLLMENT_ON_TRACK,
        claim_assertion="Apitegromab meets HFMSE motor function endpoint at 12 months in TOPAZ",
    ),
    dict(
        ticker="IOVA",
        company_id="co-iova",
        asset_id="a-iova",
        indication="TIL therapy — melanoma / NSCLC / cervical",
        ranking_score=0.44,
        opportunity_score=0.40,
        conviction="low-medium",
        catalyst="Amtagvi commercial uptake trajectory; LN-145 NSCLC Ph2 expansion ORR",
        claim_type=ClaimType.MARKET_REACTION_POSITIVE,
        claim_assertion="Amtagvi treatment centers reach 50 sites by end of 2025; ramp holds",
    ),
    # --- Tier C: known failures / distressed — low ranking, stress-tests the filter ---
    dict(
        ticker="NVAX",
        company_id="co-nvax",
        asset_id="a-nvax",
        indication="protein subunit vaccines — COVID / flu",
        ranking_score=0.22,
        opportunity_score=0.18,
        conviction="very-low",
        catalyst="COVID booster season share; Sanofi co-promotion milestone",
        claim_type=ClaimType.MARKET_REACTION_POSITIVE,
        claim_assertion="Nuvaxovid captures ≥5% of US COVID booster market in 2025 fall season",
    ),
    dict(
        ticker="PRTA",
        company_id="co-prta",
        asset_id="a-prta",
        indication="neurodegenerative — Parkinson's / Alzheimer's (alpha-syn / tau / ATTR)",
        ranking_score=0.19,
        opportunity_score=0.16,
        conviction="very-low",
        catalyst="Prasinezumab (alpha-syn) Ph2b PADOVA extension; PRX012 ATTR-CM Ph1",
        claim_type=ClaimType.ENDPOINT_MET,
        claim_assertion="Prasinezumab slows motor progression in rapid-progressors in Ph2b extension",
    ),
    dict(
        ticker="EDIT",
        company_id="co-edit",
        asset_id="a-edit",
        indication="CRISPR gene editing — SCD / LCA10 / AML",
        ranking_score=0.17,
        opportunity_score=0.14,
        conviction="very-low",
        catalyst="EDIT-301 SCD Ph1/2 durability data; cash runway / partnership decision",
        claim_type=ClaimType.ENROLLMENT_ON_TRACK,
        claim_assertion="EDIT-301 achieves HbF induction sustaining HbS <30% at 12 months",
    ),
    dict(
        ticker="AMRN",
        company_id="co-amrn",
        asset_id="a-amrn",
        indication="cardiovascular — Vascepa (icosapentaenoic acid)",
        ranking_score=0.12,
        opportunity_score=0.10,
        conviction="very-low",
        catalyst="Vascepa patent challenge outcome; potential acquisition / licensing deal",
        claim_type=ClaimType.COMPETITOR_FAILURE,
        claim_assertion="Patent courts uphold Vascepa formulation claims, limiting generic entry",
    ),
    dict(
        ticker="ZYME",
        company_id="co-zyme",
        asset_id="a-zyme",
        indication="oncology — HER2 bispecific / ADC",
        ranking_score=0.28,
        opportunity_score=0.24,
        conviction="low",
        catalyst="Zanidatamab (HER2 bispecific) BLA FDA decision in biliary tract cancer",
        claim_type=ClaimType.REGULATORY_PATHWAY,
        claim_assertion="Zanidatamab receives FDA approval in biliary tract cancer (BTC)",
    ),
]


# ---------------------------------------------------------------------------
# M&A research file paths (relative to repo root)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent.parent.parent
_MNA_PROFILES_PATH = str(_REPO_ROOT / "research" / "mna" / "pipeline_gaps.yaml")
_MNA_COMPS_PATH    = str(_REPO_ROOT / "research" / "mna" / "comparable_deals.yaml")
_MNA_VULN_PATH     = str(_REPO_ROOT / "research" / "mna" / "vulnerability_signals.yaml")


def _run_mna_scan(store: KnowledgeStore, top_n: int = 10) -> Optional[object]:
    """
    Run the M&A probability scan over the weekly UNIVERSE and return
    `MAProbabilityResult`, or None if research files are unavailable.
    """
    # Lazy import to avoid top-level import cost on every runner invocation
    try:
        from bve.intelligence.ma_probability import MAProbabilityConfig, MAProbabilityScanner
        from bve.pipeline.watchlist_runner import WatchlistAsset
    except ImportError:
        return None

    if not all(Path(p).exists() for p in [_MNA_PROFILES_PATH, _MNA_COMPS_PATH, _MNA_VULN_PATH]):
        return None

    # Build WatchlistAsset list from UNIVERSE definition
    watchlist_assets = [
        WatchlistAsset(
            company_id=u["company_id"],
            asset_id=u["asset_id"],
            ticker=u.get("ticker"),
            indication=u.get("indication"),
        )
        for u in UNIVERSE
    ]

    config = MAProbabilityConfig(
        top_n=top_n,
        alert_threshold=0.70,
        vulnerability_signals_path=_MNA_VULN_PATH,
        persist_daily_snapshots=False,
        enable_monitor=False,
        fit_integration_config={
            "acquirer_profiles_path": _MNA_PROFILES_PATH,
            "comparable_deals_path": _MNA_COMPS_PATH,
            "top_n": top_n,
            "require_acquisition_readiness": True,
        },
    )
    try:
        scanner = MAProbabilityScanner(knowledge_store=store, config=config)
        return scanner.scan_watchlist(watchlist_assets, top_n=top_n)
    except Exception:
        return None


def _print_mna_section(result: object, *, top_n: int = 10) -> None:
    """Print a compact M&A probability table appended to the weekly report."""
    rows = getattr(result, "rows", [])
    if not rows:
        print("  (no M&A probability rows — check research files and universe stage coverage)")
        return

    print(f"  {'#':>2}  {'TICKER':6s}  {'P(ACQ)':>7}  {'BEST ACQUIRER':22s}  "
          f"{'FIT':>5}  {'DISC':>6}  {'STAGE':10s}  FLAGS")
    print("  " + "-" * 82)
    for row in rows[:top_n]:
        ticker = getattr(row, "ticker", None) or row.asset_id
        p = getattr(row, "p_acquisition", None)
        p_str = f"{p*100:.1f}%" if p is not None else "n/a"
        acquirer = (getattr(row, "best_acquirer_id", None) or "—")[:22]
        fit = getattr(row, "best_acquirer_fit_score", None)
        fit_str = f"{fit:.2f}" if fit is not None else " n/a"
        disc = getattr(row, "acquisition_discount", None)
        disc_str = f"{disc:.2f}x" if disc is not None else "  n/a"
        stage = (getattr(row, "stage", None) or "—")[:10]
        alert = "⚑ ALERT" if getattr(row, "above_alert_threshold", False) else ""
        hard_fails = getattr(row, "hard_fail_reasons", [])
        flags = alert or (hard_fails[0] if hard_fails else "—")
        print(f"  {row.rank:>2}  {ticker:6s}  {p_str:>7}  {acquirer:22s}  "
              f"{fit_str:>5}  {disc_str:>6}  {stage:10s}  {flags}")

    threshold_cross = [r for r in rows if getattr(r, "above_alert_threshold", False)]
    if threshold_cross:
        tickers = ", ".join(getattr(r, "ticker", r.asset_id) or r.asset_id for r in threshold_cross)
        print(f"\n  ⚑ THRESHOLD CROSS (≥70%): {tickers}")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_seed() -> None:
    """First-time setup: insert universe + thesis claims."""
    store = _get_store()
    tt = ThesisTracker(store)

    # Check if already seeded
    existing = store._conn.execute(
        "SELECT COUNT(*) as n FROM thesis_claims"
    ).fetchone()
    if dict(existing)["n"] > 0:
        print(f"Universe already seeded ({dict(existing)['n']} claims). "
              "Use 'status' to view or manually add new claims.")
        store.close()
        return

    print(f"Seeding {len(UNIVERSE)} assets...\n")
    for u in UNIVERSE:
        claim = tt.add_claim(
            asset_id=u["asset_id"],
            company_id=u["company_id"],
            claim_type=u["claim_type"],
            assertion=u["claim_assertion"],
        )
        print(f"  {u['ticker']:6s}  [{u['conviction']:12s}]  {u['claim_type'].value}  → {claim.claim_id}")

    store.close()
    print(f"\nSeeded. DB: {DB_PATH}")


def cmd_report(top_n: int = 5) -> None:
    """Generate weekly actionable report."""
    store = _get_store()
    tt = ThesisTracker(store)
    gen = ActionableGenerator()

    candidates = []
    for u in UNIVERSE:
        snap = tt.snapshot(u["asset_id"])
        n_resolved = snap.n_confirmed + snap.n_refuted + snap.n_expired
        thesis_strength = snap.thesis_strength if n_resolved > 0 else None
        candidates.append(ScoredCandidate(
            asset_id=u["asset_id"],
            ticker=u["ticker"],
            ranking_score=u["ranking_score"],
            opportunity_score=u["opportunity_score"],
            thesis_strength=thesis_strength,
            catalyst_description=u["catalyst"],
            indication=u["indication"],
            company_id=u["company_id"],
        ))

    report = gen.generate(candidates, top_n=top_n, week_ending=date.today())

    print(f"\n{'='*60}")
    print(f"WEEKLY ACTIONABLE REPORT — {report.week_ending}")
    print(f"Score version: {report.score_version}  |  "
          f"Weights: ranking={report.score_weights['ranking']:.0%} "
          f"thesis={report.score_weights['thesis']:.0%} "
          f"opp={report.score_weights['opportunity']:.0%}")
    print(f"Considered: {report.n_considered}  |  "
          f"Actionable: {report.has_actionable}")
    print(f"{'='*60}\n")

    for i, opp in enumerate(report.opportunities, 1):
        action_label = {
            "buy": "🔵 BUY",
            "add": "🟢 ADD",
            "monitor": "🟡 MONITOR",
            "avoid": "🔴 AVOID",
        }.get(opp.recommended_action, opp.recommended_action.upper())

        print(f"  #{i}  {opp.ticker:6s}  {action_label:15s}  "
              f"composite={opp.composite_score:.3f}  "
              f"size={opp.recommended_size_pct:.0%}")
        print(f"       {opp.one_line_summary}")
        if opp.risk_flags:
            print(f"       ⚠ {' | '.join(opp.risk_flags)}")
        print()

    # Save report JSON
    out = DB_PATH.parent / f"report_{report.week_ending}.json"
    out.write_text(report.model_dump_json(indent=2))
    print(f"Saved: {out}")

    # Append M&A probability scan section
    print(f"\n{'='*60}")
    print(f"M&A PROBABILITY SCAN — Top 10  ({date.today()})")
    print(f"{'='*60}\n")
    mna_result = _run_mna_scan(store, top_n=10)
    if mna_result is None:
        print("  (M&A scan skipped — research files not found or scanner unavailable)")
    else:
        _print_mna_section(mna_result, top_n=10)
    print()

    # Implied PoS screen — persist snapshot to KnowledgeStore
    _persist_screen_snapshot(store)

    store.close()
    return report


def _persist_screen_snapshot(store: "KnowledgeStore") -> None:  # type: ignore[name-defined]
    """Run offline implied PoS screen and persist rows to screen_snapshots table."""
    try:
        import warnings as _w
        from bve.analysis.implied_pos_batch import run_screen

        with _w.catch_warnings():
            _w.simplefilter("ignore")
            rows = run_screen(UNIVERSE, fetch_live=False)

        n = store.write_screen_snapshots(rows)
        print(f"  Implied PoS screen: {n} rows persisted to screen_snapshots "
              f"(as_of={date.today().isoformat()})")
    except Exception as exc:  # noqa: BLE001
        print(f"  Implied PoS screen skipped: {exc}")


def cmd_mna_scan(top_n: int = 10) -> None:
    """Standalone M&A probability scan over the weekly UNIVERSE (top-N)."""
    store = _get_store()
    print(f"\n{'='*60}")
    print(f"M&A PROBABILITY SCAN — Top {top_n}  ({date.today()})")
    print(f"{'='*60}\n")
    mna_result = _run_mna_scan(store, top_n=top_n)
    if mna_result is None:
        print("  M&A scan unavailable. Ensure research files exist:")
        print(f"    {_MNA_PROFILES_PATH}")
        print(f"    {_MNA_COMPS_PATH}")
        print(f"    {_MNA_VULN_PATH}")
    else:
        _print_mna_section(mna_result, top_n=top_n)
    print()
    store.close()


def cmd_review() -> None:
    """Run weekly review over last 7 days."""
    store = _get_store()
    dl = DecisionLayer(store)
    tt = ThesisTracker(store)
    engine = WeeklyReviewEngine(store, decision_layer=dl, thesis_tracker=tt)

    report = engine.run_review(week_ending=date.today())

    print(f"\n{'='*60}")
    print(f"WEEKLY REVIEW — {report.week_ending}")
    print(f"{'='*60}")

    f = report.fundamental
    print("\nFUNDAMENTAL ACCURACY")
    print(f"  Resolved forecasts : {f.n_resolved}")
    print(f"  Hit rate           : {f.hit_rate:.1%}" if f.hit_rate else "  Hit rate           : n/a")
    print(f"  Confirmed thesis   : {f.n_confirmed_thesis}")
    print(f"  PoS errors         : {f.n_pos_error}")
    print(f"  Market drift       : {f.n_market_drift}")
    print(f"  Top win            : {report.top_win or 'n/a'}")
    print(f"  Top miss           : {report.top_miss or 'n/a'}")

    t = report.thesis
    print("\nTHESIS ACCURACY")
    print(f"  Key claims confirmed : {t.n_key_claims_confirmed}")
    print(f"  Key claims refuted   : {t.n_key_claims_refuted}")
    net = f"{t.net_thesis_score:.2f}" if t.net_thesis_score is not None else "n/a"
    print(f"  Net thesis score     : {net}")

    m = report.market_timing
    print("\nMARKET TIMING")
    print(f"  Forecasts checked : {m.n_forecasts_checked}")
    pct = f"{m.pct_stale:.1%}" if m.pct_stale is not None else "n/a"
    print(f"  Stale signals     : {m.n_stale_signals}  ({pct})")

    s = report.sizing
    print("\nSIZING QUALITY")
    print(f"  Decisions checked : {s.n_decisions_checked}")
    print(f"  Diverged          : {s.n_recommended_vs_executed_diverged}")

    store.close()


def cmd_status() -> None:
    """Show open claims and active positions."""
    store = _get_store()
    dl = DecisionLayer(store)

    print(f"\n{'='*60}")
    print(f"UNIVERSE STATUS — {date.today()}")
    print(f"{'='*60}\n")

    print(f"{'TICKER':6s}  {'CLAIM TYPE':28s}  {'STATUS':12s}  ASSERTION")
    print("-" * 90)
    for u in UNIVERSE:
        rows = store._conn.execute(
            "SELECT claim_type, status, assertion FROM thesis_claims "
            "WHERE asset_id = ? ORDER BY created_at DESC LIMIT 1",
            (u["asset_id"],),
        ).fetchall()
        for row in rows:
            r = dict(row)
            print(f"  {u['ticker']:6s}  {r['claim_type']:28s}  {r['status']:12s}  {r['assertion'][:55]}")

    positions = dl.get_active_positions()
    if positions:
        print(f"\nACTIVE POSITIONS ({len(positions)})")
        print("-" * 60)
        for p in positions:
            ticker = next((u["ticker"] for u in UNIVERSE if u["asset_id"] == p.asset_id), p.asset_id)
            print(f"  {ticker:6s}  size={p.current_size_pct:.1%}  "
                  f"entry={p.entry_date}  active={p.is_active}")
    else:
        print("\nNo active positions recorded.")

    decisions = dl.get_decision_history(limit=5)
    if decisions:
        print(f"\nRECENT DECISIONS (last {len(decisions)})")
        print("-" * 60)
        for d in decisions:
            ticker = next((u["ticker"] for u in UNIVERSE if u["asset_id"] == d.asset_id), d.asset_id)
            exec_str = f" → executed={d.executed_action}" if d.executed_action else ""
            print(f"  {ticker:6s}  recommended={d.recommended_action}{exec_str}  "
                  f"size={d.recommended_size_pct or 0:.1%}  {d.decided_at.date()}")

    store.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "seed":
        cmd_seed()
    elif cmd == "report":
        cmd_report()
    elif cmd == "review":
        cmd_review()
    elif cmd == "status":
        cmd_status()
    elif cmd == "mna":
        top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        cmd_mna_scan(top_n=top_n)
    else:
        print(__doc__)
