"""
Tests for POSOutcomeRecord, load_outcome_records, and build_sponsor_tracks.
"""
from __future__ import annotations

import csv
import io
import tempfile
from pathlib import Path
from textwrap import dedent

import pytest

from bve.empirical.pos_outcome import (
    POSOutcomeRecord,
    SponsorTrackRecord,
    build_sponsor_tracks,
    load_bundled_records,
    load_outcome_records,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_ROW = {
    "drug": "testinib",
    "company": "Acme Pharma",
    "indication": "NSCLC",
    "phase_start": "phase_2",
    "outcome": "approved",
    "year": "2022",
    "moa_precedent": "novel",
    "biomarker_enriched": "true",
    "safety_profile": "clean",
    "competitive_pressure": "low",
    "endpoint_type": "surrogate_validated",
    "notes": "test note",
}


def _make_csv(*rows: dict, extra_rows: list[dict] | None = None) -> Path:
    """Write a minimal outcomes CSV to a temp file and return its path."""
    all_rows = list(rows) + (extra_rows or [])
    fields = list(_VALID_ROW.keys())
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    ) as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in all_rows:
            merged = {**_VALID_ROW, **row}
            writer.writerow(merged)
    return Path(fh.name)


# ---------------------------------------------------------------------------
# A. POSOutcomeRecord validation
# ---------------------------------------------------------------------------

class TestPOSOutcomeRecord:
    def test_valid_record_approved(self):
        rec = POSOutcomeRecord(
            program_id="testinib_2022",
            sponsor="Acme",
            asset_name="testinib",
            indication_raw="NSCLC",
            phase_at_entry="phase_2",
            success=True,
            outcome_raw="approved",
        )
        assert rec.success is True
        assert rec.biomarker_selected is False

    def test_valid_record_failed(self):
        rec = POSOutcomeRecord(
            program_id="failinib_2020",
            sponsor="Acme",
            asset_name="failinib",
            indication_raw="CRC",
            phase_at_entry="phase_3",
            success=False,
            outcome_raw="failed",
        )
        assert rec.success is False

    def test_invalid_phase_raises(self):
        with pytest.raises(ValueError, match="phase_at_entry"):
            POSOutcomeRecord(
                program_id="x",
                sponsor="x",
                asset_name="x",
                indication_raw="x",
                phase_at_entry="phase_5",  # invalid
                success=True,
                outcome_raw="approved",
            )

    def test_invalid_endpoint_type_raises(self):
        with pytest.raises(ValueError, match="endpoint_type"):
            POSOutcomeRecord(
                program_id="x",
                sponsor="x",
                asset_name="x",
                indication_raw="x",
                phase_at_entry="phase_2",
                endpoint_type="imaginary_endpoint",
                success=True,
                outcome_raw="approved",
            )

    def test_invalid_moa_raises(self):
        with pytest.raises(ValueError, match="moa_precedent"):
            POSOutcomeRecord(
                program_id="x",
                sponsor="x",
                asset_name="x",
                indication_raw="x",
                phase_at_entry="phase_2",
                moa_precedent="supervalidated",
                success=True,
                outcome_raw="approved",
            )

    def test_invalid_safety_raises(self):
        with pytest.raises(ValueError, match="safety_profile"):
            POSOutcomeRecord(
                program_id="x",
                sponsor="x",
                asset_name="x",
                indication_raw="x",
                phase_at_entry="phase_3",
                safety_profile="catastrophic",
                success=False,
                outcome_raw="failed",
            )

    def test_invalid_competition_raises(self):
        with pytest.raises(ValueError, match="competitive_pressure"):
            POSOutcomeRecord(
                program_id="x",
                sponsor="x",
                asset_name="x",
                indication_raw="x",
                phase_at_entry="phase_2",
                competitive_pressure="extreme",
                success=True,
                outcome_raw="approved",
            )

    def test_all_valid_phases_accepted(self):
        for phase in ("phase_1", "phase_2", "phase_3", "nda_bla"):
            rec = POSOutcomeRecord(
                program_id=f"drug_{phase}",
                sponsor="S",
                asset_name="drug",
                indication_raw="X",
                phase_at_entry=phase,
                success=True,
                outcome_raw="approved",
            )
            assert rec.phase_at_entry == phase

    def test_optional_fields_default_to_none(self):
        rec = POSOutcomeRecord(
            program_id="x",
            sponsor="S",
            asset_name="d",
            indication_raw="X",
            phase_at_entry="phase_2",
            success=True,
            outcome_raw="approved",
        )
        assert rec.indication_canonical is None
        assert rec.therapeutic_area is None
        assert rec.modality is None
        assert rec.moa_precedent is None
        assert rec.outcome_date is None


# ---------------------------------------------------------------------------
# B. load_outcome_records
# ---------------------------------------------------------------------------

class TestLoadOutcomeRecords:
    def test_loads_approved_row(self):
        path = _make_csv(_VALID_ROW)
        records = load_outcome_records(path)
        assert len(records) == 1
        assert records[0].success is True
        assert records[0].asset_name == "testinib"

    def test_loads_advanced_as_success(self):
        path = _make_csv({**_VALID_ROW, "outcome": "advanced"})
        records = load_outcome_records(path)
        assert records[0].success is True

    def test_loads_failed_as_failure(self):
        path = _make_csv({**_VALID_ROW, "outcome": "failed"})
        records = load_outcome_records(path)
        assert records[0].success is False

    def test_censored_rows_skipped_by_default(self):
        approved_row = {**_VALID_ROW, "drug": "drugA", "outcome": "approved"}
        ongoing_row = {**_VALID_ROW, "drug": "drugB", "outcome": "ongoing"}
        path = _make_csv(approved_row, ongoing_row)
        records = load_outcome_records(path)
        assert len(records) == 1
        assert records[0].asset_name == "drugA"

    def test_censored_rows_raise_when_skip_censored_false(self):
        path = _make_csv({**_VALID_ROW, "outcome": "ongoing"})
        with pytest.raises(ValueError, match="censored"):
            load_outcome_records(path, skip_censored=False)

    def test_invalid_phase_raises_by_default(self):
        path = _make_csv({**_VALID_ROW, "phase_start": "phase_99"})
        with pytest.raises(ValueError):
            load_outcome_records(path)

    def test_invalid_phase_skipped_when_skip_invalid(self):
        approved = {**_VALID_ROW, "drug": "good", "outcome": "approved"}
        bad_phase = {**_VALID_ROW, "drug": "bad", "phase_start": "phase_99"}
        path = _make_csv(approved, bad_phase)
        records = load_outcome_records(path, skip_invalid=True)
        assert len(records) == 1
        assert records[0].asset_name == "good"

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            load_outcome_records("/nonexistent/path.csv")

    def test_biomarker_enriched_true_parsed(self):
        path = _make_csv({**_VALID_ROW, "biomarker_enriched": "true"})
        records = load_outcome_records(path)
        assert records[0].biomarker_selected is True

    def test_biomarker_enriched_false_parsed(self):
        path = _make_csv({**_VALID_ROW, "biomarker_enriched": "false"})
        records = load_outcome_records(path)
        assert records[0].biomarker_selected is False

    def test_moa_precedent_populated(self):
        path = _make_csv({**_VALID_ROW, "moa_precedent": "novel"})
        records = load_outcome_records(path)
        assert records[0].moa_precedent == "novel"

    def test_safety_profile_populated(self):
        path = _make_csv({**_VALID_ROW, "safety_profile": "concerning"})
        records = load_outcome_records(path)
        assert records[0].safety_profile == "concerning"

    def test_endpoint_type_populated(self):
        path = _make_csv({**_VALID_ROW, "endpoint_type": "hard_clinical"})
        records = load_outcome_records(path)
        assert records[0].endpoint_type == "hard_clinical"

    def test_year_stored_as_outcome_date(self):
        path = _make_csv({**_VALID_ROW, "year": "2021"})
        records = load_outcome_records(path)
        assert records[0].outcome_date == "2021"

    def test_notes_stored_as_source_label(self):
        path = _make_csv({**_VALID_ROW, "notes": "A useful note"})
        records = load_outcome_records(path)
        assert records[0].source_label == "A useful note"


# ---------------------------------------------------------------------------
# Bundled dataset
# ---------------------------------------------------------------------------

class TestLoadBundledRecords:
    def test_bundled_records_load(self):
        records = load_bundled_records()
        # Dataset has ~99 rows; ~7 are 'ongoing' so we expect ~80+ usable records
        assert len(records) >= 60
        assert all(isinstance(r, POSOutcomeRecord) for r in records)

    def test_bundled_has_both_successes_and_failures(self):
        records = load_bundled_records()
        assert any(r.success for r in records)
        assert any(not r.success for r in records)

    def test_bundled_phases_valid(self):
        records = load_bundled_records()
        valid = {"phase_1", "phase_2", "phase_3", "nda_bla"}
        assert all(r.phase_at_entry in valid for r in records)


# ---------------------------------------------------------------------------
# C. build_sponsor_tracks
# ---------------------------------------------------------------------------

class TestBuildSponsorTracks:
    def _make_records(self) -> list[POSOutcomeRecord]:
        return [
            POSOutcomeRecord(
                program_id="a1",
                sponsor="Merck",
                asset_name="drugA",
                indication_raw="NSCLC",
                phase_at_entry="phase_2",
                success=True,
                outcome_raw="approved",
            ),
            POSOutcomeRecord(
                program_id="a2",
                sponsor="Merck",
                asset_name="drugB",
                indication_raw="CRC",
                phase_at_entry="phase_3",
                success=False,
                outcome_raw="failed",
            ),
            POSOutcomeRecord(
                program_id="a3",
                sponsor="Merck",
                asset_name="drugC",
                indication_raw="GBM",
                phase_at_entry="phase_2",
                success=True,
                outcome_raw="approved",
            ),
            POSOutcomeRecord(
                program_id="b1",
                sponsor="Novartis",
                asset_name="drugD",
                indication_raw="HR+ BC",
                phase_at_entry="phase_3",
                success=True,
                outcome_raw="approved",
            ),
        ]

    def test_sponsor_track_counts(self):
        records = self._make_records()
        tracks = build_sponsor_tracks(records)
        assert "Merck" in tracks
        merck = tracks["Merck"]
        assert merck.n_trials == 3
        assert merck.n_success == 2
        assert abs(merck.success_rate - 2 / 3) < 0.001

    def test_phase_breakdown(self):
        records = self._make_records()
        tracks = build_sponsor_tracks(records)
        merck = tracks["Merck"]
        assert "phase_2" in merck.phases
        assert merck.phases["phase_2"]["n"] == 2
        assert merck.phases["phase_2"]["n_success"] == 2

    def test_all_sponsors_present(self):
        records = self._make_records()
        tracks = build_sponsor_tracks(records)
        assert "Novartis" in tracks
        assert tracks["Novartis"].n_trials == 1
        assert tracks["Novartis"].n_success == 1

    def test_min_trials_filter(self):
        records = self._make_records()
        # Novartis has only 1 trial
        tracks = build_sponsor_tracks(records, min_trials=2)
        assert "Merck" in tracks
        assert "Novartis" not in tracks

    def test_empty_records(self):
        tracks = build_sponsor_tracks([])
        assert tracks == {}

    def test_bundled_sponsor_tracks(self):
        records = load_bundled_records()
        tracks = build_sponsor_tracks(records)
        assert len(tracks) > 5
        # Well-known sponsors should appear
        sponsors = set(tracks.keys())
        assert any("Merck" in s for s in sponsors)
