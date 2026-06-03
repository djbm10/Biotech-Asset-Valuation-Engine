"""Render validation grade badges for model outputs."""

from __future__ import annotations

from bve.validation.model_grade import ModelGrade, ModelGradeRecord
from bve.validation.validation_registry import ValidationRegistry, get_registry


_GRADE_EMOJI = {
    ModelGrade.UNVALIDATED: "[UNVALIDATED]",
    ModelGrade.RESEARCH_GRADE: "[RESEARCH]",
    ModelGrade.SCREENING_GRADE: "[SCREENING]",
    ModelGrade.IC_REVIEW_GRADE: "[IC-REVIEW]",
    ModelGrade.DECISION_GRADE: "[DECISION-GRADE]",
}


def render_badge(record: ModelGradeRecord) -> str:
    """Return a one-line badge string for inline use."""
    label = _GRADE_EMOJI.get(record.grade, record.grade.value)
    validated = record.last_validated.isoformat() if record.last_validated else "never"
    return f"{label} {record.model_name} (N={record.n_samples}, validated {validated})"


def render_badge_block(model_names: list[str], registry: ValidationRegistry | None = None) -> str:
    """Return a Markdown block of badges for multiple models."""
    reg = registry or get_registry()
    lines = ["## Model Validation Status", ""]
    for name in model_names:
        record = reg.get(name)
        badge = render_badge(record)
        lines.append(f"- {badge}")
        if record.warning_message:
            lines.append(f"  > {record.warning_message}")
    lines.append("")
    return "\n".join(lines)


def get_output_warning(model_name: str, registry: ValidationRegistry | None = None) -> str | None:
    """Return the warning message for a model, or None if DECISION_GRADE."""
    reg = registry or get_registry()
    return reg.get(model_name).warning_message
