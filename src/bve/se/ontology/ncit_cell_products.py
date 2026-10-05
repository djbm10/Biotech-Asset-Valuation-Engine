"""NCIt product concepts typed ``Cell`` (``ncit_modality_v1``).

A fill-only modality source: an asset with no ChEMBL modality whose unambiguous NCIt link
is a ``Cell``-typed product concept is a cell therapy. The sidecar is the list of those
codes, built from the pinned release and sealed like the other NCIt sidecars.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path

CELL_PRODUCTS_VERSION = "ncit_cell_products_v1"
NCIT_CELL_PRODUCTS_KEY = "ncit_cell_products"
_DEFAULT_PATH = Path("data/se/ontology/ncit/ncit_26.08e_cell_products.json")


def build_cell_products(flat_txt: Path, product_codes: set[str], *, release_zip_sha256: str) -> dict:
    csv.field_size_limit(1 << 30)
    cells = []
    with flat_txt.open(encoding="utf-8") as handle:
        for row in csv.reader(handle, delimiter="\t", quoting=csv.QUOTE_NONE):
            if row[0] in product_codes and "Cell" in row[7].split("|"):
                cells.append(row[0])
    return {
        "version": CELL_PRODUCTS_VERSION,
        "ncit_release": "26.08e",
        "release_zip_sha256": release_zip_sha256,
        "cell_product_codes": sorted(cells),
    }


class NcitCellProducts:
    def __init__(self, payload: dict, sha256: str) -> None:
        self.payload = payload
        self.sha256 = sha256
        self.codes = frozenset(payload["cell_product_codes"])

    @property
    def version_token(self) -> str:
        return f"{CELL_PRODUCTS_VERSION}@ncit_{self.payload['ncit_release']}@{self.sha256[:16]}"


def default_cell_products_path() -> Path:
    override = os.environ.get("BVE_SE_NCIT_CELL_PRODUCTS")
    return Path(override) if override else _DEFAULT_PATH


@lru_cache(maxsize=4)
def _load(path: str) -> NcitCellProducts | None:
    file = Path(path)
    if not file.exists():
        return None
    raw = file.read_bytes()
    return NcitCellProducts(json.loads(raw), hashlib.sha256(raw).hexdigest())


def ncit_cell_products() -> NcitCellProducts | None:
    return _load(str(default_cell_products_path()))


def reset_cell_products_cache() -> None:
    _load.cache_clear()
