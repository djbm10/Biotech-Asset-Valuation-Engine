"""DEVELOPMENT: score a CHEK1 dev run against the disclosed CHEK1 AI reference.

    python research/se_identity_dev_v1/dev_score.py LABEL RESULT.json REFERENCE.json OUT.json

Uses the pilot scorer's own computation (``blinded_pilot._compute``) on two views (all
candidates; eligible + review) so definitions match the sealed pilot. Not a pilot score:
the pilot's official results are untouched.
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from bve.se.evaluation import blinded_pilot as BP
from bve.se.pipeline import SESearchResult

PILOT = Path(__file__).resolve().parents[1] / "se_blinded_pilot_v1/chek1_clinical_any_v1"


def main() -> None:
    label, result_path, ref_path, out = sys.argv[1:5]
    result = SESearchResult.model_validate_json(Path(result_path).read_text())
    reference = BP.ReferenceDataset.model_validate_json(Path(ref_path).read_text())
    criteria = BP.EvaluationCriteria.model_validate_json((PILOT / "criteria.json").read_text())
    export = BP.export_candidates(result, spec_id="chek1_clinical_any_v1", engine_commit="DEV")
    visible = set(result.eligible_asset_ids) | set(result.unresolved_asset_ids)
    views = {"all": export, "visible": export.model_copy(update={
        "candidates": [c for c in export.candidates if c.candidate_id in visible]})}
    receipt = BP.SealReceipt(
        spec_sha256="DEVELOPMENT", criteria_sha256="DEVELOPMENT", candidates_sha256=f"DEV:{label}",
        spec_id="chek1_clinical_any_v1", sealed_at=datetime.now(UTC).isoformat(),
        scorer_commit="DEVELOPMENT", prereg_sha256="DEVELOPMENT", prereg_commit="DEVELOPMENT",
        prereg_committed_at=result.run_manifest.started_at, prereg_on_remote=False,
        run_id=result.run_manifest.run_id, run_started_at=result.run_manifest.started_at)
    body = {"label": label, "grade": "DEVELOPMENT - disclosed example, AI reference, not validation",
            "counts": {"candidates": len(result.candidates), "eligible": len(result.eligible_asset_ids),
                       "review": len(result.unresolved_asset_ids), "excluded": len(result.excluded_asset_ids),
                       "low_support": len(result.low_support_asset_ids),
                       "engine_merges": len(result.identity_merges)}}
    for name, view in views.items():
        report = BP._compute(receipt, criteria, view, reference, "DEVELOPMENT", "UNVALIDATED", "DEV")
        d = report.model_dump(mode="json")
        body[name] = {k: d[k] for k in ("n_candidates", "recall", "precision_strict", "precision_adjudicated",
                                        "true_positives", "false_negatives", "negative_control_hits",
                                        "merge_errors", "split_errors", "trial_coverage_overall",
                                        "trial_coverage_recovered", "target_accuracy",
                                        "target_accuracy_incl_unknown", "modality_accuracy_incl_unknown")}
        body[name]["unadjudicated"] = len(d["unadjudicated_candidates"])
    Path(out).write_text(json.dumps(body, indent=1) + "\n")
    print(json.dumps(body, indent=1))


if __name__ == "__main__":
    main()
