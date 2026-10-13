"""Validate frozen snapshot field locators and query offsets offline."""

import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
rows = json.loads((root / "audit.json").read_text())
cache = {}
count = 0
for row in rows:
    for assertion in row["assertions"]:
        locator = assertion["locator"]
        path = Path(locator["file"])
        if path not in cache:
            cache[path] = path.read_text().splitlines()
        value = json.loads(cache[path][locator["line"] - 1])
        for part in locator["field"].split("/"):
            value = value[int(part)] if isinstance(value, list) else value[part]
        assert value == assertion["raw_label"]
        count += 1
    for start, end in row["span_candidates"]:
        assert row["query"][start:end] == row["surface"]
assert len(rows) == 124
assert sum(row["category"] == "prior_failure" for row in rows) == 77
assert all(row["assertions"] for row in rows if row["category"] == "prior_failure")
print(f"{len(rows)} observations; {count} exact raw-field round-trips; offsets valid")
