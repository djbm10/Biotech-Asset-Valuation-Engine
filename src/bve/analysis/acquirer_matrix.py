"""
P3.2 — Acquirer urgency map: buyer-target matrix with heat-map output.

Builds an N_acquirers × N_targets composite-score matrix from the canonical
ACQUIRER_UNIVERSE and a caller-supplied list of target specs.  Each cell
combines four signals:

    composite = ta_weight   × ta_match          (TA fit)
              + loe_weight  × loe_urgency        (LOE pressure)
              + budget_weight × budget_ok        (affordability)
              + stage_weight  × stage_match      (preferred phase fit)

Default weights: ta=0.35, loe=0.30, budget=0.20, stage=0.15.

The matrix is the primary output; convenience accessors expose:
  - top_pairs(n)              → top-N (acquirer, target) cells by score
  - scores_for_target(name)   → all acquirers ranked vs one target
  - scores_for_acquirer(id)   → one acquirer ranked across all targets
  - heat_map_dict()           → {acquirer_name: {target_name: score}} for rendering
  - as_csv_rows()             → header + data rows for tabular display
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from bve.entities.acquirer import ACQUIRER_UNIVERSE, AcquirerProfile


# ---------------------------------------------------------------------------
# Target spec
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TargetSpec:
    """
    Minimal description of an M&A target.

    Parameters
    ----------
    name : str
        Human-readable company or program name.
    therapeutic_area : str
        Primary TA (e.g. "oncology", "immunology").
    modality : str
        Drug modality (e.g. "small_molecule", "biologic").
    deal_size_millions : float
        Expected acquisition price in USD millions. Used for affordability gate.
    stage : str
        Clinical stage (e.g. "Phase 1", "Phase 2", "Phase 3", "Approved").
        Compared against AcquirerProfile.preferred_phase.
    ticker : Optional[str]
        Stock ticker for display purposes only.
    """
    name: str
    therapeutic_area: str
    modality: str
    deal_size_millions: float
    stage: str = "Phase 3"
    ticker: Optional[str] = None

    def short_label(self) -> str:
        """Return ticker if available, else truncated name."""
        return self.ticker or self.name[:12]


# ---------------------------------------------------------------------------
# Matrix cell
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MatrixCell:
    """
    One (acquirer, target) entry in the buyer-target matrix.

    Attributes
    ----------
    acquirer_id : str
        Canonical acquirer identifier (e.g. "pfizer").
    acquirer_name : str
        Human-readable acquirer name.
    target_name : str
        Target company / program name.
    ta_match : bool
        True when target's TA is in acquirer's strategic_areas.
    modality_match : bool
        True when target's modality is in acquirer's preferred_modalities.
    loe_urgency : float
        Acquirer's composite LOE urgency score [0–1].
    budget_ok : bool
        True when acquirer can afford the deal (deal_size ≤ 25% of firepower).
    stage_match : float
        1.0 = preferred phase matches; 0.5 = "Any" preference or unset; 0.0 = mismatch.
    composite_score : float
        Weighted composite score [0–1]. Higher = stronger strategic fit.
    """
    acquirer_id: str
    acquirer_name: str
    target_name: str
    ta_match: bool
    modality_match: bool
    loe_urgency: float
    budget_ok: bool
    stage_match: float
    composite_score: float

    @property
    def heat_level(self) -> str:
        """Categorical heat level for display: hot | warm | cool | cold."""
        if self.composite_score >= 0.70:
            return "hot"
        if self.composite_score >= 0.50:
            return "warm"
        if self.composite_score >= 0.30:
            return "cool"
        return "cold"


# ---------------------------------------------------------------------------
# Matrix
# ---------------------------------------------------------------------------

@dataclass
class AcquirerMatrix:
    """
    N_acquirers × N_targets buyer-target matrix.

    The ``cells`` attribute is a list of rows (one per acquirer), each row
    containing one MatrixCell per target, in the same order as ``targets``.

    Parameters
    ----------
    acquirers : list[AcquirerProfile]
        Row index — the acquirers scored.
    targets : list[TargetSpec]
        Column index — the targets scored.
    cells : list[list[MatrixCell]]
        ``cells[i][j]`` is the score for acquirer ``i`` vs target ``j``.
    weights : dict[str, float]
        Scoring weights used to build this matrix.
    """
    acquirers: list[AcquirerProfile]
    targets: list[TargetSpec]
    cells: list[list[MatrixCell]]
    weights: dict[str, float] = field(default_factory=dict)

    # ------------------------------------------------------------------ #
    # Cell access                                                          #
    # ------------------------------------------------------------------ #

    def get_cell(self, acquirer_id: str, target_name: str) -> Optional[MatrixCell]:
        """Return the cell for (acquirer_id, target_name), or None if not found."""
        for row in self.cells:
            for cell in row:
                if cell.acquirer_id == acquirer_id and cell.target_name == target_name:
                    return cell
        return None

    # ------------------------------------------------------------------ #
    # Ranked views                                                         #
    # ------------------------------------------------------------------ #

    def top_pairs(self, n: int = 5) -> list[MatrixCell]:
        """Return the top-N (acquirer, target) cells by composite_score."""
        flat = [cell for row in self.cells for cell in row]
        return sorted(flat, key=lambda c: c.composite_score, reverse=True)[:n]

    def scores_for_target(self, target_name: str) -> list[MatrixCell]:
        """All acquirers ranked against a single target, highest score first."""
        cells = [
            cell
            for row in self.cells
            for cell in row
            if cell.target_name == target_name
        ]
        return sorted(cells, key=lambda c: c.composite_score, reverse=True)

    def scores_for_acquirer(self, acquirer_id: str) -> list[MatrixCell]:
        """One acquirer ranked across all targets, highest score first."""
        cells = [
            cell
            for row in self.cells
            for cell in row
            if cell.acquirer_id == acquirer_id
        ]
        return sorted(cells, key=lambda c: c.composite_score, reverse=True)

    # ------------------------------------------------------------------ #
    # Export helpers                                                       #
    # ------------------------------------------------------------------ #

    def heat_map_dict(self) -> dict[str, dict[str, float]]:
        """
        Return ``{acquirer_name: {target_name: composite_score}}``.

        Suitable for JSON serialization or building a pandas DataFrame.
        """
        result: dict[str, dict[str, float]] = {}
        for row in self.cells:
            for cell in row:
                if cell.acquirer_name not in result:
                    result[cell.acquirer_name] = {}
                result[cell.acquirer_name][cell.target_name] = round(cell.composite_score, 3)
        return result

    def as_csv_rows(self) -> list[list]:
        """
        Return header + data rows suitable for writing to CSV or tabular display.

        Header: ["Acquirer", target1, target2, ...]
        Each row: [acquirer_name, score1, score2, ...]
        """
        target_names = [t.name for t in self.targets]
        header = ["Acquirer"] + target_names
        rows = [header]
        for acq, row_cells in zip(self.acquirers, self.cells):
            row = [acq.name] + [round(c.composite_score, 3) for c in row_cells]
            rows.append(row)
        return rows

    def as_heat_map_text(self) -> str:
        """
        ASCII heat-map table for console display.

        Columns are right-aligned; scores formatted to 2 decimal places.
        Long target names are truncated to 10 chars.
        """
        target_labels = [t.short_label()[:10].ljust(10) for t in self.targets]
        col_width = 10
        acq_col = 20

        header = " " * acq_col + "  ".join(t.center(col_width) for t in target_labels)
        separator = "-" * len(header)
        lines = [header, separator]

        for acq, row_cells in zip(self.acquirers, self.cells):
            row_parts = []
            for cell in row_cells:
                score_str = f"{cell.composite_score:.2f}"
                heat = {"hot": "***", "warm": "**", "cool": "*", "cold": ""}[cell.heat_level]
                row_parts.append(f"{score_str}{heat}".center(col_width))
            line = acq.name[:acq_col].ljust(acq_col) + "  ".join(row_parts)
            lines.append(line)

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def _stage_match_score(acq: AcquirerProfile, target_stage: str) -> float:
    """
    Return a stage-match score [0, 0.5, 1.0].

    1.0 = acquirer's preferred_phase matches target stage (case-insensitive prefix)
    0.5 = acquirer has no preference ("Any") or preferred_phase is not set
    0.0 = explicit mismatch
    """
    pref = acq.preferred_phase
    if not pref or pref.lower() in ("any", "all"):
        return 0.5
    # Soft prefix match: "Phase 3" matches "Phase 3" or "Phase 3 (NDA ready)"
    target_normalized = target_stage.lower().strip()
    pref_normalized = pref.lower().strip()
    if target_normalized.startswith(pref_normalized) or pref_normalized.startswith(target_normalized):
        return 1.0
    return 0.0


def _score_cell(
    acq: AcquirerProfile,
    target: TargetSpec,
    ta_weight: float,
    loe_weight: float,
    budget_weight: float,
    stage_weight: float,
) -> MatrixCell:
    """Compute one MatrixCell for (acquirer, target)."""
    ta_match = acq.covers_ta(target.therapeutic_area)
    modality_match = acq.covers_modality(target.modality)
    loe_urgency = acq.loe_urgency
    budget_ok = acq.can_afford(target.deal_size_millions)
    stage_score = _stage_match_score(acq, target.stage)

    composite = (
        ta_weight * float(ta_match)
        + loe_weight * loe_urgency
        + budget_weight * float(budget_ok)
        + stage_weight * stage_score
    )
    composite = round(min(1.0, max(0.0, composite)), 4)

    return MatrixCell(
        acquirer_id=acq.company_id,
        acquirer_name=acq.name,
        target_name=target.name,
        ta_match=ta_match,
        modality_match=modality_match,
        loe_urgency=round(loe_urgency, 4),
        budget_ok=budget_ok,
        stage_match=stage_score,
        composite_score=composite,
    )


def build_acquirer_matrix(
    targets: list[TargetSpec],
    universe: Optional[list[AcquirerProfile]] = None,
    *,
    ta_weight: float = 0.35,
    loe_weight: float = 0.30,
    budget_weight: float = 0.20,
    stage_weight: float = 0.15,
) -> AcquirerMatrix:
    """
    Build a buyer-target composite-score matrix.

    Parameters
    ----------
    targets : list[TargetSpec]
        The M&A targets to score (columns of the matrix).
    universe : list[AcquirerProfile], optional
        Acquirer universe (rows of the matrix). Defaults to ACQUIRER_UNIVERSE.
    ta_weight, loe_weight, budget_weight, stage_weight : float
        Scoring weights. Must sum to 1.0 (validated with tolerance).

    Returns
    -------
    AcquirerMatrix
        N_acquirers × N_targets matrix of MatrixCells.

    Raises
    ------
    ValueError
        When ``targets`` is empty or weights don't sum to ~1.0.
    """
    if not targets:
        raise ValueError("targets list must not be empty")

    total_weight = ta_weight + loe_weight + budget_weight + stage_weight
    if abs(total_weight - 1.0) > 0.01:
        raise ValueError(
            f"Weights must sum to 1.0; got {total_weight:.4f}. "
            f"(ta={ta_weight}, loe={loe_weight}, budget={budget_weight}, stage={stage_weight})"
        )

    acqs = universe if universe is not None else ACQUIRER_UNIVERSE

    cells: list[list[MatrixCell]] = []
    for acq in acqs:
        row = [
            _score_cell(acq, target, ta_weight, loe_weight, budget_weight, stage_weight)
            for target in targets
        ]
        cells.append(row)

    return AcquirerMatrix(
        acquirers=acqs,
        targets=targets,
        cells=cells,
        weights={
            "ta": ta_weight,
            "loe": loe_weight,
            "budget": budget_weight,
            "stage": stage_weight,
        },
    )
