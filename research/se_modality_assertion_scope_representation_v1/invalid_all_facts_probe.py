import json
from pathlib import Path

from bve.se.gates.engine import _requirement
from bve.se.gates.evaluator import evaluate_requirement
from bve.se.schemas.contracts import NormalizedFact, RequirementOperator

r = json.loads(Path("/home/djmann/se_runs/heldout_h19_v4/result.json").read_text())
req = _requirement(
    "modality.required", "modality_id", RequirementOperator.IN, ["ANTIBODY_DRUG_CONJUGATE"]
)
facts = [NormalizedFact.model_validate(f) for f in r["facts"] if f["fact_type"] == "modality_id"]
checked = []
for gate in r["gate_evaluations"]:
    for d in gate["decisions"]:
        if d["requirement_id"] != "modality.required":
            continue
        actual = evaluate_requirement(
            req, subject_id=gate["subject_id"], facts=facts, gate_id=d["gate_id"]
        )
        assert actual.status.value == d["status"], (gate["subject_id"], actual.status, d["status"])
        assert actual.observed_fact_ids == d["observed_fact_ids"]
        checked.append(
            {
                "subject_id": gate["subject_id"],
                "status": d["status"],
                "observed_fact_ids": actual.observed_fact_ids,
            }
        )
Path("/tmp/modality_repr_gates.json").write_text(
    json.dumps(
        {
            "checked": len(checked),
            "deltas": 0,
            "requirement": "H19 frozen ADC modality requirement",
            "decisions": checked,
        },
        sort_keys=True,
    )
    + "\n"
)
print(len(checked), "unchanged modality gate decisions")
