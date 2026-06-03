"""
POSOutcomeRecord — data model and CSV loader for real clinical trial outcomes.

CSV schema (research/data/oncology_phase_transitions.csv):
    drug, company, indication, phase_start, outcome, year,
    moa_precedent, biomarker_enriched, safety_profile,
    competitive_pressure, endpoint_type, notes

Success definition: outcome in {"advanced", "approved"}.
Ongoing records are censored and excluded from base-rate calculations.
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, model_validator

logger = logging.getLogger(__name__)

# Outcomes that map to success=True
_SUCCESS_OUTCOMES = frozenset({"advanced", "approved"})
# Outcomes that map to success=False
_FAILURE_OUTCOMES = frozenset({"failed"})
# Outcomes that are censored (excluded from POS calculations)
_CENSORED_OUTCOMES = frozenset({"ongoing"})

# Valid phase keys
_VALID_PHASES = frozenset({"phase_1", "phase_2", "phase_3", "nda_bla"})

# Valid categorical field values
_VALID_MOA = frozenset({"validated", "partial", "novel"})
_VALID_SAFETY = frozenset({"clean", "minor", "concerning", "serious"})
_VALID_COMPETITION = frozenset({"low", "moderate", "high"})
_VALID_ENDPOINT = frozenset({
    "hard_clinical", "surrogate_validated", "surrogate_novel", "biomarker_only"
})


class POSOutcomeRecord(BaseModel):
    """
    One phase-transition outcome for a clinical program.

    Fields map directly to the CSV schema; optional fields are None when
    the column is missing or blank in the source file.
    """

    # Identity
    program_id: str = Field(description="Unique slug: {drug}_{year}")
    sponsor: str = Field(description="Company / sponsor name")
    asset_name: str = Field(description="Drug / asset name")

    # Indication context
    indication_raw: str = Field(description="Raw indication string from source")
    indication_canonical: Optional[str] = Field(
        default=None,
        description="Normalized canonical indication (populated post-load when normalizer available)"
    )
    therapeutic_area: Optional[str] = Field(
        default=None,
        description="Therapeutic area string (e.g. 'oncology'); None when not provided"
    )
    modality: Optional[str] = Field(
        default=None,
        description="Drug modality (e.g. 'small_molecule', 'antibody'); None when not provided"
    )

    # Trial characteristics
    phase_at_entry: str = Field(
        description="Phase being evaluated (phase_1 / phase_2 / phase_3 / nda_bla)"
    )
    endpoint_type: Optional[str] = Field(
        default=None,
        description="Primary endpoint type (hard_clinical / surrogate_validated / surrogate_novel / biomarker_only)"
    )
    biomarker_selected: bool = Field(
        default=False,
        description="Trial restricted to a biomarker-selected population"
    )
    enrollment: Optional[int] = Field(
        default=None, description="Total planned enrollment (when available)"
    )
    randomization: Optional[str] = Field(
        default=None, description="Randomization type (e.g. 'randomized', 'single_arm')"
    )
    blinding: Optional[str] = Field(
        default=None, description="Blinding (e.g. 'double_blind', 'open_label')"
    )
    comparator_type: Optional[str] = Field(
        default=None, description="Comparator (e.g. 'placebo', 'active', 'soc')"
    )

    # Heuristic adjuster fields (match pos_model.py enumerations)
    moa_precedent: Optional[str] = Field(
        default=None,
        description="MoA precedent: validated / partial / novel"
    )
    safety_profile: Optional[str] = Field(
        default=None,
        description="Safety profile: clean / minor / concerning / serious"
    )
    competitive_pressure: Optional[str] = Field(
        default=None,
        description="Competitive pressure: low / moderate / high"
    )

    # Outcome
    success: bool = Field(description="True = advanced or approved; False = failed")
    outcome_raw: str = Field(description="Raw outcome string from source")
    outcome_date: Optional[str] = Field(
        default=None,
        description="Year or ISO date of outcome determination"
    )

    # Provenance
    source_type: str = Field(default="csv", description="Source type identifier")
    source_id: Optional[str] = Field(default=None, description="Source file or database ID")
    source_label: Optional[str] = Field(
        default=None, description="Human-readable source label / notes"
    )

    @model_validator(mode="after")
    def _validate_fields(self) -> "POSOutcomeRecord":
        if self.phase_at_entry not in _VALID_PHASES:
            raise ValueError(
                f"phase_at_entry={self.phase_at_entry!r} not in {sorted(_VALID_PHASES)}"
            )
        if self.endpoint_type is not None and self.endpoint_type not in _VALID_ENDPOINT:
            raise ValueError(
                f"endpoint_type={self.endpoint_type!r} not in {sorted(_VALID_ENDPOINT)}"
            )
        if self.moa_precedent is not None and self.moa_precedent not in _VALID_MOA:
            raise ValueError(
                f"moa_precedent={self.moa_precedent!r} not in {sorted(_VALID_MOA)}"
            )
        if self.safety_profile is not None and self.safety_profile not in _VALID_SAFETY:
            raise ValueError(
                f"safety_profile={self.safety_profile!r} not in {sorted(_VALID_SAFETY)}"
            )
        if self.competitive_pressure is not None and self.competitive_pressure not in _VALID_COMPETITION:
            raise ValueError(
                f"competitive_pressure={self.competitive_pressure!r} not in {sorted(_VALID_COMPETITION)}"
            )
        return self


def _parse_row(row: dict, source_id: Optional[str] = None) -> Optional[POSOutcomeRecord]:
    """
    Parse one CSV row into a POSOutcomeRecord.

    Returns None for censored (ongoing) rows; raises ValueError for malformed rows.
    """
    drug = row.get("drug", "").strip()
    company = row.get("company", "").strip()
    indication = row.get("indication", "").strip()
    phase_start = row.get("phase_start", "").strip().lower()
    outcome_raw = row.get("outcome", "").strip().lower()
    year = row.get("year", "").strip()
    moa = row.get("moa_precedent", "").strip().lower()
    biomarker_raw = row.get("biomarker_enriched", "false").strip().lower()
    safety = row.get("safety_profile", "").strip().lower()
    competition = row.get("competitive_pressure", "").strip().lower()
    endpoint = row.get("endpoint_type", "").strip().lower()
    notes = row.get("notes", "").strip()

    if not drug or not company:
        raise ValueError("Missing required fields: drug, company")

    if outcome_raw in _CENSORED_OUTCOMES:
        return None  # censored — caller decides whether to skip or log

    if outcome_raw in _SUCCESS_OUTCOMES:
        success = True
    elif outcome_raw in _FAILURE_OUTCOMES:
        success = False
    else:
        raise ValueError(f"Unknown outcome {outcome_raw!r} for {drug}")

    if phase_start not in _VALID_PHASES:
        raise ValueError(f"Unknown phase {phase_start!r} for {drug}")

    program_id = f"{drug.lower().replace(' ', '_')}_{year}" if year else drug.lower()

    return POSOutcomeRecord(
        program_id=program_id,
        sponsor=company,
        asset_name=drug,
        indication_raw=indication,
        phase_at_entry=phase_start,
        endpoint_type=endpoint if endpoint in _VALID_ENDPOINT else None,
        biomarker_selected=biomarker_raw == "true",
        moa_precedent=moa if moa in _VALID_MOA else None,
        safety_profile=safety if safety in _VALID_SAFETY else None,
        competitive_pressure=competition if competition in _VALID_COMPETITION else None,
        success=success,
        outcome_raw=outcome_raw,
        outcome_date=year or None,
        source_type="csv",
        source_id=source_id,
        source_label=notes or None,
    )


def load_outcome_records(
    csv_path: str | Path,
    skip_censored: bool = True,
    skip_invalid: bool = False,
) -> list[POSOutcomeRecord]:
    """
    Load and validate outcome records from a CSV file.

    Parameters
    ----------
    csv_path:
        Path to the outcomes CSV.
    skip_censored:
        When True (default), silently drop censored (ongoing) rows.
        When False, raise ValueError on censored rows.
    skip_invalid:
        When True, log and skip rows that fail validation.
        When False (default), re-raise validation errors.

    Returns
    -------
    List of validated POSOutcomeRecord objects.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"Outcomes CSV not found: {path}")

    records: list[POSOutcomeRecord] = []
    censored_count = 0
    invalid_count = 0

    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for lineno, row in enumerate(reader, start=2):  # 1-indexed; row 1 = header
            try:
                record = _parse_row(row, source_id=str(path))
            except ValueError as exc:
                drug = row.get("drug", "?")
                outcome = row.get("outcome", "?")
                if skip_invalid:
                    logger.warning("Row %d (%s / %s): %s — skipped", lineno, drug, outcome, exc)
                    invalid_count += 1
                    continue
                raise ValueError(f"Row {lineno} ({drug}): {exc}") from exc

            if record is None:
                # Censored row
                drug = row.get("drug", "?")
                if not skip_censored:
                    raise ValueError(
                        f"Row {lineno} ({drug}): censored outcome {row.get('outcome')!r}; "
                        "set skip_censored=True to allow"
                    )
                censored_count += 1
                continue

            records.append(record)

    if censored_count:
        logger.debug("Skipped %d censored (ongoing) rows", censored_count)
    if invalid_count:
        logger.warning("Skipped %d invalid rows", invalid_count)

    if not records:
        raise ValueError(f"No usable outcome records found in {path}")

    return records


# ---------------------------------------------------------------------------
# Bundled dataset path
# ---------------------------------------------------------------------------

def _bundled_csv_path() -> Path:
    """Return the path to the bundled oncology_phase_transitions.csv."""
    # File is in research/data/ relative to the project root.
    # Walk up from this module until we find the research/ directory.
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "research" / "data" / "oncology_phase_transitions.csv"
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "Cannot locate research/data/oncology_phase_transitions.csv. "
        "Pass an explicit csv_path to load_outcome_records()."
    )


def load_bundled_records() -> list[POSOutcomeRecord]:
    """Load the bundled oncology dataset shipped with the repository."""
    return load_outcome_records(_bundled_csv_path())


# ---------------------------------------------------------------------------
# Sponsor track records
# ---------------------------------------------------------------------------

@dataclass
class SponsorTrackRecord:
    """Aggregated success history for one sponsor."""
    sponsor: str
    n_trials: int
    n_success: int
    success_rate: float
    # Phase-level breakdown: phase_key → {"n": int, "n_success": int, "rate": float}
    phases: dict = field(default_factory=dict)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"SponsorTrackRecord({self.sponsor!r}, "
            f"n={self.n_trials}, success_rate={self.success_rate:.1%})"
        )


def build_sponsor_tracks(
    records: list[POSOutcomeRecord],
    min_trials: int = 1,
) -> dict[str, SponsorTrackRecord]:
    """
    Compute sponsor-level success history from a list of outcome records.

    Parameters
    ----------
    records:   Outcome records (censored rows should have been excluded already).
    min_trials: Minimum number of trials for a sponsor to appear in the result.
                Default 1 — include all sponsors with at least one record.

    Returns
    -------
    Dict mapping sponsor name → SponsorTrackRecord.
    """
    # Phase-keyed counts: sponsor → phase → {"n": int, "n_success": int}
    agg: dict[str, dict[str, dict[str, int]]] = {}

    for rec in records:
        sponsor = rec.sponsor
        phase = rec.phase_at_entry
        if sponsor not in agg:
            agg[sponsor] = {}
        if phase not in agg[sponsor]:
            agg[sponsor][phase] = {"n": 0, "n_success": 0}
        agg[sponsor][phase]["n"] += 1
        if rec.success:
            agg[sponsor][phase]["n_success"] += 1

    tracks: dict[str, SponsorTrackRecord] = {}
    for sponsor, phase_data in agg.items():
        n_total = sum(d["n"] for d in phase_data.values())
        if n_total < min_trials:
            continue
        n_success_total = sum(d["n_success"] for d in phase_data.values())
        phases = {
            phase: {
                "n": d["n"],
                "n_success": d["n_success"],
                "rate": d["n_success"] / d["n"] if d["n"] > 0 else 0.0,
            }
            for phase, d in phase_data.items()
        }
        tracks[sponsor] = SponsorTrackRecord(
            sponsor=sponsor,
            n_trials=n_total,
            n_success=n_success_total,
            success_rate=round(n_success_total / n_total, 4) if n_total > 0 else 0.0,
            phases=phases,
        )

    return tracks
