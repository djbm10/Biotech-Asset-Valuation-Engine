"""
Wave 4B — Tests for WeeklyOpportunityBrief model, WeeklyBriefGenerator,
WeeklyBriefRenderer, and CLI helpers.

Coverage:
  - Model defaults and field types (Step 1)
  - Generator: empty store, single diff, accepted/rejected split (Step 2)
  - Generator: event-type counts, net ΔNPV, pending snapshot, top-N (Step 2)
  - Renderer: output contains expected headings and data (Step 3)
  - AcceptedChange and PendingItem models (Step 1)
  - _severity_label helper
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from bve.intelligence.knowledge_layer import KnowledgeStore, SourceTrace
from bve.intelligence.schemas.runs import ReviewDecision
from bve.intelligence.weekly_brief import (
    AcceptedChange,
    PendingItem,
    WeeklyBriefGenerator,
    WeeklyBriefRenderer,
    WeeklyOpportunityBrief,
    _severity_label,
)


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_diff(
    store: KnowledgeStore,
    *,
    run_id: str | None = None,
    asset_id: str = "asset-A",
    event_id: str | None = None,
    delta_npv: float = 50.0,
    event_type: str = "trial_readout",
) -> tuple[str, str]:
    """Insert a valuation_diff + matching event. Returns (run_id, event_id)."""
    run_id = run_id or str(uuid.uuid4())
    event_id = event_id or str(uuid.uuid4())

    store._conn.execute(
        """
        INSERT INTO events
            (id, company_id, asset_id, event_type, observed_at,
             payload_json, source_trace_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id, "co-001", asset_id, event_type,
            _now_iso(),
            json.dumps({"id": event_id, "event_type": event_type}),
            json.dumps({"source_type": "test", "source_ref": "test"}),
        ),
    )
    payload = {
        "run_id": run_id,
        "event_id": event_id,
        "asset_id": asset_id,
        "valuation_before": {"rnpv_millions": 100.0},
        "valuation_after":  {"rnpv_millions": 100.0 + delta_npv},
        "delta_npv": delta_npv,
        "created_at": _now_iso(),
        "valuation_delta": {},
        "assumptions_changed": [
            {
                "parameter_path": "trials[nda].success_probability",
                "before": 0.50,
                "after": 0.65,
                "delta_pct": 30.0,
                "rationale": "Positive readout",
            }
        ],
        "applied_overrides": {},
    }
    store._conn.execute(
        """
        INSERT INTO valuation_diffs
            (run_id, asset_id, event_id, delta_npv, created_at,
             payload_json, source_trace_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id, asset_id, event_id, delta_npv,
            _now_iso(),
            json.dumps(payload),
            json.dumps({"source_type": "test", "source_ref": "test"}),
        ),
    )
    store._conn.commit()
    return run_id, event_id


def _accept_diff(
    store: KnowledgeStore,
    run_id: str,
    *,
    reviewer_id: str = "analyst",
    reviewer_confidence: float = 0.9,
    decision: str = "accepted",
) -> None:
    rec = ReviewDecision(
        id=str(uuid.uuid4()),
        proposal_id=run_id,
        run_id=run_id,
        decision=decision,  # type: ignore[arg-type]
        reviewer_id=reviewer_id,
        reviewed_at=datetime.now(timezone.utc),
        rationale="Test rationale",
        reviewer_confidence=reviewer_confidence,
    )
    store.add_review_decision(
        rec,
        company_id=None,
        asset_id="asset-A",
        source_trace=SourceTrace(source_type="test", source_ref="test"),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def store() -> KnowledgeStore:
    s = KnowledgeStore(db_path=":memory:")
    yield s
    s.close()


@pytest.fixture
def gen() -> WeeklyBriefGenerator:
    return WeeklyBriefGenerator(lookback_days=7, top_n=3)


# ---------------------------------------------------------------------------
# Step 1: Model defaults
# ---------------------------------------------------------------------------

class TestWeeklyOpportunityBriefModel:
    def test_defaults(self) -> None:
        b = WeeklyOpportunityBrief(
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 7),
        )
        assert b.n_signals_processed == 0
        assert b.n_diffs_generated == 0
        assert b.n_accepted == 0
        assert b.n_rejected == 0
        assert b.n_deferred == 0
        assert b.n_pending == 0
        assert b.n_alerts_fired == 0
        assert b.net_delta_npv_accepted_millions == 0.0
        assert b.net_confidence_weighted_delta_npv_millions == 0.0
        assert b.top_opportunities == []
        assert b.accepted_changes == []
        assert b.pending_items == []
        assert b.competitive_developments == []
        assert b.event_type_counts == {}
        assert b.lookback_days == 7
        assert b.top_n == 5

    def test_generated_at_is_utc(self) -> None:
        b = WeeklyOpportunityBrief(
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 7),
        )
        assert b.generated_at.tzinfo is not None

    def test_accepted_change_model(self) -> None:
        ch = AcceptedChange(
            run_id="run-1",
            asset_id="asset-A",
            delta_npv_millions=75.0,
        )
        assert ch.event_type is None
        assert ch.parameter_path is None

    def test_pending_item_model(self) -> None:
        pi = PendingItem(
            run_id="run-2",
            asset_id="asset-B",
            delta_npv_millions=120.0,
            severity="high",
        )
        assert pi.severity == "high"


# ---------------------------------------------------------------------------
# Step 2: Generator
# ---------------------------------------------------------------------------

class TestWeeklyBriefGeneratorEmpty:
    def test_empty_store(self, store: KnowledgeStore, gen: WeeklyBriefGenerator) -> None:
        brief = gen.generate(store)
        assert brief.n_signals_processed == 0
        assert brief.n_diffs_generated == 0
        assert brief.n_reviewed == 0
        assert brief.n_pending == 0
        assert brief.net_delta_npv_accepted_millions == 0.0

    def test_period_dates_set(self, store: KnowledgeStore, gen: WeeklyBriefGenerator) -> None:
        brief = gen.generate(store)
        assert (brief.period_end - brief.period_start).days == gen.lookback_days

    def test_lookback_and_top_n_echoed(self, store: KnowledgeStore, gen: WeeklyBriefGenerator) -> None:
        brief = gen.generate(store)
        assert brief.lookback_days == 7
        assert brief.top_n == 3


class TestWeeklyBriefGeneratorDiffs:
    def test_diffs_counted(self, store: KnowledgeStore, gen: WeeklyBriefGenerator) -> None:
        _insert_diff(store, run_id="run-1")
        _insert_diff(store, run_id="run-2")
        brief = gen.generate(store)
        assert brief.n_diffs_generated == 2

    def test_pending_count(self, store: KnowledgeStore, gen: WeeklyBriefGenerator) -> None:
        _insert_diff(store, run_id="run-p1")
        _insert_diff(store, run_id="run-p2")
        brief = gen.generate(store)
        assert brief.n_pending == 2

    def test_event_type_counts(self, store: KnowledgeStore, gen: WeeklyBriefGenerator) -> None:
        _insert_diff(store, run_id="run-t1", event_type="trial_readout")
        _insert_diff(store, run_id="run-t2", event_type="trial_readout")
        _insert_diff(store, run_id="run-f1", event_type="fda_approval")
        brief = gen.generate(store)
        assert brief.event_type_counts.get("trial_readout", 0) == 2
        assert brief.event_type_counts.get("fda_approval", 0) == 1

    def test_reviewed_vs_pending_split(self, store: KnowledgeStore, gen: WeeklyBriefGenerator) -> None:
        run_a, _ = _insert_diff(store, run_id="run-A")
        run_b, _ = _insert_diff(store, run_id="run-B")
        _accept_diff(store, run_a, decision="accepted")
        brief = gen.generate(store)
        assert brief.n_reviewed == 1
        assert brief.n_accepted == 1
        assert brief.n_pending == 1  # run-B still pending

    def test_n_rejected_counted(self, store: KnowledgeStore, gen: WeeklyBriefGenerator) -> None:
        run_a, _ = _insert_diff(store, run_id="run-rej")
        _accept_diff(store, run_a, decision="rejected")
        brief = gen.generate(store)
        assert brief.n_rejected == 1
        assert brief.n_accepted == 0

    def test_n_deferred_counted(self, store: KnowledgeStore, gen: WeeklyBriefGenerator) -> None:
        run_a, _ = _insert_diff(store, run_id="run-def")
        _accept_diff(store, run_a, decision="deferred")
        brief = gen.generate(store)
        assert brief.n_deferred == 1

    def test_alert_count_and_competitive_updates(self, store: KnowledgeStore, gen: WeeklyBriefGenerator) -> None:
        now = _now_iso()
        store._conn.execute(
            """
            INSERT INTO opportunity_alerts(asset_id, event_type, window, run_id, created_at, payload_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "asset-A",
                "trial_readout",
                "2026-03-09T00:00:00+00:00__2026-03-10T00:00:00+00:00",
                "run-alert",
                now,
                json.dumps({"score": 0.8}),
            ),
        )
        store._conn.execute(
            """
            INSERT INTO competitor_programs(
                program_id, asset_id, company, drug_name, nct_id, phase,
                status, primary_endpoint_type, indication, discovered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "prog-1",
                "asset-A",
                "CompCo",
                "Drug Z",
                "NCT0001",
                "phase_2",
                "RECRUITING",
                "PFS",
                "NSCLC",
                now,
            ),
        )
        store._conn.commit()
        brief = gen.generate(store)
        assert brief.n_alerts_fired == 1
        assert len(brief.competitive_developments) == 1


class TestWeeklyBriefGeneratorNetDelta:
    def test_net_delta_zero_with_no_accepted(
        self, store: KnowledgeStore, gen: WeeklyBriefGenerator
    ) -> None:
        _insert_diff(store, delta_npv=80.0)
        brief = gen.generate(store)
        assert brief.net_delta_npv_accepted_millions == 0.0
        assert brief.net_confidence_weighted_delta_npv_millions == 0.0

    def test_net_delta_single_accepted(
        self, store: KnowledgeStore, gen: WeeklyBriefGenerator
    ) -> None:
        run_id, _ = _insert_diff(store, run_id="run-net", delta_npv=75.0)
        _accept_diff(store, run_id)
        brief = gen.generate(store)
        assert brief.net_delta_npv_accepted_millions == pytest.approx(75.0)

    def test_net_delta_multiple_accepted(
        self, store: KnowledgeStore, gen: WeeklyBriefGenerator
    ) -> None:
        r1, _ = _insert_diff(store, run_id="run-n1", delta_npv=30.0)
        r2, _ = _insert_diff(store, run_id="run-n2", delta_npv=45.0)
        _accept_diff(store, r1)
        _accept_diff(store, r2)
        brief = gen.generate(store)
        assert brief.net_delta_npv_accepted_millions == pytest.approx(75.0)

    def test_net_delta_negative_accepted(
        self, store: KnowledgeStore, gen: WeeklyBriefGenerator
    ) -> None:
        run_id, _ = _insert_diff(store, run_id="run-neg", delta_npv=-60.0)
        _accept_diff(store, run_id)
        brief = gen.generate(store)
        assert brief.net_delta_npv_accepted_millions == pytest.approx(-60.0)

    def test_confidence_weighted_delta_with_full_confidence(
        self, store: KnowledgeStore, gen: WeeklyBriefGenerator
    ) -> None:
        # confidence=1.0 → weighted == raw
        run_id, _ = _insert_diff(store, run_id="run-cw1", delta_npv=100.0)
        _accept_diff(store, run_id, reviewer_confidence=1.0)
        brief = gen.generate(store)
        assert brief.net_confidence_weighted_delta_npv_millions == pytest.approx(100.0)

    def test_confidence_weighted_delta_down_weights(
        self, store: KnowledgeStore, gen: WeeklyBriefGenerator
    ) -> None:
        # confidence=0.5 → weighted = 50.0
        run_id, _ = _insert_diff(store, run_id="run-cw2", delta_npv=100.0)
        _accept_diff(store, run_id, reviewer_confidence=0.5)
        brief = gen.generate(store)
        assert brief.net_confidence_weighted_delta_npv_millions == pytest.approx(50.0)
        assert brief.net_delta_npv_accepted_millions == pytest.approx(100.0)

    def test_confidence_none_treated_as_one(
        self, store: KnowledgeStore, gen: WeeklyBriefGenerator
    ) -> None:
        # No confidence set → weight defaults to 1.0
        run_id, _ = _insert_diff(store, run_id="run-cw3", delta_npv=80.0)
        # Manually insert a decision with no reviewer_confidence
        from bve.intelligence.schemas.runs import ReviewDecision
        import uuid as _uuid
        rec = ReviewDecision(
            id=str(_uuid.uuid4()),
            proposal_id=run_id,
            run_id=run_id,
            decision="accepted",
            reviewer_id="anon",
            reviewed_at=datetime.now(timezone.utc),
            rationale="no conf",
            reviewer_confidence=None,
        )
        store.add_review_decision(
            rec,
            company_id=None,
            asset_id="asset-A",
            source_trace=SourceTrace(source_type="test", source_ref="test"),
        )
        brief = gen.generate(store)
        assert brief.net_confidence_weighted_delta_npv_millions == pytest.approx(80.0)

    def test_accepted_change_has_weighted_field(
        self, store: KnowledgeStore, gen: WeeklyBriefGenerator
    ) -> None:
        run_id, _ = _insert_diff(store, run_id="run-cwf", delta_npv=60.0)
        _accept_diff(store, run_id, reviewer_confidence=0.75)
        brief = gen.generate(store)
        ch = brief.accepted_changes[0]
        assert ch.delta_npv_millions == pytest.approx(60.0)
        assert ch.confidence_weighted_delta_npv_millions == pytest.approx(45.0)


class TestWeeklyBriefGeneratorAcceptedChanges:
    def test_accepted_change_populated(
        self, store: KnowledgeStore, gen: WeeklyBriefGenerator
    ) -> None:
        run_id, _ = _insert_diff(store, run_id="run-ch", asset_id="asset-X", delta_npv=80.0)
        _accept_diff(store, run_id, reviewer_id="analyst-dj", reviewer_confidence=0.85)
        brief = gen.generate(store)
        assert len(brief.accepted_changes) == 1
        ch = brief.accepted_changes[0]
        assert ch.asset_id == "asset-X"
        assert ch.delta_npv_millions == pytest.approx(80.0)
        assert ch.reviewer_id == "analyst-dj"
        assert ch.reviewer_confidence == pytest.approx(0.85)

    def test_accepted_changes_sorted_by_abs_delta(
        self, store: KnowledgeStore, gen: WeeklyBriefGenerator
    ) -> None:
        for run_id, delta in [("run-s1", 30.0), ("run-s2", 90.0), ("run-s3", 10.0)]:
            rid, _ = _insert_diff(store, run_id=run_id, delta_npv=delta)
            _accept_diff(store, rid)
        brief = gen.generate(store)
        deltas = [c.delta_npv_millions for c in brief.accepted_changes]
        assert deltas == sorted(deltas, key=abs, reverse=True)

    def test_parameter_path_extracted(
        self, store: KnowledgeStore, gen: WeeklyBriefGenerator
    ) -> None:
        run_id, _ = _insert_diff(store, run_id="run-param")
        _accept_diff(store, run_id)
        brief = gen.generate(store)
        assert brief.accepted_changes[0].parameter_path == "trials[nda].success_probability"


class TestWeeklyBriefGeneratorPendingItems:
    def test_pending_items_by_magnitude(
        self, store: KnowledgeStore, gen: WeeklyBriefGenerator
    ) -> None:
        _insert_diff(store, run_id="run-pi1", delta_npv=150.0)
        _insert_diff(store, run_id="run-pi2", delta_npv=20.0)
        _insert_diff(store, run_id="run-pi3", delta_npv=60.0)
        brief = gen.generate(store)
        # top_n=3; all three pending; sorted by |ΔNPV| desc
        magnitudes = [abs(p.delta_npv_millions) for p in brief.pending_items]
        assert magnitudes == sorted(magnitudes, reverse=True)

    def test_pending_items_capped_at_top_n(
        self, store: KnowledgeStore, gen: WeeklyBriefGenerator
    ) -> None:
        for i in range(6):
            _insert_diff(store, run_id=f"run-cap-{i}", delta_npv=float(i * 10))
        brief = gen.generate(store)
        assert len(brief.pending_items) <= gen.top_n

    def test_pending_item_severity(
        self, store: KnowledgeStore, gen: WeeklyBriefGenerator
    ) -> None:
        _insert_diff(store, run_id="run-sev1", delta_npv=150.0)
        _insert_diff(store, run_id="run-sev2", delta_npv=50.0)
        _insert_diff(store, run_id="run-sev3", delta_npv=10.0)
        brief = gen.generate(store)
        sev_map = {p.delta_npv_millions: p.severity for p in brief.pending_items}
        assert sev_map[150.0] == "high"
        assert sev_map[50.0] == "medium"
        assert sev_map[10.0] == "low"

    def test_reviewed_excluded_from_pending_items(
        self, store: KnowledgeStore, gen: WeeklyBriefGenerator
    ) -> None:
        run_id, _ = _insert_diff(store, run_id="run-ex")
        _accept_diff(store, run_id)
        brief = gen.generate(store)
        assert all(p.run_id != run_id for p in brief.pending_items)


class TestWeeklyBriefGeneratorTopOpportunities:
    def test_top_opportunities_not_empty_with_diffs(
        self, store: KnowledgeStore, gen: WeeklyBriefGenerator
    ) -> None:
        _insert_diff(store, run_id="run-opp1", asset_id="A1", delta_npv=80.0)
        _insert_diff(store, run_id="run-opp2", asset_id="A2", delta_npv=40.0)
        brief = gen.generate(store)
        assert len(brief.top_opportunities) >= 1

    def test_top_opportunities_capped_at_top_n(
        self, store: KnowledgeStore, gen: WeeklyBriefGenerator
    ) -> None:
        for i in range(10):
            _insert_diff(store, run_id=f"run-top-{i}", asset_id=f"asset-{i}", delta_npv=float(i * 10))
        brief = gen.generate(store)
        assert len(brief.top_opportunities) <= gen.top_n

    def test_top_opportunities_have_rank(
        self, store: KnowledgeStore, gen: WeeklyBriefGenerator
    ) -> None:
        for i in range(3):
            _insert_diff(store, run_id=f"run-rk-{i}", asset_id=f"asset-rk-{i}", delta_npv=float(i * 20))
        brief = gen.generate(store)
        ranks = [opp["rank"] for opp in brief.top_opportunities]
        assert ranks == list(range(1, len(ranks) + 1))

    def test_top_opportunities_deduped_by_asset(
        self, store: KnowledgeStore, gen: WeeklyBriefGenerator
    ) -> None:
        # Two diffs for same asset — only one entry in top_opportunities
        _insert_diff(store, run_id="run-dup1", asset_id="asset-dup", delta_npv=60.0)
        _insert_diff(store, run_id="run-dup2", asset_id="asset-dup", delta_npv=30.0)
        brief = gen.generate(store)
        asset_ids = [opp["asset_id"] for opp in brief.top_opportunities]
        assert asset_ids.count("asset-dup") == 1

    def test_top_opportunities_prefer_company_sotp_snapshots(
        self, store: KnowledgeStore, gen: WeeklyBriefGenerator
    ) -> None:
        snapshot_date = date.today()
        store.write_company_sotp_snapshots(
            [
                SimpleNamespace(
                    ticker="AAA",
                    company_id="co-aaa",
                    company_name="AAA Bio",
                    snapshot_date=snapshot_date,
                    rank=1,
                    market_cap_millions=600.0,
                    enterprise_value_millions=500.0,
                    sotp_equity_value_millions=900.0,
                    sotp_per_share=9.0,
                    sotp_discount=1.5,
                    ranked_sotp_discount=1.6,
                    modeled_asset_coverage_pct=0.85,
                    asset_count_modeled=1,
                    modeled_asset_ids=["asset-aaa"],
                    config_quality_summary="curated",
                    modeled_asset_confidence_min=0.9,
                    modeled_asset_confidence_avg=0.9,
                    action_policy="buy",
                    action_reason="ranked_discount_above_buy_threshold:1.60x",
                    market_cap_source="unit_test",
                    balance_sheet_source="sec_edgar_company_facts",
                    balance_sheet_source_ref="unit-test",
                    balance_sheet_snapshot_date=snapshot_date,
                    balance_sheet_period_end_date=snapshot_date,
                    balance_sheet_form_type="10-Q",
                    balance_sheet_is_point_in_time=True,
                    balance_sheet_age_days=7,
                    balance_sheet_passes_recency_gate=True,
                    balance_sheet_recency_penalty=1.0,
                    buckets=[],
                    limitations=[],
                    notes=None,
                )
            ]
        )
        _insert_diff(store, run_id="run-opp-fallback", asset_id="asset-diff", delta_npv=90.0)

        brief = gen.generate(store)

        assert brief.top_opportunities_source_mode == "company_sotp_snapshot"
        assert brief.top_opportunities_reference_date == snapshot_date
        assert brief.top_opportunities[0]["ticker"] == "AAA"
        assert brief.top_opportunities[0]["action_policy"] == "buy"


# ---------------------------------------------------------------------------
# _severity_label helper
# ---------------------------------------------------------------------------

class TestSeverityLabel:
    def test_none_is_low(self) -> None:
        assert _severity_label(None) == "low"

    def test_above_100_high(self) -> None:
        assert _severity_label(150.0) == "high"
        assert _severity_label(-110.0) == "high"

    def test_25_to_100_medium(self) -> None:
        assert _severity_label(50.0) == "medium"
        assert _severity_label(25.0) == "medium"

    def test_below_25_low(self) -> None:
        assert _severity_label(10.0) == "low"
        assert _severity_label(0.0) == "low"


# ---------------------------------------------------------------------------
# Step 3: Renderer
# ---------------------------------------------------------------------------

class TestWeeklyBriefRenderer:
    def _make_brief(self) -> WeeklyOpportunityBrief:
        return WeeklyOpportunityBrief(
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 7),
            n_signals_processed=12,
            n_diffs_generated=5,
            n_reviewed=3,
            n_accepted=2,
            n_rejected=1,
            n_deferred=0,
            n_pending=2,
            net_delta_npv_accepted_millions=95.0,
            event_type_counts={"trial_readout": 3, "fda_approval": 2},
            accepted_changes=[
                AcceptedChange(
                    run_id="run-1",
                    asset_id="asset-A",
                    event_type="trial_readout",
                    delta_npv_millions=75.0,
                    confidence_weighted_delta_npv_millions=67.5,
                    parameter_path="trials[nda].success_probability",
                    reviewer_id="analyst-dj",
                    reviewer_confidence=0.9,
                    reviewed_at="2025-01-05",
                )
            ],
            pending_items=[
                PendingItem(
                    run_id="run-p1",
                    asset_id="asset-B",
                    event_type="fda_approval",
                    delta_npv_millions=120.0,
                    severity="high",
                    created_at="2025-01-03",
                )
            ],
            top_opportunities=[
                {
                    "rank": 1,
                    "asset_id": "asset-A",
                    "delta_npv_millions": 75.0,
                    "composite_score": 0.812,
                    "signal_event_type": "trial_readout",
                    "extraction_confidence": 0.88,
                    "mispricing_score": None,
                }
            ],
        )

    def test_render_returns_string(self) -> None:
        renderer = WeeklyBriefRenderer()
        brief = self._make_brief()
        output = renderer.render(brief)
        assert isinstance(output, str)
        assert len(output) > 100

    def test_render_contains_period(self) -> None:
        renderer = WeeklyBriefRenderer()
        brief = self._make_brief()
        output = renderer.render(brief)
        assert "2025-01-01" in output
        assert "2025-01-07" in output

    def test_render_contains_throughput_stats(self) -> None:
        renderer = WeeklyBriefRenderer()
        brief = self._make_brief()
        output = renderer.render(brief)
        assert "12" in output   # n_signals_processed
        assert "5" in output    # n_diffs_generated

    def test_render_contains_accepted_change(self) -> None:
        renderer = WeeklyBriefRenderer()
        brief = self._make_brief()
        output = renderer.render(brief)
        assert "asset-A" in output
        assert "analyst-dj" in output

    def test_render_contains_net_delta(self) -> None:
        renderer = WeeklyBriefRenderer()
        brief = self._make_brief()
        output = renderer.render(brief)
        assert "95" in output   # net delta $95M

    def test_render_contains_pending_item(self) -> None:
        renderer = WeeklyBriefRenderer()
        brief = self._make_brief()
        output = renderer.render(brief)
        assert "asset-B" in output

    def test_render_contains_top_opportunity(self) -> None:
        renderer = WeeklyBriefRenderer()
        brief = self._make_brief()
        output = renderer.render(brief)
        assert "0.812" in output   # composite score

    def test_render_empty_brief(self) -> None:
        renderer = WeeklyBriefRenderer()
        brief = WeeklyOpportunityBrief(
            period_start=date(2025, 1, 1),
            period_end=date(2025, 1, 7),
        )
        output = renderer.render(brief)
        assert "Weekly Opportunity Brief" in output
        assert "empty" in output.lower() or "0" in output

    def test_render_event_type_distribution(self) -> None:
        renderer = WeeklyBriefRenderer()
        brief = self._make_brief()
        output = renderer.render(brief)
        assert "trial_readout" in output
        assert "fda_approval" in output
