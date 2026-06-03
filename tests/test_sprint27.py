"""
Sprint 27 — Historical thesis claims backfiller + resolved_at no-lookahead fix.

Tests for:
1. ThesisTracker.snapshot() resolved_at no-lookahead fix
2. ThesisClaimsBackfiller YAML loading and seeding
3. bve-seed-replay-claims CLI (dry-run + live)
4. Integration: thesis_strength correctly reflected in replay decisions
"""
from __future__ import annotations

import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store(tmp_path: Path):
    from bve.intelligence.knowledge_layer import KnowledgeStore
    db = str(tmp_path / "test_tt.db")
    return KnowledgeStore(db)


def _utc(year, month, day) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


# ===========================================================================
# 1. ThesisTracker.snapshot() — resolved_at no-lookahead fix
# ===========================================================================

class TestSnapshotResolvedAtNoLookahead:
    def test_claim_not_yet_resolved_appears_open(self, tmp_path):
        """
        A claim created 2021-01-01, resolved 2022-06-01 as 'confirmed',
        should appear as 'open' when snapshot taken as of 2021-12-31.
        """
        from bve.intelligence.thesis_tracker import ClaimType, ThesisTracker
        store = _make_store(tmp_path)
        tt = ThesisTracker(store)

        claim = tt.add_claim(
            asset_id="a-test",
            company_id="c-test",
            claim_type=ClaimType.ENDPOINT_MET,
            assertion="Test endpoint met",
            created_at=_utc(2021, 1, 1),
        )
        tt.resolve_claim(
            claim_id=claim.claim_id,
            status="confirmed",
            evidence="trial succeeded",
            resolved_at=_utc(2022, 6, 1),
        )

        # Snapshot as of date BEFORE resolution → should appear open
        snap = tt.snapshot("a-test", as_of_date=date(2021, 12, 31))
        assert snap.n_open == 1
        assert snap.n_confirmed == 0
        assert snap.thesis_strength is None  # no resolved claims
        store.close()

    def test_claim_appears_confirmed_after_resolution(self, tmp_path):
        """Same claim should show as confirmed after resolved_at date."""
        from bve.intelligence.thesis_tracker import ClaimType, ThesisTracker
        store = _make_store(tmp_path)
        tt = ThesisTracker(store)

        claim = tt.add_claim(
            asset_id="a-test",
            company_id="c-test",
            claim_type=ClaimType.ENDPOINT_MET,
            assertion="Test endpoint met",
            created_at=_utc(2021, 1, 1),
        )
        tt.resolve_claim(
            claim_id=claim.claim_id,
            status="confirmed",
            evidence="trial succeeded",
            resolved_at=_utc(2022, 6, 1),
        )

        # Snapshot AFTER resolution → confirmed
        snap = tt.snapshot("a-test", as_of_date=date(2022, 6, 2))
        assert snap.n_confirmed == 1
        assert snap.n_open == 0
        assert snap.thesis_strength == pytest.approx(1.0)
        store.close()

    def test_thesis_strength_none_until_first_resolution(self, tmp_path):
        """With one open claim, thesis_strength should be None (not 0.5)."""
        from bve.intelligence.thesis_tracker import ClaimType, ThesisTracker
        store = _make_store(tmp_path)
        tt = ThesisTracker(store)

        tt.add_claim(
            asset_id="a-test",
            company_id="c-test",
            claim_type=ClaimType.ENDPOINT_MET,
            assertion="Unresolved claim",
            created_at=_utc(2021, 1, 1),
        )
        snap = tt.snapshot("a-test", as_of_date=date(2021, 6, 1))
        assert snap.thesis_strength is None
        store.close()

    def test_refuted_claim_after_resolution_date(self, tmp_path):
        """A refuted claim resolved 2023-01-01 should appear open before that date."""
        from bve.intelligence.thesis_tracker import ClaimType, ThesisTracker
        store = _make_store(tmp_path)
        tt = ThesisTracker(store)

        claim = tt.add_claim(
            asset_id="a-test",
            company_id="c-test",
            claim_type=ClaimType.ENDPOINT_MET,
            assertion="Endpoint will not be met",
            created_at=_utc(2022, 1, 1),
        )
        tt.resolve_claim(
            claim_id=claim.claim_id,
            status="refuted",
            evidence="trial failed",
            resolved_at=_utc(2023, 1, 1),
        )

        snap_before = tt.snapshot("a-test", as_of_date=date(2022, 12, 31))
        assert snap_before.n_open == 1
        assert snap_before.n_refuted == 0

        snap_after = tt.snapshot("a-test", as_of_date=date(2023, 1, 2))
        assert snap_after.n_refuted == 1
        assert snap_after.thesis_strength == pytest.approx(0.0)
        store.close()

    def test_two_claims_partial_resolution(self, tmp_path):
        """
        Two claims: one confirmed (2022-01-01), one still open as of 2022-06-01.
        thesis_strength should be 1.0 (1 confirmed / 1 resolved).
        """
        from bve.intelligence.thesis_tracker import ClaimType, ThesisTracker
        store = _make_store(tmp_path)
        tt = ThesisTracker(store)

        c1 = tt.add_claim("a-test", "c-test", ClaimType.ENDPOINT_MET,
                          "Claim 1", created_at=_utc(2021, 1, 1))
        tt.resolve_claim(c1.claim_id, "confirmed", resolved_at=_utc(2022, 1, 1))

        tt.add_claim("a-test", "c-test", ClaimType.ENDPOINT_MET,
                     "Claim 2", created_at=_utc(2021, 6, 1))
        # Claim 2 resolved 2023 — not yet resolved as of 2022-06-01

        snap = tt.snapshot("a-test", as_of_date=date(2022, 6, 1))
        assert snap.n_confirmed == 1
        assert snap.n_open == 1  # Claim 2 still open
        assert snap.thesis_strength == pytest.approx(1.0)
        store.close()

    def test_no_as_of_returns_all_resolved(self, tmp_path):
        """Without as_of_date, resolved claims always show their final status."""
        from bve.intelligence.thesis_tracker import ClaimType, ThesisTracker
        store = _make_store(tmp_path)
        tt = ThesisTracker(store)

        claim = tt.add_claim("a-test", "c-test", ClaimType.ENDPOINT_MET,
                              "Test claim", created_at=_utc(2021, 1, 1))
        tt.resolve_claim(claim.claim_id, "confirmed", resolved_at=_utc(2025, 1, 1))

        # No as_of_date → always confirmed
        snap = tt.snapshot("a-test")
        assert snap.n_confirmed == 1
        store.close()


# ===========================================================================
# 2. ThesisClaimsBackfiller — YAML loading and seeding
# ===========================================================================

_MINIMAL_YAML = """\
claims:
  - ticker: ALNY
    asset_id: a-alny
    company_id: co-alny
    claim_type: endpoint_met
    assertion: "Test claim for ALNY"
    created_at: "2021-01-04"
    resolved_at: "2022-06-01"
    status: confirmed
    evidence: "Trial succeeded"
  - ticker: FATE
    asset_id: a-fate
    company_id: co-fate
    claim_type: pos_above_threshold
    assertion: "Test claim for FATE"
    created_at: "2021-01-04"
    resolved_at: "2023-12-11"
    status: refuted
    evidence: "Program discontinued"
"""


class TestThesisClaimsBackfillerLoad:
    def test_loads_valid_yaml(self, tmp_path):
        from bve.ops.thesis_claims_backfiller import ThesisClaimsBackfiller
        yaml_file = tmp_path / "claims.yaml"
        yaml_file.write_text(_MINIMAL_YAML)
        db = str(tmp_path / "test.db")
        bf = ThesisClaimsBackfiller(db, yaml_path=yaml_file)
        claims = bf.load()
        assert len(claims) == 2

    def test_rejects_missing_field(self, tmp_path):
        from bve.ops.thesis_claims_backfiller import ThesisClaimsBackfiller
        bad = "claims:\n  - ticker: ALNY\n    asset_id: a-alny\n"
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text(bad)
        db = str(tmp_path / "test.db")
        bf = ThesisClaimsBackfiller(db, yaml_path=yaml_file)
        with pytest.raises(ValueError, match="missing field"):
            bf.load()

    def test_rejects_invalid_status(self, tmp_path):
        from bve.ops.thesis_claims_backfiller import ThesisClaimsBackfiller
        bad_yaml = _MINIMAL_YAML.replace("status: confirmed", "status: wrong")
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text(bad_yaml)
        db = str(tmp_path / "test.db")
        bf = ThesisClaimsBackfiller(db, yaml_path=yaml_file)
        with pytest.raises(ValueError, match="invalid status"):
            bf.load()

    def test_default_yaml_path_exists(self):
        from bve.ops.thesis_claims_backfiller import _DEFAULT_YAML
        assert _DEFAULT_YAML.exists(), f"Default YAML not found at {_DEFAULT_YAML}"


class TestThesisClaimsBackfillerSeed:
    def test_seed_inserts_claims(self, tmp_path):
        from bve.ops.thesis_claims_backfiller import ThesisClaimsBackfiller
        from bve.intelligence.knowledge_layer import KnowledgeStore
        from bve.intelligence.thesis_tracker import ThesisTracker

        yaml_file = tmp_path / "claims.yaml"
        yaml_file.write_text(_MINIMAL_YAML)
        db = str(tmp_path / "test.db")

        bf = ThesisClaimsBackfiller(db, yaml_path=yaml_file)
        result = bf.seed()

        assert result["inserted"] == 2
        assert result["skipped"] == 0

        # Verify claims are in the DB with correct timestamps
        store = KnowledgeStore(db)
        tt = ThesisTracker(store)

        # ALNY: before resolved_at → open
        snap_before = tt.snapshot("a-alny", as_of_date=date(2022, 1, 1))
        assert snap_before.n_open == 1
        assert snap_before.n_confirmed == 0

        # ALNY: after resolved_at → confirmed
        snap_after = tt.snapshot("a-alny", as_of_date=date(2022, 7, 1))
        assert snap_after.n_confirmed == 1
        assert snap_after.thesis_strength == pytest.approx(1.0)

        # FATE: after resolved_at → refuted
        snap_fate = tt.snapshot("a-fate", as_of_date=date(2024, 1, 1))
        assert snap_fate.n_refuted == 1
        assert snap_fate.thesis_strength == pytest.approx(0.0)
        store.close()

    def test_seed_is_idempotent(self, tmp_path):
        from bve.ops.thesis_claims_backfiller import ThesisClaimsBackfiller

        yaml_file = tmp_path / "claims.yaml"
        yaml_file.write_text(_MINIMAL_YAML)
        db = str(tmp_path / "test.db")

        bf = ThesisClaimsBackfiller(db, yaml_path=yaml_file)
        r1 = bf.seed()
        r2 = bf.seed()

        assert r1["inserted"] == 2
        assert r2["inserted"] == 0
        assert r2["skipped"] == 2

    def test_dry_run_makes_no_db_changes(self, tmp_path):
        from bve.ops.thesis_claims_backfiller import ThesisClaimsBackfiller
        from bve.intelligence.knowledge_layer import KnowledgeStore

        yaml_file = tmp_path / "claims.yaml"
        yaml_file.write_text(_MINIMAL_YAML)
        db = str(tmp_path / "test.db")

        # Pre-create schema (ThesisTracker creates the table on init)
        from bve.intelligence.thesis_tracker import ThesisTracker
        store = KnowledgeStore(db)
        ThesisTracker(store)  # initialises thesis_claims table

        bf = ThesisClaimsBackfiller(db, yaml_path=yaml_file, dry_run=True)
        result = bf.seed()
        assert result["inserted"] == 0

        # DB should have no claims after dry-run
        count = store._conn.execute(
            "SELECT COUNT(*) FROM thesis_claims"
        ).fetchone()[0]
        store.close()
        assert count == 0


# ===========================================================================
# 3. Default YAML: real 28-claim file loads without error
# ===========================================================================

class TestDefaultYamlIntegrity:
    def test_default_yaml_loads_89_claims(self):
        from bve.ops.thesis_claims_backfiller import ThesisClaimsBackfiller, _DEFAULT_YAML
        import sqlite3, tempfile
        # Seed into a temp DB just to validate full load+seed path
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "temp.db")
            bf = ThesisClaimsBackfiller(db, yaml_path=_DEFAULT_YAML)
            claims = bf.load()
            assert len(claims) >= 89  # expanded: 125 after Wave 3 additions

    def test_all_resolved_at_after_created_at(self):
        from bve.ops.thesis_claims_backfiller import ThesisClaimsBackfiller, _DEFAULT_YAML
        with tempfile.TemporaryDirectory() as td:
            db = str(Path(td) / "temp.db")
            bf = ThesisClaimsBackfiller(db, yaml_path=_DEFAULT_YAML)
            claims = bf.load()
            for c in claims:
                assert c["created_at"] <= c["resolved_at"], (
                    f"{c['ticker']}: created_at={c['created_at']} > "
                    f"resolved_at={c['resolved_at']}"
                )

    def test_default_yaml_seeds_successfully(self, tmp_path):
        from bve.ops.thesis_claims_backfiller import ThesisClaimsBackfiller, _DEFAULT_YAML
        db = str(tmp_path / "temp.db")
        bf = ThesisClaimsBackfiller(db, yaml_path=_DEFAULT_YAML)
        result = bf.seed()
        assert result["inserted"] >= 89  # expanded: 125 after Wave 3 additions
        assert result["skipped"] == 0


# ===========================================================================
# 4. CLI smoke tests
# ===========================================================================

class TestSeedReplayClaimsCLI:
    def test_dry_run_flag(self, tmp_path, capsys):
        from bve.cli.seed_replay_claims import main
        yaml_file = tmp_path / "claims.yaml"
        yaml_file.write_text(_MINIMAL_YAML)
        db = str(tmp_path / "test.db")

        with patch("sys.argv", ["bve-seed-replay-claims",
                                 "--dry-run", "--claims", str(yaml_file),
                                 "--db", db]):
            main()
        out = capsys.readouterr().out
        assert "dry-run" in out
        assert "2" in out  # 2 claims in minimal YAML

    def test_live_seed(self, tmp_path, capsys):
        from bve.cli.seed_replay_claims import main
        yaml_file = tmp_path / "claims.yaml"
        yaml_file.write_text(_MINIMAL_YAML)
        db = str(tmp_path / "test.db")

        with patch("sys.argv", ["bve-seed-replay-claims",
                                 "--claims", str(yaml_file), "--db", db]):
            main()
        out = capsys.readouterr().out
        assert "2 inserted" in out
