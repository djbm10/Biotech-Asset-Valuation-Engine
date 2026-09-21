"""Derive the two-token drug-name lexicon from the frozen ontology snapshot.

Companion to ``known_drug_names_v1.json``, which holds single tokens only and therefore
cannot see that ``belantamab mafodotin`` is one molecule. Selection is declared in
``docs/se_policies/multi_token_drug_name_identity_v1.md`` before this script was written:
DRUG labels and aliases that are exactly two alphabetic tokens of length >= 5. Nothing is
filtered by suffix or class, so no run can have influenced what is in here.

    python scripts/build_multi_token_drug_names.py
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
from datetime import UTC, datetime

ONTOLOGY = pathlib.Path("data/se/ontology/current")
OUT = pathlib.Path("src/bve/se/lexicon/multi_token_drug_names_v1.json")
MIN_TOKEN_LENGTH = 5
_TWO_ALPHA_TOKENS = re.compile(rf"^[a-z]{{{MIN_TOKEN_LENGTH},}} [a-z]{{{MIN_TOKEN_LENGTH},}}$")


def _candidate_strings(record: dict) -> list[str]:
    return [record.get("label") or "", *(a.get("value", "") for a in record.get("aliases") or [])]


def main() -> None:
    records = ONTOLOGY / "records.jsonl"
    digest = hashlib.sha256(records.read_bytes()).hexdigest()
    names: set[str] = set()
    for line in records.open():
        record = json.loads(line)
        if record.get("entity_type") != "DRUG":
            continue
        for value in _candidate_strings(record):
            folded = " ".join(value.split()).casefold()
            if _TWO_ALPHA_TOKENS.fullmatch(folded):
                names.add(folded)
    OUT.write_text(
        json.dumps(
            {
                "schema_version": "se_multi_token_drug_names_v1",
                "derived_from": str(ONTOLOGY),
                "records_sha256": digest,
                "generated_at": datetime.now(UTC).isoformat(),
                "name_count": len(names),
                "selection": {
                    "entity_type": "DRUG",
                    "fields": "label and aliases",
                    "shape": "exactly two alphabetic tokens",
                    "min_token_length": MIN_TOKEN_LENGTH,
                    "declared_before_building": True,
                },
                "names": sorted(names),
            },
            indent=1,
        )
        + "\n"
    )
    print(f"{len(names)} two-token drug names -> {OUT}")


if __name__ == "__main__":
    main()
