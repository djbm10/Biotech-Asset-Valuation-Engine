"""Derive the identity-bearing drug-name lexicon from the frozen ontology snapshot.

``known_drug_names_v1.json`` answers "does the ontology hold this string anywhere", which is
the right question for **nomination** -- a trade name should absolutely nominate a mention so
it can be resolved to its parent. It is the wrong question for **qualification**, because the
ontology holds ordinary English as trade names: ``frontline`` is FIPRONIL, a veterinary
insecticide; ``choice`` is WARFARIN; ``discase`` is CHYMOPAPAIN.

Selection is declared in ``docs/se_policies/asset_qualification_tiered_evidence_v3.md``
§3a, committed before this script was rewritten. v1 of this artifact excluded ``TRADE_NAME``
and kept ``SYNONYM``, which removed ``frontline``/``choice``/``discase`` and left ``paper``
-- a ChEMBL synonym -- to reach shortlist position 10 on a live run.

So the artifact now carries two tiers rather than one list. A directly-qualifying name may
place a string on the default canonical path by itself. A corroborative name may resolve a
mention to its parent and nothing more; it needs a second, independent qualification route.
That preserves ``Keytruda`` as an alias of pembrolizumab and legacy synonyms as aliases of
their molecules, without letting ontology membership alone decide that a string is an asset.

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

#: Alias types that assert what a molecule *is*, in a form the ontology treats as its
#: identity. These may qualify a name on their own.
DIRECTLY_QUALIFYING = ("APPROVED_NAME", "DEVELOPMENT_CODE")

#: Alias types that can resolve a mention to a parent asset but may not, alone, place that
#: string on the default canonical path. ``TRADE_NAME`` asserts what a molecule is *sold
#: as*; ``SYNONYM`` is whatever a depositor wrote in the synonym field, which measurably
#: includes ordinary English -- ``paper`` reached shortlist position 10 through it.
#: ``XREF`` is a database accession, not a name a document would use, and is in neither.
CORROBORATIVE = ("SYNONYM", "TRADE_NAME")

#: Multi-token names are kept, unlike the single-token lexicon this one sits beside. That
#: artifact feeds a scan over prose, where a phrase cannot be looked up; this one answers an
#: exact question about one candidate name. Excluding them dropped ``AMG 420`` -- a sponsor
#: code whose separator is a space -- along with every repaired two-token molecule.
_ANY_NAME = re.compile(r"^\S+(?: \S+)*$")


def main() -> None:
    records = ONTOLOGY / "records.jsonl"
    digest = hashlib.sha256(records.read_bytes()).hexdigest()
    direct: set[str] = set()
    corroborative: set[str] = set()
    for line in records.open():
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        if record.get("entity_type") != "DRUG":
            continue
        tiered = [
            (record.get("canonical_symbol") or "", direct),
            (record.get("label") or "", direct),
        ]
        for alias in record.get("aliases") or []:
            alias_type = alias.get("alias_type")
            if alias_type in DIRECTLY_QUALIFYING:
                tiered.append((alias.get("value", ""), direct))
            elif alias_type in CORROBORATIVE:
                tiered.append((alias.get("value", ""), corroborative))
        for value, tier in tiered:
            folded = " ".join(value.split()).casefold()
            if folded and _ANY_NAME.fullmatch(folded):
                tier.add(folded)
    # A name carried in both tiers is directly qualifying: one record's synonym is another
    # record's approved name, and the stronger claim wins.
    corroborative -= direct
    OUT.write_text(
        json.dumps(
            {
                "schema_version": "se_identity_bearing_drug_names_v1",
                "derived_from": str(ONTOLOGY),
                "records_sha256": digest,
                "generated_at": datetime.now(UTC).isoformat(),
                "name_count": len(direct),
                "corroborative_name_count": len(corroborative),
                "selection": {
                    "entity_type": "DRUG",
                    "fields": "canonical_symbol, label, and aliases of identity-bearing type",
                    "directly_qualifying_alias_types": list(DIRECTLY_QUALIFYING),
                    "corroborative_alias_types": list(CORROBORATIVE),
                    "excluded_alias_types": ["XREF"],
                    "shape": "one or more space-separated tokens",
                    "declared_before_building": True,
                    "policy": "docs/se_policies/asset_qualification_tiered_evidence_v3.md#3a",
                },
                "names": sorted(direct),
                "corroborative_names": sorted(corroborative),
            },
            indent=1,
        )
        + "\n"
    )
    print(
        f"{len(direct)} directly-qualifying and {len(corroborative)} corroborative "
        f"drug names -> {OUT}"
    )


if __name__ == "__main__":
    main()
