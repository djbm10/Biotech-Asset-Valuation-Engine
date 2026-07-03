from __future__ import annotations

import csv
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LABELS_CSV = REPO_ROOT / "research/data/killer_question_ground_truth.csv"
PHASE_TRANSITIONS_CSV = REPO_ROOT / "research/data/phase_transitions.csv"

REQUIRED_COLUMNS = {
    "program_id",
    "decision_date",
    "outcome",
    "decisive_archetype",
    "label_status",
    "decisive_confidence",
    "why_this_archetype_decided",
    "label_source",
    "label_date",
    "pivotal_evidence_event",
    "pivotal_evidence_date",
    "single_question_dominant",
    "competing_archetypes",
}

ALLOWED_ARCHETYPES = {
    "TARGET_VALIDITY",
    "DELIVERY_EXPOSURE",
    "DOSE_ADEQUACY",
    "DIFFERENTIATION",
    "TOLERABILITY_CEILING",
    "NOVEL_OR_UNMODELED_RISK",
}
ALLOWED_LABEL_STATUSES = {"clean", "subjective", "excluded"}
ALLOWED_CONFIDENCE = {"high", "medium", "low"}
ALLOWED_BOOL = {"true", "false"}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_ground_truth_file_exists_with_required_columns() -> None:
    rows = _read_csv(LABELS_CSV)

    assert rows
    assert REQUIRED_COLUMNS.issubset(rows[0])


def test_ground_truth_rows_use_allowed_values() -> None:
    rows = _read_csv(LABELS_CSV)

    for row in rows:
        assert row["decisive_archetype"] in ALLOWED_ARCHETYPES
        assert row["label_status"] in ALLOWED_LABEL_STATUSES
        assert row["decisive_confidence"] in ALLOWED_CONFIDENCE
        assert row["single_question_dominant"] in ALLOWED_BOOL


def test_ground_truth_rows_have_required_provenance() -> None:
    rows = _read_csv(LABELS_CSV)

    for row in rows:
        assert row["why_this_archetype_decided"].strip()
        assert row["label_source"].strip()
        assert row["label_date"].strip()
        assert row["pivotal_evidence_event"].strip()


def test_label_date_is_not_before_decision_date() -> None:
    rows = _read_csv(LABELS_CSV)

    for row in rows:
        decision_date = date.fromisoformat(row["decision_date"])
        label_date = date.fromisoformat(row["label_date"])

        assert label_date >= decision_date


def test_decision_date_precedes_pivotal_evidence_date() -> None:
    rows = _read_csv(LABELS_CSV)

    for row in rows:
        decision_date = date.fromisoformat(row["decision_date"])
        pivotal_date = date.fromisoformat(row["pivotal_evidence_date"])

        assert decision_date < pivotal_date


def test_program_ids_exist_in_phase_transition_dataset() -> None:
    labels = _read_csv(LABELS_CSV)
    phase_rows = _read_csv(PHASE_TRANSITIONS_CSV)
    known_programs = {row["drug"] for row in phase_rows}

    assert {row["program_id"] for row in labels}.issubset(known_programs)


def test_headline_eligibility_is_per_row_not_per_archetype() -> None:
    rows = _read_csv(LABELS_CSV)
    statuses_by_archetype: dict[str, set[str]] = {}

    for row in rows:
        statuses_by_archetype.setdefault(row["decisive_archetype"], set()).add(
            row["label_status"]
        )

    assert any(len(statuses) > 1 for statuses in statuses_by_archetype.values())
    assert any(row["label_status"] == "clean" for row in rows)
    assert any(row["label_status"] == "subjective" for row in rows)
    assert any(row["label_status"] == "excluded" for row in rows)


def test_seed_has_minimum_clean_headline_rows() -> None:
    rows = _read_csv(LABELS_CSV)
    clean_rows = [row for row in rows if row["label_status"] == "clean"]

    assert len(clean_rows) >= 15
    assert all(row["single_question_dominant"] == "true" for row in clean_rows)


def test_competing_archetypes_are_valid_and_exclude_decisive() -> None:
    """Each competing archetype must be a known archetype and must not repeat
    the decisive one (the decisive archetype is opened separately)."""
    rows = _read_csv(LABELS_CSV)

    for row in rows:
        competing = [
            token.strip()
            for token in row["competing_archetypes"].split(",")
            if token.strip()
        ]
        for archetype in competing:
            assert archetype in ALLOWED_ARCHETYPES, (
                f"{row['program_id']}: unknown competing archetype {archetype!r}"
            )
        assert row["decisive_archetype"] not in competing, (
            f"{row['program_id']}: decisive archetype listed in competing_archetypes"
        )
        assert len(competing) == len(set(competing)), (
            f"{row['program_id']}: duplicate competing archetypes"
        )


def test_clean_headline_rows_have_competing_archetypes() -> None:
    """Every clean headline row must present a real ranking field (>=1 competing
    archetype), otherwise M1 degenerates to a single-candidate walkover."""
    rows = _read_csv(LABELS_CSV)
    clean_rows = [row for row in rows if row["label_status"] == "clean"]

    for row in clean_rows:
        competing = [t.strip() for t in row["competing_archetypes"].split(",") if t.strip()]
        assert competing, f"{row['program_id']}: clean row has no competing archetypes"
