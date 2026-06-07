"""
test_golden_source_deals — exact assertions for 3 verified seed deals.

These tests are the "golden source" contract: if any of these assertions
fail, someone has modified the seed data without updating the authoritative
deal record.  Do NOT relax these assertions without a verified primary source.

Also includes a deliberate leakage fixture test that proves the backtest
refuses to run when a post-snapshot source date is present.
"""
from __future__ import annotations

import pytest
from datetime import date
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEED_CSV = (
    Path(__file__).parent.parent.parent
    / "research/backtests/vrtx_regn_2010/seeds/deal_seed_vrtx_regn.csv"
)


def _load_seed() -> list[dict]:
    import csv
    if not SEED_CSV.exists():
        pytest.skip(f"Seed CSV not found: {SEED_CSV}")
    with SEED_CSV.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _verified(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r.get("verified", "").upper() == "TRUE"]


def _get_deal(rows: list[dict], acquirer: str, target: str) -> dict:
    matches = [
        r for r in rows
        if r["acquirer_ticker"] == acquirer and r["target_ticker"] == target
    ]
    assert len(matches) == 1, (
        f"Expected exactly 1 deal for ({acquirer}, {target}), got {len(matches)}"
    )
    return matches[0]


# ---------------------------------------------------------------------------
# Golden source assertions — VRTX / Semma Therapeutics
# ---------------------------------------------------------------------------

class TestGoldenSourceVRTXSemma:
    """
    Authoritative record: Vertex acquires Semma Therapeutics, announced 2019-09-03.
    Source: https://investors.vrtx.com/news-releases/news-release-details/
            vertex-pharmaceuticals-acquire-semma-therapeutics
    Deal value: $950M cash (all-cash).
    Lead asset: stem-cell-derived islet therapy (preclinical → VX-880).
    Indication: Type 1 diabetes.
    """

    def test_acquirer_is_vrtx(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "SEMMA")
        assert deal["acquirer_ticker"] == "VRTX"

    def test_target_ticker_is_semma(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "SEMMA")
        assert deal["target_ticker"] == "SEMMA"

    def test_announced_date_is_2019_09_03(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "SEMMA")
        assert deal["announced_date"] == "2019-09-03"

    def test_deal_value_is_950_million(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "SEMMA")
        assert float(deal["deal_value_usd_millions"]) == pytest.approx(950.0)

    def test_deal_type_is_full_acquisition(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "SEMMA")
        assert deal["deal_type"] == "full_acquisition"

    def test_therapeutic_area_is_diabetes_endocrine(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "SEMMA")
        assert deal["therapeutic_area"] == "diabetes_endocrine"

    def test_verification_source_is_vertex_press_release(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "SEMMA")
        assert deal["verification_source"] == "vertex_press_release"

    def test_verification_url_contains_vrtx_domain(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "SEMMA")
        assert "vrtx.com" in deal["verification_url"]

    def test_verified_flag_is_true(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "SEMMA")
        assert deal["verified"].upper() == "TRUE"


# ---------------------------------------------------------------------------
# Golden source assertions — VRTX / Alpine Immune Sciences
# ---------------------------------------------------------------------------

class TestGoldenSourceVRTXAlpine:
    """
    Authoritative record: Vertex acquires Alpine Immune Sciences, announced 2024-04-10.
    Source: https://investors.vrtx.com/news-releases/news-release-details/
            vertex-pharmaceuticals-acquire-alpine-immune-sciences
    Deal value: ~$4.9B cash (all-cash).
    Lead asset: povetacicept (BAFF/APRIL dual blocker), Phase 2.
    Indication: IgA nephropathy.
    """

    def test_announced_date_is_2024_04_10(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "ALPN")
        assert deal["announced_date"] == "2024-04-10"

    def test_deal_value_is_4900_million(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "ALPN")
        assert float(deal["deal_value_usd_millions"]) == pytest.approx(4900.0)

    def test_deal_type_is_full_acquisition(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "ALPN")
        assert deal["deal_type"] == "full_acquisition"

    def test_lead_asset_contains_povetacicept(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "ALPN")
        assert "povetacicept" in deal["lead_asset"].lower()

    def test_lead_asset_stage_at_deal_is_phase2(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "ALPN")
        assert deal["lead_asset_stage_at_deal"] == "phase2"

    def test_therapeutic_area_contains_immunology(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "ALPN")
        assert "immunology" in deal["therapeutic_area"]

    def test_verification_url_contains_vrtx_domain(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "ALPN")
        assert "vrtx.com" in deal["verification_url"]


# ---------------------------------------------------------------------------
# Golden source assertions — REGN / Decibel Therapeutics
# ---------------------------------------------------------------------------

class TestGoldenSourceREGNDecibel:
    """
    Authoritative record: Regeneron acquires Decibel Therapeutics, announced 2023-08-09.
    Source: https://investor.regeneron.com/news-releases/news-release-details/
            regeneron-acquire-decibel-therapeutics
    Deal value: ~$109M upfront + up to $213M CVR.
    Lead asset: DB-OTO (AAV gene therapy), Phase 1/2.
    Indication: Otoferlin-related hearing loss.
    """

    def test_announced_date_is_2023_08_09(self):
        rows = _load_seed()
        deal = _get_deal(rows, "REGN", "DBTX")
        assert deal["announced_date"] == "2023-08-09"

    def test_upfront_value_is_109_million(self):
        rows = _load_seed()
        deal = _get_deal(rows, "REGN", "DBTX")
        assert float(deal["upfront_usd_millions"]) == pytest.approx(109.0)

    def test_cvr_max_is_213_million(self):
        rows = _load_seed()
        deal = _get_deal(rows, "REGN", "DBTX")
        assert float(deal["cvr_max_usd_millions"]) == pytest.approx(213.0)

    def test_deal_type_is_full_acquisition(self):
        rows = _load_seed()
        deal = _get_deal(rows, "REGN", "DBTX")
        assert deal["deal_type"] == "full_acquisition"

    def test_lead_asset_is_db_oto(self):
        rows = _load_seed()
        deal = _get_deal(rows, "REGN", "DBTX")
        assert "db-oto" in deal["lead_asset"].lower()

    def test_lead_asset_modality_is_aav_gene_therapy(self):
        rows = _load_seed()
        deal = _get_deal(rows, "REGN", "DBTX")
        assert deal["lead_asset_modality"] == "aav_gene_therapy"

    def test_therapeutic_area_contains_rare_disease(self):
        rows = _load_seed()
        deal = _get_deal(rows, "REGN", "DBTX")
        assert "rare_disease" in deal["therapeutic_area"]

    def test_verification_url_contains_regeneron_domain(self):
        rows = _load_seed()
        deal = _get_deal(rows, "REGN", "DBTX")
        assert "regeneron.com" in deal["verification_url"]


# ---------------------------------------------------------------------------
# Golden source assertions — VRTX / Exonics Therapeutics
# ---------------------------------------------------------------------------

class TestGoldenSourceVRTXExonics:
    """
    Authoritative record: Vertex acquires Exonics Therapeutics, announced 2019-06-06.
    Source: https://news.vrtx.com/news-releases/news-release-details/
            vertex-expands-new-disease-areas-and-enhances-gene-editing
    Deal value: $245M upfront + up to ~$1B including milestones.
    Lead asset: DMD/DM1 gene editing / exon-skipping platform (preclinical).
    Indication: Duchenne muscular dystrophy.
    """

    def test_announced_date_is_2019_06_06(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "EXON")
        assert deal["announced_date"] == "2019-06-06"

    def test_upfront_value_is_245_million(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "EXON")
        assert float(deal["upfront_usd_millions"]) == pytest.approx(245.0)

    def test_cvr_max_is_1000_million(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "EXON")
        assert float(deal["cvr_max_usd_millions"]) == pytest.approx(1000.0)

    def test_deal_type_is_full_acquisition(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "EXON")
        assert deal["deal_type"] == "full_acquisition"

    def test_therapeutic_area_contains_neuromuscular(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "EXON")
        assert "neuromuscular" in deal["therapeutic_area"]

    def test_modality_is_gene_editing(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "EXON")
        assert deal["lead_asset_modality"] == "gene_editing"

    def test_verification_source_is_vertex_press_release(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "EXON")
        assert deal["verification_source"] == "vertex_press_release"

    def test_verification_url_contains_vrtx_domain(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "EXON")
        assert "vrtx.com" in deal["verification_url"]

    def test_label_set_is_primary_full_company_acquisition(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "EXON")
        assert deal["label_set"] == "primary_full_company_acquisition"


# ---------------------------------------------------------------------------
# Golden source assertions — VRTX / ViaCyte
# ---------------------------------------------------------------------------

class TestGoldenSourceVRTXViaCyte:
    """
    Authoritative record: Vertex acquires ViaCyte, announced 2022-07-11.
    Source: https://news.vrtx.com/news-releases/news-release-details/
            vertex-acquire-viacyte-goal-accelerating-its-potentially
    Deal value: $320M all-cash.
    Lead asset: PEC-01 / PEC-Direct / PEC-Encap (stem-cell pancreatic progenitors).
    Indication: Type 1 diabetes.
    """

    def test_announced_date_is_2022_07_11(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "VCYT")
        assert deal["announced_date"] == "2022-07-11"

    def test_deal_value_is_320_million(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "VCYT")
        assert float(deal["deal_value_usd_millions"]) == pytest.approx(320.0)

    def test_deal_type_is_full_acquisition(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "VCYT")
        assert deal["deal_type"] == "full_acquisition"

    def test_therapeutic_area_is_diabetes_endocrine(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "VCYT")
        assert deal["therapeutic_area"] == "diabetes_endocrine"

    def test_modality_is_cell_therapy(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "VCYT")
        assert deal["lead_asset_modality"] == "cell_therapy"

    def test_verification_source_is_vertex_press_release(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "VCYT")
        assert deal["verification_source"] == "vertex_press_release"

    def test_verification_url_contains_vrtx_domain(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "VCYT")
        assert "vrtx.com" in deal["verification_url"]

    def test_label_set_is_primary_full_company_acquisition(self):
        rows = _load_seed()
        deal = _get_deal(rows, "VRTX", "VCYT")
        assert deal["label_set"] == "primary_full_company_acquisition"


# ---------------------------------------------------------------------------
# Seed invariants
# ---------------------------------------------------------------------------

class TestSeedInvariants:
    """
    Invariants that must hold for the entire seed file regardless of specific deals.
    """

    def test_exactly_five_verified_deals(self):
        rows = _load_seed()
        assert len(_verified(rows)) == 5, (
            f"Expected 5 verified deals, got {len(_verified(rows))}.  "
            "Block 13 promoted EXON + VCYT to verified=TRUE.  "
            "Add unverified deals with verified=FALSE, not verified=TRUE."
        )

    def test_verified_deals_are_five_expected(self):
        rows = _load_seed()
        verified = {(r["acquirer_ticker"], r["target_ticker"]) for r in _verified(rows)}
        expected = {
            ("VRTX", "SEMMA"),
            ("VRTX", "ALPN"),
            ("VRTX", "VCYT"),
            ("VRTX", "EXON"),
            ("REGN", "DBTX"),
        }
        assert verified == expected

    def test_unverified_deals_have_documented_source(self):
        # Block 12B promoted some deals to secondary_references_only / reuters_secondary.
        # All unverified sources must be one of these allowlisted values (not empty).
        _VALID_UNVERIFIED = {
            "research_gap",
            "secondary_references_only",
            "reuters_secondary",
            "partial_secondary",
        }
        rows = _load_seed()
        for r in rows:
            if r.get("verified", "").upper() != "TRUE":
                src = r.get("verification_source", "").strip()
                assert any(v in src for v in _VALID_UNVERIFIED), (
                    f"Unverified deal {r['acquirer_ticker']}/{r['target_ticker']} "
                    f"has unrecognised verification_source '{src}'; "
                    f"expected one of {_VALID_UNVERIFIED}"
                )

    def test_all_verified_deals_have_https_url(self):
        rows = _load_seed()
        for r in _verified(rows):
            assert r.get("verification_url", "").startswith("https://"), (
                f"Verified deal {r['acquirer_ticker']}/{r['target_ticker']} "
                "must have an https verification_url"
            )

    def test_no_verified_deal_has_null_deal_value(self):
        rows = _load_seed()
        for r in _verified(rows):
            val = r.get("deal_value_usd_millions", "").strip()
            assert val != "" and val != "null", (
                f"Verified deal {r['acquirer_ticker']}/{r['target_ticker']} "
                "must have a numeric deal_value_usd_millions"
            )


# ---------------------------------------------------------------------------
# Deliberate leakage fixture — proves the backtest refuses to run
# ---------------------------------------------------------------------------

class TestDeliberateLeakageRefusal:
    """
    Proves that the LeakageGuard hard-blocks the backtest runner when any
    feature row has source_published_date AFTER snapshot_date.

    This test is intentionally injecting a bad row and asserting that
    BacktestRunner.run() raises LeakageViolationError.
    """

    def _make_clean_row(self) -> dict:
        return {
            "deal_id": "test_deal",
            "acquirer_ticker": "VRTX",
            "target_ticker": "ALPN",
            "snapshot_date": "2024-01-01",
            "days_before": "90",
            "is_actual_target": "true",
            "source_url": "https://example.com/source",
            "source_published_date": "2023-12-01",   # before snapshot — clean
            "data_as_of_date": "2023-12-01",
            "extraction_method": "manual",
            "confidence": "0.9",
            "asset_quality": "0.7",
            "acquirer_appetite": "0.6",
            "ta_overlap": "0.8",
            "size_fit": "0.5",
            "acquirer_urgency": "0.4",
            "integration_capacity": "0.5",
            "provenance_complete": "true",
        }

    def _write_feature_csv(self, rows: list[dict], path: "Path") -> None:
        import csv
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    def test_clean_feature_store_passes_leakage_guard(self, tmp_path: Path):
        """A clean feature store must not raise LeakageViolationError."""
        from bve.backtest_research.leakage_guard import LeakageGuard

        clean_row = self._make_clean_row()
        guard = LeakageGuard()
        audit = guard.audit_dataframe([clean_row], snapshot_date_col="snapshot_date")
        assert not audit.has_violations, (
            f"Clean row should pass leakage guard but got violations: {audit.violations}"
        )

    def test_post_snapshot_source_date_causes_violation(self):
        """A row with source_published_date > snapshot_date must be flagged."""
        from bve.backtest_research.leakage_guard import LeakageGuard

        bad_row = self._make_clean_row()
        # Inject a post-snapshot source date — this simulates lookahead bias
        bad_row["source_published_date"] = "2024-03-15"   # AFTER snapshot 2024-01-01

        guard = LeakageGuard()
        audit = guard.audit_dataframe([bad_row], snapshot_date_col="snapshot_date")
        assert audit.has_violations, (
            "Expected LeakageGuard to flag row with source_published_date > snapshot_date"
        )

    def test_post_snapshot_data_as_of_date_causes_violation(self):
        """A row with data_as_of_date > snapshot_date must be flagged."""
        from bve.backtest_research.leakage_guard import LeakageGuard

        bad_row = self._make_clean_row()
        bad_row["data_as_of_date"] = "2024-06-01"   # AFTER snapshot 2024-01-01

        guard = LeakageGuard()
        audit = guard.audit_dataframe([bad_row], snapshot_date_col="snapshot_date")
        assert audit.has_violations, (
            "Expected LeakageGuard to flag row with data_as_of_date > snapshot_date"
        )

    def test_runner_refuses_on_leakage_violation(self, tmp_path: Path):
        """BacktestRunner.run() must raise LeakageViolationError on any violation."""
        import csv
        from bve.backtest_research.vrtx_regn_backtest_runner import BacktestRunner
        from bve.backtest_research.leakage_guard import LeakageViolationError

        # Build a feature store with a deliberately leaky row
        bad_row = self._make_clean_row()
        bad_row["source_published_date"] = "2024-06-15"  # post-snapshot leakage

        feature_store_path = tmp_path / "vrtx_regn_feature_store.csv"
        self._write_feature_csv([bad_row], feature_store_path)

        runner = BacktestRunner(score_mode="approved_only")
        with pytest.raises(LeakageViolationError):
            runner.run(
                feature_store_path=feature_store_path,
                output_dir=tmp_path / "outputs",
            )

    def test_label_column_name_causes_violation(self):
        """A feature column named 'deal_value' must be rejected by the guard."""
        from bve.backtest_research.leakage_guard import LeakageGuard

        bad_row = self._make_clean_row()
        bad_row["deal_value_usd_millions"] = "4900.0"  # label field in feature row

        guard = LeakageGuard()
        violations = guard.check_column_names(list(bad_row.keys()))
        # check_column_names returns a list of Violation objects
        assert len(violations) > 0, (
            "Expected LeakageGuard to reject column 'deal_value_usd_millions' "
            "as a label-contaminating column name"
        )
