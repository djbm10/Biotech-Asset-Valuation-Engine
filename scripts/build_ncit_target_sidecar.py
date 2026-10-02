"""Build the NCIt target sidecar from the pinned 26.08e FLAT release.

Usage::

    PYTHONPATH=src python scripts/build_ncit_target_sidecar.py <Thesaurus_26.08e.FLAT.zip> [<output.json>]

The zip's sha256 must equal the one frozen in ``docs/se_policies/ncit_target_sidecar_v1.md``.
"""

from __future__ import annotations

import json
import sys
import tempfile
import zipfile
from pathlib import Path

from bve.se.ontology.ncit_targets import _sha256, build_sidecar, default_sidecar_path

FROZEN_ZIP_SHA256 = "645ad414c3a0b6ceecda66e132ca66055c15608f39508597c23a3a94b38309da"


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    archive = Path(argv[0])
    output = Path(argv[1]) if len(argv) > 1 else default_sidecar_path()
    digest = _sha256(archive)
    if digest != FROZEN_ZIP_SHA256:
        print(f"refusing: {archive} sha256 {digest} is not the frozen 26.08e release")
        return 1
    with tempfile.TemporaryDirectory() as scratch, zipfile.ZipFile(archive) as bundle:
        bundle.extract("Thesaurus.txt", scratch)
        payload = build_sidecar(Path(scratch) / "Thesaurus.txt", release_zip_sha256=digest)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    reasons: dict[str, int] = {}
    for product in payload["products"].values():
        reasons[product["reason"]] = reasons.get(product["reason"], 0) + 1
    print(f"{output}: {len(payload['products'])} products {reasons} sha256={_sha256(output)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
