"""
Weekly operational runner — seeds universe, runs actionable report, records decisions.

Usage:
    python -m bve.ops.weekly_runner seed       # first-time setup
    python -m bve.ops.weekly_runner report     # generate weekly actionable report
    python -m bve.ops.weekly_runner review     # run weekly review (after outcomes)
    python -m bve.ops.weekly_runner status     # show current positions + open claims
    python -m bve.ops.weekly_runner mna        # standalone M&A probability scan (top-15)
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Optional

from bve.intelligence.actionable_output import ActionableGenerator, ScoredCandidate
from bve.intelligence.decision_layer import DecisionLayer
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.thesis_tracker import ThesisTracker
from bve.intelligence.weekly_review import WeeklyReviewEngine
from bve.ops.universe_data import UNIVERSE

# ---------------------------------------------------------------------------
# Persistent DB path
# ---------------------------------------------------------------------------

DB_PATH = Path(__file__).parent.parent.parent.parent / "outputs" / "intelligence" / "ops.db"
SHADOW_BOOK_PATH = DB_PATH.parent / "shadow_book.db"
MIN_SHADOW_BOOK_SCORE = 0.55


def _get_store() -> KnowledgeStore:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return KnowledgeStore(str(DB_PATH))


# ---------------------------------------------------------------------------
# Universe definition — imported from bve.ops.universe_data
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# M&A research file paths (relative to repo root)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent.parent.parent
_MNA_PROFILES_PATH = str(_REPO_ROOT / "examples" / "research" / "acquirer_profiles")
_MNA_COMPS_PATH    = str(_REPO_ROOT / "research" / "mna" / "comparable_deals.yaml")
_MNA_VULN_PATH     = str(_REPO_ROOT / "research" / "mna" / "vulnerability_signals.yaml")
# Watchlist YAML that maps tracked tickers -> existing valuation configs. Used to
# attach configs to the M&A scan so the acquisition screener can run rNPV/EV
# inline (populating the coarse investment lens of the dual-track screen).
_MNA_VALUATION_WATCHLIST = str(
    _REPO_ROOT / "examples" / "configs" / "watchlists" / "watchlist_replay_expanded_phase2.yaml"
)
# Hand-authored provisional CURRENT configs for high-conviction names with no PIT
# replay config. Merged AFTER the replay watchlist so it only fills coverage gaps
# and never overrides a point-in-time config.
_MNA_PROVISIONAL_WATCHLIST = str(
    _REPO_ROOT / "examples" / "configs" / "watchlists" / "watchlist_provisional.yaml"
)
# Pipeline-generated coarse configs (bve-profile gen-config --all). Merged LAST so
# it only fills names still uncovered after the replay + provisional watchlists.
_MNA_AUTO_GENERATED_WATCHLIST = str(
    _REPO_ROOT / "examples" / "configs" / "watchlists" / "watchlist_auto_generated.yaml"
)
_MNA_CALIBRATION_CANDIDATES = [
    _REPO_ROOT / "outputs" / "analysis" / "ma_calibration_fit_post_step2.json",
    _REPO_ROOT / "outputs" / "analysis" / "ma_calibration_fit.json",
]


def _resolve_mna_calibration_model_path() -> str | None:
    for candidate in _MNA_CALIBRATION_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    return None


def _load_valuation_config_map(watchlist_path: str = _MNA_VALUATION_WATCHLIST) -> dict[str, str]:
    """Map ``TICKER -> absolute valuation_config path`` from a watchlist YAML.

    The M&A scan attaches these configs to its watchlist assets so the
    acquisition screener can run rNPV/EV inline. Tickers with no mapped config —
    or whose config file is absent on disk — are simply omitted, so those names
    degrade to an honest ``missing_valuation_config`` / ``not_assessed`` rather
    than a fabricated verdict. Returns an empty map on any load/parse failure so
    the scan still runs.
    """
    import yaml

    path = Path(watchlist_path)
    if not path.exists():
        return {}
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}

    entries = raw.get("watchlist", []) if isinstance(raw, dict) else []
    config_map: dict[str, str] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        ticker = entry.get("ticker")
        cfg = entry.get("valuation_config")
        if not ticker or not cfg:
            continue
        ticker_key = str(ticker).upper()
        if ticker_key in config_map:
            continue  # keep first occurrence — stable, deterministic
        cfg_path = Path(cfg)
        if not cfg_path.is_absolute():
            cfg_path = _REPO_ROOT / cfg_path
        if not cfg_path.exists():
            continue
        config_map[ticker_key] = str(cfg_path.resolve())
    return config_map


def _mna_config_map() -> dict[str, str]:
    """Merged ``TICKER -> config path`` map used by the M&A scan.

    The replay watchlist provides the point-in-time configs; the provisional and
    pipeline auto-generated watchlists fill coverage gaps only (``setdefault`` →
    never override a PIT or provisional config). Exposed so the dual-track screen
    can classify name liveness from the config source.
    """
    config_map = _load_valuation_config_map()
    for gap_watchlist in (_MNA_PROVISIONAL_WATCHLIST, _MNA_AUTO_GENERATED_WATCHLIST):
        for ticker_key, cfg_path in _load_valuation_config_map(gap_watchlist).items():
            config_map.setdefault(ticker_key, cfg_path)
    return config_map


def _build_mna_watchlist(config_map: Optional[dict[str, str]] = None) -> list:
    """Build the M&A scan ``WatchlistAsset`` list from UNIVERSE.

    Existing valuation configs are attached by ticker (via
    :func:`_load_valuation_config_map`) so the acquisition screener can compute
    rNPV/EV inline. Names with no mapped config keep ``valuation_config=None``
    and stay honestly ``not_assessed`` on the investment lens.
    """
    from bve.pipeline.watchlist_runner import WatchlistAsset

    if config_map is None:
        config_map = _mna_config_map()

    # Deduplicate by asset_id — UNIVERSE lists some assets twice (across conviction
    # tiers), which otherwise produces duplicate scan rows for one ticker (and,
    # via independent acquirer tie-breaks, even two different "natural acquirers").
    assets: list = []
    seen_asset_ids: set[str] = set()
    for u in UNIVERSE:
        asset_id = u["asset_id"]
        if asset_id in seen_asset_ids:
            continue
        seen_asset_ids.add(asset_id)
        ticker = u.get("ticker")
        assets.append(
            WatchlistAsset(
                company_id=u["company_id"],
                asset_id=asset_id,
                ticker=ticker,
                indication=u.get("indication"),
                valuation_config=(
                    config_map.get(str(ticker).upper()) if ticker else None
                ),
            )
        )
    return assets


def _run_mna_scan(store: KnowledgeStore, top_n: int = 15) -> Optional[object]:
    """
    Run the M&A probability scan over the weekly UNIVERSE and return
    `MAProbabilityResult`, or None if research files are unavailable.
    """
    # Lazy import to avoid top-level import cost on every runner invocation
    try:
        from bve.intelligence.ma_probability import MAProbabilityConfig, MAProbabilityScanner
    except ImportError:
        return None

    if not all(Path(p).exists() for p in [_MNA_PROFILES_PATH, _MNA_COMPS_PATH, _MNA_VULN_PATH]):
        return None

    # Build WatchlistAsset list from UNIVERSE, attaching existing valuation
    # configs by ticker so the screener can populate the coarse investment lens.
    try:
        watchlist_assets = _build_mna_watchlist()
    except ImportError:
        return None

    config = MAProbabilityConfig(
        top_n=top_n,
        alert_threshold=0.70,
        vulnerability_signals_path=_MNA_VULN_PATH,
        persist_daily_snapshots=True,   # auto-log every scan run for calibration
        enable_monitor=False,
        calibration_model_path=_resolve_mna_calibration_model_path(),
        calibration_policy="display_only",
        calibration_threshold=0.10,
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


def _print_mna_section(result: object, *, top_n: int = 15) -> None:
    """Print a compact M&A probability table appended to the weekly report."""
    rows = getattr(result, "rows", [])
    if not rows:
        print("  (no M&A probability rows — check research files and universe stage coverage)")
        return

    print(
        f"  {'#':>2}  {'TICKER':6s}  {'M&A':>7}  {'CAL':>7}  {'BEST ACQUIRER':22s}  "
        f"{'DEAL RANGE':18s}  {'FIT':>5}  {'DISC':>6}  {'D-RISK':>6}  {'CAPV':>5}  FLAGS"
    )
    print("  " + "-" * 133)
    for row in rows[:top_n]:
        ticker = getattr(row, "ticker", None) or row.asset_id
        p = getattr(row, "mna_probability_score", None)
        p_str = f"{p*100:.1f}%" if p is not None else "n/a"
        p_cal = getattr(row, "p_takeout_calibrated", None)
        p_cal_str = f"{p_cal*100:.1f}%" if p_cal is not None else "n/a"
        acquirer = (getattr(row, "best_acquirer_id", None) or "—")[:22]
        deal_low = getattr(row, "estimated_deal_value_low_millions", None)
        deal_high = getattr(row, "estimated_deal_value_high_millions", None)
        if deal_low is not None and deal_high is not None:
            if deal_low >= 1000 or deal_high >= 1000:
                deal_range = f"${deal_low/1000.0:.1f}B-${deal_high/1000.0:.1f}B"
            else:
                deal_range = f"${deal_low:,.0f}M-${deal_high:,.0f}M"
        else:
            deal_range = "n/a"
        fit = getattr(row, "best_acquirer_fit_score", None)
        fit_str = f"{fit:.2f}" if fit is not None else " n/a"
        disc = getattr(row, "acquisition_discount", None)
        disc_str = f"{disc:.2f}x" if disc is not None else "  n/a"
        d_risk = getattr(row, "de_risking_stage_score", None)
        d_risk_str = f"{d_risk:.2f}" if d_risk is not None else " n/a"
        capv = getattr(row, "capital_vulnerability_score", None)
        capv_str = f"{capv:.2f}" if capv is not None else " n/a"
        alert = "⚑ ALERT" if getattr(row, "above_alert_threshold", False) else ""
        hard_fails = getattr(row, "hard_fail_reasons", [])
        flags = alert or (hard_fails[0] if hard_fails else "—")
        print(
            f"  {row.rank:>2}  {ticker:6s}  {p_str:>7}  {p_cal_str:>7}  {acquirer:22s}  "
            f"{deal_range:18s}  {fit_str:>5}  {disc_str:>6}  {d_risk_str:>6}  "
            f"{capv_str:>5}  {flags}"
        )

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
        company_snapshot = store.get_company_sotp_snapshot_for_ticker_on_or_before(
            str(u["ticker"]),
            date.today(),
        )
        candidates.append(ScoredCandidate(
            asset_id=u["asset_id"],
            ticker=u["ticker"],
            ranking_score=u["ranking_score"],
            opportunity_score=u["opportunity_score"],
            thesis_strength=thesis_strength,
            catalyst_description=u["catalyst"],
            indication=u["indication"],
            company_id=u["company_id"],
            company_action_policy=(
                str(company_snapshot.get("action_policy"))
                if company_snapshot and company_snapshot.get("action_policy")
                else None
            ),
            company_action_reason=(
                str(company_snapshot.get("action_reason"))
                if company_snapshot and company_snapshot.get("action_reason")
                else ""
            ),
            company_snapshot_date=(
                company_snapshot.get("snapshot_date")
                if company_snapshot is not None
                else None
            ),
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
    _register_shadow_book_candidates(store, report)

    # Append M&A probability scan section
    print(f"\n{'='*60}")
    print(f"M&A PROBABILITY SCAN — Top 15  ({date.today()})")
    print(f"{'='*60}\n")
    mna_result = _run_mna_scan(store, top_n=15)
    if mna_result is None:
        print("  (M&A scan skipped — research files not found or scanner unavailable)")
    else:
        _print_mna_section(mna_result, top_n=15)
        n_snaps = getattr(mna_result, "snapshots_written", 0)
        print(f"\n  Prediction log: {n_snaps} snapshot rows written to ops.db "
              f"(date={date.today().isoformat()})")
        n_fit = _log_acquirer_fit_predictions_from_mna_result(mna_result)
        if n_fit:
            print(f"  Acquirer-fit log: {n_fit} fit prediction records written to "
                  f"acquirer_fit_log.db")
    print()

    # Implied PoS screen — persist snapshot to KnowledgeStore
    _persist_screen_snapshot(store)

    store.close()
    return report


def _register_shadow_book_candidates(store: KnowledgeStore, report: object) -> int:
    """Pre-register qualifying add signals in the prospective shadow book."""
    from bve.analysis.shadow_book import ShadowBook

    today = date.today()
    book = ShadowBook(SHADOW_BOOK_PATH)
    book.initialize()
    n_registered = 0
    for opp in getattr(report, "opportunities", []):
        if getattr(opp, "recommended_action", None) != "add":
            continue
        score = float(getattr(opp, "composite_score", 0.0) or 0.0)
        if score < MIN_SHADOW_BOOK_SCORE:
            continue
        catalyst_date = getattr(opp, "catalyst_date", None)
        if catalyst_date is None:
            continue
        if isinstance(catalyst_date, str):
            try:
                catalyst_date = date.fromisoformat(catalyst_date[:10])
            except ValueError:
                continue
        if catalyst_date <= today:
            continue
        ticker = str(getattr(opp, "ticker", "") or "")
        price_record = store.get_latest_price(ticker) if ticker else None
        entry_price = getattr(price_record, "adj_close_usd", None) or getattr(
            price_record, "close_usd", None
        )
        if entry_price is None or float(entry_price) <= 0.0:
            print(f"  Shadow book skipped for {ticker}: missing entry price")
            continue
        book.register(
            ticker=ticker,
            asset_id=str(getattr(opp, "asset_id", "") or ""),
            model_score=score,
            entry_price_usd=float(entry_price),
            entry_date=today.isoformat(),
            catalyst_date=catalyst_date.isoformat(),
            catalyst_type=str(getattr(opp, "catalyst_type", "unknown") or "unknown"),
            rationale=str(
                getattr(opp, "rationale", "")
                or getattr(opp, "one_line_summary", "")
                or ""
            ),
            max_hold_days=28,
        )
        n_registered += 1
    if n_registered:
        print(f"  Shadow book: {n_registered} qualifying add signal(s) registered")
    return n_registered


def _persist_screen_snapshot(store: "KnowledgeStore") -> None:  # type: ignore[name-defined]
    """Run offline implied PoS screen and persist rows to screen_snapshots table.

    Injects thesis_strength per ticker from ThesisTracker.snapshot() so the
    screen record captures claim health at the time of screening.
    """
    try:
        import warnings as _w
        from bve.analysis.implied_pos_batch import run_screen

        with _w.catch_warnings():
            _w.simplefilter("ignore")
            rows = run_screen(UNIVERSE, fetch_live=False)

        # Attach thesis_strength from KnowledgeStore
        tt = ThesisTracker(store)
        asset_id_by_ticker = {
            u["ticker"]: u["asset_id"] for u in UNIVERSE if "asset_id" in u
        }
        enriched = []
        for row in rows:
            asset_id = asset_id_by_ticker.get(row.ticker)
            if asset_id:
                snap = tt.snapshot(asset_id)
                n_resolved = snap.n_confirmed + snap.n_refuted + snap.n_expired
                thesis_strength = snap.thesis_strength if n_resolved > 0 else None
            else:
                thesis_strength = None
            from dataclasses import replace
            enriched.append(replace(row, thesis_strength=thesis_strength))

        n = store.write_screen_snapshots(enriched)
        print(f"  Implied PoS screen: {n} rows persisted to screen_snapshots "
              f"(as_of={date.today().isoformat()})")
    except Exception as exc:  # noqa: BLE001
        print(f"  Implied PoS screen skipped: {exc}")


def _log_acquirer_fit_predictions_from_mna_result(result: object) -> int:
    """Persist per-acquirer fit prediction logs from an MAProbabilityResult.

    Groups ranked rows by best_acquirer_id and calls log_fit_predictions() for
    each acquirer so the acquirer-fit log can be graded when deals close.

    Returns total number of prediction records written.
    """
    try:
        from bve.intelligence.acquirer_fit_log import log_fit_predictions
        import types
    except ImportError:
        return 0

    rows = getattr(result, "rows", [])
    if not rows:
        return 0

    today_str = date.today().isoformat()
    store_path = DB_PATH.parent / "acquirer_fit_log.db"

    # Group targets by their best acquirer
    by_acquirer: dict[str, list] = {}
    for row in rows:
        acq = getattr(row, "best_acquirer_id", None)
        if not acq:
            continue
        by_acquirer.setdefault(acq, []).append(row)

    total = 0
    for acquirer_id, acq_rows in by_acquirer.items():
        # Re-rank by acquirer fit score (desc) within this acquirer's universe
        acq_rows.sort(key=lambda r: -(getattr(r, "best_acquirer_fit_score", 0.0) or 0.0))
        log_rows = []
        for rank_idx, row in enumerate(acq_rows, start=1):
            log_rows.append(types.SimpleNamespace(
                asset_id=row.asset_id,
                ticker=getattr(row, "ticker", None),
                therapeutic_area=getattr(row, "therapeutic_area", None),
                stage=getattr(row, "stage", None),
                rank=rank_idx,
                fit_score=float(getattr(row, "best_acquirer_fit_score", 0.0) or 0.0),
            ))
        ids = log_fit_predictions(
            store_path,
            acquirer_id=acquirer_id,
            screen_date=today_str,
            rows=log_rows,
            overwrite_same_date=True,
        )
        total += len(ids)
    return total


def cmd_mna_scan(top_n: int = 15) -> None:
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
        n_snaps = getattr(mna_result, "snapshots_written", 0)
        print(f"\n  Prediction log: {n_snaps} snapshot rows written to ops.db "
              f"(date={date.today().isoformat()})")
        n_fit = _log_acquirer_fit_predictions_from_mna_result(mna_result)
        if n_fit:
            print(f"  Acquirer-fit log: {n_fit} fit prediction records written to "
                  f"acquirer_fit_log.db")
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

    p = report.policy_audit
    print("\nPOLICY AUDIT")
    print(f"  Snapshots         : {p.n_policy_snapshots}")
    print(f"  Buy/Add           : {p.n_buy}/{p.n_add}")
    print(f"  Monitor/Avoid     : {p.n_monitor}/{p.n_avoid}")
    avg_size = f"{p.avg_sizing_pct:.2f}%" if p.avg_sizing_pct is not None else "n/a"
    print(f"  Avg size          : {avg_size}")
    print(f"  Gate-blocked      : {p.n_blocked_by_company_gate}")

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
