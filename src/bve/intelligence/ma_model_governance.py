"""Layer 5 — 5H: Model Governance, Model Card, and Audit Reporting.

Produces auditable governance artifacts for the M&A scoring system.

Responsibilities:
  - Generate a human-readable Model Card summarising calibration,
    known limitations, and operating instructions
  - Produce a Layer Validation Report that records which layer outputs
    have been validated against known historical answers
  - Create a Governance Checklist capturing required sign-offs before
    any production deployment
  - Generate Audit Trails (structured JSONL records) for every scored
    prediction to satisfy regulatory and institutional review requirements

Layer 5 governance NEVER:
  - Silently modifies model weights or thresholds
  - Suppresses uncertainty warnings
  - Produces "validated" stamps unless the validation criteria are met

All governance artifacts should be treated as advisory unless explicitly
approved by a human reviewer.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any, Optional

from bve.intelligence.ma_calibration_models import (
    CalibrationArtifact,
    CalibrationDiagnostics,
    CalibrationGovernanceMetadata,
    CalibrationQualityLabel,
    DriftReport,
    Layer5CalibrationConfig,
    Layer5CalibrationOutput,
    LayerValidated,
    SegmentDiagnostics,
    ThresholdRecommendation,
)


# ---------------------------------------------------------------------------
# Layer validation report
# ---------------------------------------------------------------------------

def generate_layer_validation_report(
    cases_validated: dict[LayerValidated, int],
    *,
    known_answer_cases: int = 0,
    top_k_precision: Optional[float] = None,
    base_rate_coverage: Optional[float] = None,
    validation_date: Optional[date] = None,
) -> dict[str, Any]:
    """Generate a layer-by-layer validation report.

    Args:
        cases_validated: Dict mapping each validated layer to the number of
            cases used in that validation.
        known_answer_cases: Count of cases with known historical outcomes.
        top_k_precision: Precision at top-K for the end-to-end pipeline.
        base_rate_coverage: Fraction of cases where base rate calibration applies.
        validation_date: Date of validation run (defaults to today).

    Returns:
        Dict with keys: validation_date, layers, summary, limitations.
    """
    vdate = (validation_date or date.today()).isoformat()
    layers_summary = []
    for layer, n in sorted(cases_validated.items(), key=lambda x: x[0].value):
        status = "validated" if n >= 10 else "insufficient_data"
        layers_summary.append({
            "layer": layer.value,
            "cases_validated": n,
            "status": status,
            "note": (
                "Validated against historical outcomes."
                if status == "validated"
                else f"Only {n} cases available — insufficient for reliable validation."
            ),
        })

    summary_status = "pass" if all(
        row["status"] == "validated" for row in layers_summary
    ) else "partial"

    limitations = [
        "Validation is limited by availability of resolved historical outcomes.",
        "Known-answer test set may exhibit survivorship bias toward completed deals.",
        "Layer 3 and Layer 4 validation requires pair-level ground truth which is sparse.",
    ]
    if known_answer_cases < 30:
        limitations.append(
            f"Only {known_answer_cases} known-answer cases available; "
            "precision estimates are high-variance."
        )

    return {
        "validation_date": vdate,
        "layers": layers_summary,
        "known_answer_cases": known_answer_cases,
        "top_k_precision": top_k_precision,
        "base_rate_coverage": base_rate_coverage,
        "summary_status": summary_status,
        "limitations": limitations,
    }


# ---------------------------------------------------------------------------
# Model card
# ---------------------------------------------------------------------------

def generate_model_card(
    governance: CalibrationGovernanceMetadata,
    diagnostics: Optional[CalibrationDiagnostics] = None,
    segment_diagnostics: Optional[list[SegmentDiagnostics]] = None,
    drift_report: Optional[DriftReport] = None,
    config: Optional[Layer5CalibrationConfig] = None,
    *,
    include_segment_detail: bool = False,
) -> str:
    """Generate a human-readable Model Card in Markdown format.

    Args:
        governance: Governance metadata for the calibration artifact.
        diagnostics: Training diagnostics from the calibration run.
        segment_diagnostics: Per-segment calibration diagnostics.
        drift_report: Most recent drift report.
        config: Calibration config.
        include_segment_detail: If True, include per-segment table.

    Returns:
        Markdown string representing the Model Card.
    """
    lines = [
        "# M&A Probability Scoring — Model Card",
        "",
        f"**Model Version**: {governance.model_version}  ",
        f"**Calibration Date**: {governance.calibration_date.isoformat()}  ",
        f"**Dataset Version**: {governance.calibration_dataset_version}  ",
        f"**Feature Schema**: {governance.feature_schema_version}  ",
    ]
    if governance.calibration_artifact_id:
        lines.append(f"**Artifact ID**: {governance.calibration_artifact_id}  ")
    if governance.training_window_start and governance.training_window_end:
        lines.extend([
            f"**Training Window**: "
            f"{governance.training_window_start.isoformat()} — "
            f"{governance.training_window_end.isoformat()}  ",
        ])
    lines.append("")

    # Intended use
    lines.extend([
        "## Intended Use",
        "",
        "This model produces calibrated probability estimates and rank scores for",
        "biotech M&A scenarios. It is designed to assist BD/corporate development",
        "professionals in prioritizing targets and structuring outreach — NOT to",
        "autonomously make or execute investment or acquisition decisions.",
        "",
        "**Outputs are advisory only.** All recommendations require human review",
        "before acting on them.",
        "",
    ])

    # Architecture summary
    lines.extend([
        "## Architecture",
        "",
        "| Layer | Role |",
        "|-------|------|",
        "| L0 | Eligibility pre-filter |",
        "| L1 | Strategic attractiveness scoring |",
        "| L2 | BD action prioritization |",
        "| L3 | Pair-specific deal realism |",
        "| L4 | BD routing and execution playbook |",
        "| L5 | Calibration, validation, learning, governance (this layer) |",
        "",
    ])

    # Calibration diagnostics
    if diagnostics:
        lines.extend([
            "## Calibration Diagnostics",
            "",
            f"- **Method**: {diagnostics.calibration_method.value}",
            f"- **Sample size**: {diagnostics.sample_size}",
            f"- **Effective N**: {diagnostics.effective_sample_size:.1f}",
        ])
        if diagnostics.base_rate is not None:
            lines.append(f"- **Historical base rate**: {diagnostics.base_rate:.2%}")
        if diagnostics.brier_score is not None:
            lines.append(f"- **Brier score**: {diagnostics.brier_score:.4f}")
        if diagnostics.auc is not None:
            lines.append(f"- **AUC-ROC**: {diagnostics.auc:.3f}")
        if diagnostics.expected_calibration_error is not None:
            lines.append(f"- **ECE**: {diagnostics.expected_calibration_error:.4f}")
        if diagnostics.warnings:
            lines.append("- **Calibration warnings**:")
            for w in diagnostics.warnings:
                lines.append(f"  - {w}")
        lines.append("")

    # Drift status
    if drift_report:
        lines.extend([
            "## Drift Status",
            "",
            f"- **Status**: {drift_report.drift_status}",
            f"- **Requires recalibration**: {drift_report.requires_recalibration}",
        ])
        if drift_report.drift_types:
            types_str = ", ".join(t.value for t in drift_report.drift_types)
            lines.append(f"- **Drift types detected**: {types_str}")
        if drift_report.evidence:
            lines.append("- **Evidence**:")
            for e in drift_report.evidence:
                lines.append(f"  - {e}")
        if drift_report.recommended_action:
            lines.append(f"- **Recommended action**: {drift_report.recommended_action}")
        lines.append("")

    # Segment coverage
    if segment_diagnostics:
        total = len(segment_diagnostics)
        high_conf = sum(
            1 for s in segment_diagnostics
            if s.reliability_label == CalibrationQualityLabel.HIGH_CONFIDENCE
        )
        ood = sum(1 for s in segment_diagnostics if s.out_of_domain_warning)
        lines.extend([
            "## Segment Coverage",
            "",
            f"- **Total segments evaluated**: {total}",
            f"- **High confidence segments**: {high_conf} ({high_conf/max(total,1):.0%})",
            f"- **Out-of-domain segments**: {ood}",
            "",
        ])

        if include_segment_detail:
            lines.extend([
                "### Per-Segment Detail",
                "",
                "| Segment | N | Reliability | Base Rate | Calibrated Rate |",
                "|---------|---|-------------|-----------|-----------------|",
            ])
            for seg in segment_diagnostics[:20]:  # limit to first 20
                br = f"{seg.base_rate:.2%}" if seg.base_rate is not None else "—"
                cr = f"{seg.calibrated_rate:.2%}" if seg.calibrated_rate is not None else "—"
                lines.append(
                    f"| {seg.segment_key} | {seg.sample_size} | "
                    f"{seg.reliability_label.value} | {br} | {cr} |"
                )
            if len(segment_diagnostics) > 20:
                lines.append(f"| _(+{len(segment_diagnostics)-20} more)_ | | | | |")
            lines.append("")

    # Known limitations
    lines.extend([
        "## Known Limitations",
        "",
    ])
    for lim in governance.known_limitations:
        lines.append(f"- {lim}")
    if not governance.known_limitations:
        lines.extend([
            "- Historical outcome data is sparse; calibration is driven by global base rates",
            "  in most segments.",
            "- Deal outcomes take 12–36 months to resolve; calibration window necessarily lags.",
            "- Acquirer fit is modeled from public signals only; private strategic intent is",
            "  not observable.",
            "- Model does not account for macroeconomic or regulatory regime changes unless",
            "  explicitly re-calibrated.",
        ])
    lines.append("")

    # Governance and approval
    lines.extend([
        "## Governance",
        "",
        "| Item | Status |",
        "|------|--------|",
        "| Threshold recommendations auto-applied | NO — human review required |",
        "| Weight updates auto-applied | NO — human review required |",
        "| Production deployment | Requires sign-off per operating mode |",
        "| Re-calibration trigger | Drift severity >= moderate OR Brier delta > 0.05 |",
        "",
        f"**Excluded cases (leakage)**: {governance.excluded_case_count}",
        "",
        "_This model card was generated automatically. It must be reviewed and",
        "approved by a qualified reviewer before production use._",
    ])

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Governance checklist
# ---------------------------------------------------------------------------

def generate_governance_checklist(
    governance: CalibrationGovernanceMetadata,
    diagnostics: Optional[CalibrationDiagnostics] = None,
    drift_report: Optional[DriftReport] = None,
    threshold_recs: Optional[list[ThresholdRecommendation]] = None,
) -> dict[str, Any]:
    """Generate a governance checklist for pre-deployment review.

    Returns a structured checklist dict with pass/warn/fail items.
    """
    checks: list[dict] = []

    # Sample size
    if diagnostics:
        n = diagnostics.sample_size
        if n >= 100:
            checks.append({"item": "Calibration sample size", "status": "pass", "detail": f"N={n}"})
        elif n >= 30:
            checks.append({"item": "Calibration sample size", "status": "warn",
                           "detail": f"N={n} — below recommended N=100"})
        else:
            checks.append({"item": "Calibration sample size", "status": "fail",
                           "detail": f"N={n} — too small; rank-only mode recommended"})

    # Brier score
    if diagnostics and diagnostics.brier_score is not None:
        b = diagnostics.brier_score
        if b < 0.20:
            checks.append({"item": "Brier score", "status": "pass", "detail": f"{b:.4f} < 0.20"})
        elif b < 0.25:
            checks.append({"item": "Brier score", "status": "warn", "detail": f"{b:.4f}"})
        else:
            checks.append({"item": "Brier score", "status": "fail",
                           "detail": f"{b:.4f} >= 0.25 — poor calibration"})

    # AUC
    if diagnostics and diagnostics.auc is not None:
        a = diagnostics.auc
        if a >= 0.65:
            checks.append({"item": "AUC-ROC", "status": "pass", "detail": f"{a:.3f}"})
        elif a >= 0.55:
            checks.append({"item": "AUC-ROC", "status": "warn", "detail": f"{a:.3f}"})
        else:
            checks.append({"item": "AUC-ROC", "status": "fail",
                           "detail": f"{a:.3f} < 0.55 — near-random discrimination"})

    # Drift status
    if drift_report:
        ds = drift_report.drift_status
        if ds == "none":
            checks.append({"item": "Drift status", "status": "pass", "detail": "No drift detected"})
        elif ds == "mild":
            checks.append({"item": "Drift status", "status": "warn",
                           "detail": "Mild drift — monitor closely"})
        else:
            checks.append({"item": "Drift status", "status": "fail",
                           "detail": f"Drift={ds} — re-calibration required before deployment"})

    # Threshold recommendations
    if threshold_recs:
        auto_apply = [r for r in threshold_recs if r.should_auto_apply]
        if not auto_apply:
            checks.append({"item": "Threshold auto-apply", "status": "pass",
                           "detail": "No thresholds marked for auto-apply"})
        else:
            checks.append({"item": "Threshold auto-apply", "status": "fail",
                           "detail": f"{len(auto_apply)} threshold(s) incorrectly marked auto-apply"})

    # Leakage exclusions
    if governance.excluded_case_count > 0:
        checks.append({
            "item": "Leakage exclusions",
            "status": "warn",
            "detail": f"{governance.excluded_case_count} cases excluded due to leakage",
        })
    else:
        checks.append({"item": "Leakage exclusions", "status": "pass",
                       "detail": "No leakage exclusions"})

    # Human review flag
    checks.append({
        "item": "Human review required",
        "status": "warn",
        "detail": "All threshold and weight changes require explicit human approval",
    })

    overall = "pass"
    if any(c["status"] == "fail" for c in checks):
        overall = "fail"
    elif any(c["status"] == "warn" for c in checks):
        overall = "warn"

    return {
        "checklist_date": date.today().isoformat(),
        "overall": overall,
        "checks": checks,
        "deployment_allowed": overall != "fail",
        "sign_off_required": True,
    }


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------

def build_audit_record(
    output: Layer5CalibrationOutput,
    *,
    run_id: Optional[str] = None,
    user_id: Optional[str] = None,
) -> dict[str, Any]:
    """Build a structured audit record for a single Layer 5 prediction.

    Args:
        output: The Layer5CalibrationOutput for this prediction.
        run_id: Optional run identifier for batch tracing.
        user_id: Optional user/system identifier who triggered the run.

    Returns:
        Dict suitable for serialisation to a JSONL audit log.
    """
    record: dict[str, Any] = {
        "audit_version": "1.0",
        "run_id": run_id,
        "user_id": user_id,
        "prediction_date": output.prediction_date.isoformat() if output.prediction_date else None,
        "target_id": output.target_id,
        "acquirer_id": output.acquirer_id,
        "layer4_route": output.layer4_route,
        "calibration_quality": output.calibration_quality.value,
        "do_not_use_as_probability": output.do_not_use_as_probability,
        "do_not_use_as_probability_reason": output.do_not_use_as_probability_reason,
        "calibrated_probabilities": output.calibrated_probabilities.model_dump(mode="json"),
        "raw_scores": output.raw_scores,
        "governance_version": output.governance.model_version,
        "governance_calibration_date": output.governance.calibration_date.isoformat(),
        "warnings": output.warnings,
        "drift_warnings": output.drift_warnings,
        "missing_data": output.missing_data,
    }

    # Diagnostics summary (avoid embedding large reliability tables)
    diag = output.calibration_diagnostics
    record["diagnostics_summary"] = {
        "method": diag.calibration_method.value,
        "sample_size": diag.sample_size,
        "brier_score": diag.brier_score,
        "auc": diag.auc,
    }

    return record


def write_audit_log(
    records: list[dict[str, Any]],
    path: str,
) -> None:
    """Append audit records to a JSONL file (one record per line).

    Args:
        records: List of audit record dicts (from build_audit_record).
        path: Absolute path to the JSONL file.
    """
    from pathlib import Path
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("a", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, default=str) + "\n")


# ---------------------------------------------------------------------------
# Convenience: full governance report
# ---------------------------------------------------------------------------

def generate_governance_report(
    artifact: CalibrationArtifact,
    *,
    drift_report: Optional[DriftReport] = None,
    threshold_recs: Optional[list[ThresholdRecommendation]] = None,
    segment_diagnostics: Optional[list[SegmentDiagnostics]] = None,
    config: Optional[Layer5CalibrationConfig] = None,
    include_model_card: bool = True,
    include_checklist: bool = True,
    include_layer_validation: bool = False,
) -> dict[str, Any]:
    """Generate the full governance report for a calibration artifact.

    Args:
        artifact: Fitted calibration artifact.
        drift_report: Most recent drift detection report.
        threshold_recs: Current threshold recommendations.
        segment_diagnostics: Per-segment calibration diagnostics.
        config: Calibration config.
        include_model_card: Whether to include the model card markdown.
        include_checklist: Whether to include the governance checklist.
        include_layer_validation: Whether to include a layer validation skeleton.

    Returns:
        Nested dict with keys: artifact_id, governance, model_card, checklist, etc.
    """
    report: dict[str, Any] = {
        "artifact_id": artifact.artifact_id,
        "generated_at": date.today().isoformat(),
        "governance": artifact.governance.model_dump(mode="json"),
    }

    if include_model_card:
        report["model_card"] = generate_model_card(
            artifact.governance,
            diagnostics=artifact.training_diagnostics,
            segment_diagnostics=segment_diagnostics,
            drift_report=drift_report,
            config=config,
        )

    if include_checklist:
        report["checklist"] = generate_governance_checklist(
            artifact.governance,
            diagnostics=artifact.training_diagnostics,
            drift_report=drift_report,
            threshold_recs=threshold_recs,
        )

    if drift_report:
        report["drift_report"] = drift_report.model_dump(mode="json")

    if threshold_recs:
        report["threshold_recommendations"] = [
            r.model_dump(mode="json") for r in threshold_recs
        ]

    if include_layer_validation:
        report["layer_validation"] = generate_layer_validation_report(
            {LayerValidated.END_TO_END: artifact.global_sample_size},
            known_answer_cases=artifact.global_sample_size,
        )

    return report
