"""Tests for score_update persistence + the weekly-runner signal-scoring helper."""
from __future__ import annotations

import datetime as dt
import uuid
from pathlib import Path

from bve.entities.trial import TrialPhase
from bve.intelligence.actionable_output import ScoredCandidate
from bve.intelligence.knowledge_layer import (
    KnowledgeStore,
    ScoreUpdateRecord,
    SourceTrace,
)
from bve.intelligence.schemas.signals import StructuredSignal
from bve.intelligence.score_context_builder import build_score_contexts
from bve.intelligence.taxonomy import EventType
from bve.ops.weekly_runner import _scores_with_signal_contexts

_TODAY = dt.date(2026, 6, 16)
_ST = SourceTrace(source_type="manual", source_ref="test")


def _store(tmp_path) -> KnowledgeStore:
    return KnowledgeStore(Path(tmp_path) / "ops.db")


def _seed_signal(store, asset_id, **fields):
    base = dict(
        id=f"sig-{asset_id}", event_id=f"evt-{asset_id}", asset_id=asset_id, company_id="co",
        event_type=EventType.TRIAL_READOUT, signal_date=_TODAY - dt.timedelta(days=3),
        trial_phase=TrialPhase.PHASE_3, extraction_model="t", extraction_confidence=0.9,
        created_at=dt.datetime(2026, 6, 13, tzinfo=dt.timezone.utc),
    )
    base.update(fields)
    store.add_structured_signal(StructuredSignal(**base), _ST, extraction_result_id=f"x-{asset_id}")


# ── Persistence round-trip ───────────────────────────────────────────────────────

class TestScoreUpdatePersistence:
    def test_round_trip(self, tmp_path):
        store = _store(tmp_path)
        rec = ScoreUpdateRecord(
            id=str(uuid.uuid4()), run_id="weekly-2026-06-16", asset_id="asset-A",
            as_of=_TODAY, prior_score=0.50, new_score=0.62, delta=0.12,
            components={"endpoint_z": 0.1, "catalyst_ev": 0.02},
            contributing_signal_ids=["s1"], contributing_event_ids=["e1"],
        )
        store.add_score_update(rec, source_trace=_ST)
        got = store.get_score_updates(asset_id="asset-A")
        assert len(got) == 1
        assert got[0].delta == 0.12
        assert got[0].prior_score == 0.50
        assert got[0].contributing_event_ids == ["e1"]
        assert got[0].components["endpoint_z"] == 0.1
        store.close()

    def test_filter_by_run_id_and_ordering(self, tmp_path):
        store = _store(tmp_path)
        for i, run in enumerate(["weekly-1", "weekly-1", "weekly-2"]):
            store.add_score_update(
                ScoreUpdateRecord(
                    id=str(uuid.uuid4()), run_id=run, asset_id=f"a{i}", as_of=_TODAY,
                    prior_score=0.4, new_score=0.5, delta=0.1,
                    created_at=dt.datetime(2026, 6, 16, 0, i, tzinfo=dt.timezone.utc),
                ),
                source_trace=_ST,
            )
        assert len(store.get_score_updates(run_id="weekly-1")) == 2
        newest = store.get_score_updates(limit=1)[0]
        assert newest.run_id == "weekly-2"  # newest created_at first
        store.close()


# ── Weekly-runner helper: scores move + audit row persisted ──────────────────────

class _Gen:
    weights = {"ranking": 0.5, "thesis": 0.3, "opportunity": 0.2}


def _cand(asset_id, ticker):
    return ScoredCandidate(asset_id=asset_id, ticker=ticker, ranking_score=0.5,
                           opportunity_score=0.5, thesis_strength=0.5)


class TestWeeklyScoringHelper:
    def test_positive_signal_moves_score_and_records_audit(self, tmp_path):
        store = _store(tmp_path)
        _seed_signal(store, "asset-A", primary_endpoint_met=True, p_value=0.001)
        cands = [_cand("asset-A", "AAA"), _cand("asset-B", "BBB")]
        ctxs = build_score_contexts(store, ["asset-A", "asset-B"], as_of=_TODAY)

        all_scores, n_updates = _scores_with_signal_contexts(
            store, cands, ctxs, _Gen(), run_id="weekly-2026-06-16", as_of=_TODAY,
        )
        base = round(0.5 * 0.5 + 0.3 * 0.5 + 0.2 * 0.5, 4)  # 0.5
        assert all_scores["AAA"] > base       # signal lifted A
        assert all_scores["BBB"] == base      # B had no signal → unchanged
        assert n_updates == 1

        rows = store.get_score_updates(asset_id="asset-A")
        assert len(rows) == 1
        assert rows[0].prior_score == base
        assert rows[0].new_score == all_scores["AAA"]
        assert rows[0].delta > 0
        assert rows[0].contributing_event_ids == ["evt-asset-A"]
        store.close()

    def test_no_contexts_no_updates_scores_are_base(self, tmp_path):
        store = _store(tmp_path)
        cands = [_cand("asset-A", "AAA")]
        all_scores, n_updates = _scores_with_signal_contexts(
            store, cands, {}, _Gen(), run_id="r", as_of=_TODAY,
        )
        assert n_updates == 0
        assert all_scores["AAA"] == 0.5
        assert store.get_score_updates() == []
        store.close()
