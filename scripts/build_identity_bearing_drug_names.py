"""Derive the identity-bearing drug-name lexicon from the frozen ontology snapshot.

``known_drug_names_v1.json`` answers "does the ontology hold this string anywhere", which is
the right question for **nomination** -- a trade name should absolutely nominate a mention so
it can be resolved to its parent. It is the wrong question for **qualification**, because the
ontology holds ordinary English as trade names: ``frontline`` is FIPRONIL, a veterinary
insecticide; ``choice`` is WARFARIN; ``discase`` is CHYMOPAPAIN.

Selection is declared in ``docs/se_policies/asset_nomination_evidence_v1.md`` amendment 8a,
committed before this script was written: alias types that bear identity rather than
branding. Measured there over 40 ordinary English words, ``TRADE_NAME`` is the only alias
type that admits any of them, and it admits exactly those three.

Excluding trade names from *this* artifact does not lose Keytruda. A trade name still
nominates, still resolves to its parent, and the parent qualifies on its own use context --
which is the point of amendment 8a, since ``Keytruda``'s occurrences are administration
frames and ``frontline``'s are attributive.

    python scripts/build_identity_bearing_drug_names.py
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re
from datetime import UTC, datetime

ONTOLOGY = pathlib.Path("data/se/ontology/current")
OUT = pathlib.Path("src/bve/se/lexicon/identity_bearing_drug_names_v1.json")

#: Alias types that assert what a molecule *is*. ``TRADE_NAME`` asserts what it is *sold as*
#: and is excluded; ``XREF`` is a database accession, not a name a document would use.
IDENTITY_BEARING = ("APPROVED_NAME", "SYNONYM", "DEVELOPMENT_CODE")

#: Multi-token names are kept, unlike the single-token lexicon this one sits beside. That
#: artifact feeds a scan over prose, where a phrase cannot be looked up; this one answers an
#: exact question about one candidate name. Excluding them dropped ``AMG 420`` -- a sponsor
#: code whose separator is a space -- along with every repaired two-token molecule.
_ANY_NAME = re.compile(r"^\S+(?: \S+)*$")


def main() -> None:
    records = ONTOLOGY / "records.jsonl"
    digest = hashlib.sha256(records.read_bytes()).hexdigest()
    names: set[str] = set()
    for line in records.open():
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        if record.get("entity_type") != "DRUG":
            continue
        values = [record.get("canonical_symbol") or "", record.get("label") or ""]
        values += [
            alias.get("value", "")
            for alias in record.get("aliases") or []
            if alias.get("alias_type") in IDENTITY_BEARING
        ]
        for value in values:
            folded = " ".join(value.split()).casefold()
            if folded and _ANY_NAME.fullmatch(folded):
                names.add(folded)
    OUT.write_text(
        json.dumps(
            {
                "schema_version": "se_identity_bearing_drug_names_v1",
                "derived_from": str(ONTOLOGY),
                "records_sha256": digest,
                "generated_at": datetime.now(UTC).isoformat(),
                "name_count": len(names),
                "selection": {
                    "entity_type": "DRUG",
                    "fields": "canonical_symbol, label, and aliases of identity-bearing type",
                    "identity_bearing_alias_types": list(IDENTITY_BEARING),
                    "excluded_alias_types": ["TRADE_NAME", "XREF"],
                    "shape": "one or more space-separated tokens",
                    "declared_before_building": True,
                    "policy": "docs/se_policies/asset_nomination_evidence_v1.md#8a",
                },
                "names": sorted(names),
            },
            indent=1,
        )
        + "\n"
    )
    print(f"{len(names)} identity-bearing drug names -> {OUT}")


if __name__ == "__main__":
    main()
