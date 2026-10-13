import json
import runpy
from pathlib import Path

ns = runpy.run_path("research/se_target_mention_role_representation_v2/evaluate.py")
rows = json.load(open("research/se_target_mention_role_representation_v1/baseline.json"))
errors = []
for row in rows:
    actual = ns["digest"](ns["decision"](ns["parse_query"](row["query"])))
    if actual != row["decision_sha256"]:
        errors.append({"id": row["id"], "expected": row["decision_sha256"], "actual": actual})
Path("/tmp/role_baseline_check.json").write_text(
    json.dumps({"count": len(rows), "mismatches": errors}, indent=2)
)
