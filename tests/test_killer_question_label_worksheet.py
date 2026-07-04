from __future__ import annotations

import csv
from pathlib import Path

from bve.analysis.killer_question_backtest import load_ground_truth_labels
from bve.analysis.killer_question_label_worksheet import (
    GROUND_TRUTH_COLUMNS,
    SEED_STATUS,
    build_worksheet_rows,
    propose_archetypes,
    write_worksheet,
)


def _pool_row(**overrides: str) -> dict[str, str]:
    base = {
        "drug": "testdrug",
        "company": "TestCo",
        "indication": "NSCLC",
        "phase_start": "phase_3",
        "outcome": "failed",
        "year": "2020",
        "moa_precedent": "partial",
        "biomarker_enriched": "true",
        "safety_profile": "minor",
        "competitive_pressure": "moderate",
        "endpoint_type": "hard_clinical",
        "notes": "",
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# Heuristic mapping
# --------------------------------------------------------------------------

def test_serious_safety_maps_to_tolerability() -> None:
    proposal = propose_archetypes(_pool_row(safety_profile="serious", competitive_pressure="low"))
    assert proposal.decisive == "TOLERABILITY_CEILING"


def test_high_competition_maps_to_differentiation() -> None:
    proposal = propose_archetypes(
        _pool_row(safety_profile="clean", competitive_pressure="high", moa_precedent="validated")
    )
    assert proposal.decisive == "DIFFERENTIATION"


def test_novel_unselected_maps_to_target_validity() -> None:
    proposal = propose_archetypes(
        _pool_row(
            moa_precedent="novel",
            biomarker_enriched="false",
            safety_profile="minor",
            competitive_pressure="low",
        )
    )
    assert proposal.decisive == "TARGET_VALIDITY"


def test_note_keyword_can_surface_dose_adequacy() -> None:
    proposal = propose_archetypes(
        _pool_row(notes="thrombocytopenia limits dosing; no OS benefit", safety_profile="minor")
    )
    assert "DOSE_ADEQUACY" in {proposal.decisive, *proposal.competing}


def test_conflicting_strong_signals_are_non_dominant() -> None:
    """Serious safety AND high competition should not read as a single dominant
    question — exactly the M3 case the corpus needs."""
    proposal = propose_archetypes(_pool_row(safety_profile="serious", competitive_pressure="high"))
    assert not proposal.single_dominant
    assert proposal.competing  # the runner-up is recorded


def test_no_signals_defaults_low_confidence() -> None:
    proposal = propose_archetypes(
        _pool_row(
            moa_precedent="validated",
            biomarker_enriched="true",
            safety_profile="clean",
            competitive_pressure="low",
            endpoint_type="hard_clinical",
        )
    )
    assert proposal.confidence == "low"


# --------------------------------------------------------------------------
# Worksheet safety invariants
# --------------------------------------------------------------------------

def test_every_seed_row_is_review_status_and_never_clean() -> None:
    rows = build_worksheet_rows()
    assert rows  # the pool yields failures to seed
    assert all(r["label_status"] == SEED_STATUS for r in rows)
    assert all(r["label_status"] != "clean" for r in rows)


def test_seed_rows_exclude_already_labeled_programs() -> None:
    labeled = {label.program_id.lower() for label in load_ground_truth_labels()}
    rows = build_worksheet_rows()
    assert not (labeled & {r["program_id"].lower() for r in rows})


def test_written_worksheet_cannot_load_as_ground_truth(tmp_path: Path) -> None:
    """A seed worksheet must not parse as ground truth (seed_review is not a
    valid label_status), so it can never pollute the M1 headline by accident."""
    rows = build_worksheet_rows()
    out = write_worksheet(rows, tmp_path / "worksheet.csv")

    # Ground-truth columns are present and ordered for easy promotion.
    with out.open(newline="", encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    assert header[: len(GROUND_TRUTH_COLUMNS)] == list(GROUND_TRUTH_COLUMNS)

    # Loading it as ground truth yields only non-clean rows (nothing headline-eligible).
    labels = load_ground_truth_labels(out)
    assert labels
    assert not any(label.headline_eligible for label in labels)
