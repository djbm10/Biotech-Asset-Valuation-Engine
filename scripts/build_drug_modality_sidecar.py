"""Extract ChEMBL ``molecule_type`` for every ChEMBL id the installed ontology's drugs carry.

Usage::

    PYTHONPATH=src python3 scripts/build_drug_modality_sidecar.py <chembl_37.db> [<output.json>]

The output is local data like the snapshot itself, pinned by release and sqlite sha256.
See ``docs/se_policies/authority_modality_v1.md``.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

from bve.se.ontology.drug_modality import default_modality_path
from bve.se.ontology.records import EntityType
from bve.se.ontology.targets import default_snapshot_path, get_resolver

RELEASE = "ChEMBL_37"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    database = Path(argv[0])
    output = Path(argv[1]) if len(argv) > 1 else default_modality_path()
    resolver = get_resolver()
    if resolver is None:
        print(f"no ontology snapshot at {default_snapshot_path()}", file=sys.stderr)
        return 1
    wanted = sorted(
        {
            chembl_id
            for entity in resolver.entities_of_type(EntityType.DRUG)
            for record in entity.source_records
            for chembl_id in record.xrefs.get("chembl", [])
        }
    )
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        rows = connection.execute(
            "SELECT chembl_id, molecule_type FROM molecule_dictionary WHERE molecule_type IS NOT NULL"
        ).fetchall()
    known = dict(rows)
    molecule_types = {cid: known[cid] for cid in wanted if cid in known}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "release": RELEASE,
                "source_sha256": _sha256(database),
                "ontology_version": resolver.ontology_version,
                "molecule_types": molecule_types,
            },
            indent=0,
            sort_keys=True,
        )
    )
    print(f"{len(molecule_types)}/{len(wanted)} ChEMBL ids typed -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
