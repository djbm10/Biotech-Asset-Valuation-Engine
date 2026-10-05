"""Build the NCIt Cell-typed product sidecar (``ncit_modality_v1``).

    PYTHONPATH=src python scripts/build_ncit_cell_products.py <Thesaurus_26.08e.FLAT.zip> [<output.json>]
"""

from __future__ import annotations

import json
import sys
import tempfile
import zipfile
from pathlib import Path

from bve.se.ontology.ncit_cell_products import build_cell_products, default_cell_products_path
from bve.se.ontology.ncit_targets import _sha256, ncit_authority

FROZEN_ZIP_SHA256 = "645ad414c3a0b6ceecda66e132ca66055c15608f39508597c23a3a94b38309da"


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    archive = Path(argv[0])
    output = Path(argv[1]) if len(argv) > 1 else default_cell_products_path()
    digest = _sha256(archive)
    if digest != FROZEN_ZIP_SHA256:
        print(f"refusing: {archive} sha256 {digest} is not the frozen 26.08e release")
        return 1
    authority = ncit_authority()
    if authority is None:
        print("the NCIt target sidecar must be installed first")
        return 1
    with tempfile.TemporaryDirectory() as scratch, zipfile.ZipFile(archive) as bundle:
        bundle.extract("Thesaurus.txt", scratch)
        payload = build_cell_products(
            Path(scratch) / "Thesaurus.txt", set(authority.products), release_zip_sha256=digest
        )
    output.write_text(json.dumps(payload, sort_keys=True) + "\n")
    print(f"{output}: {len(payload['cell_product_codes'])} codes sha256={_sha256(output)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
