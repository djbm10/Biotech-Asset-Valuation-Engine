"""Cycle 4 P3: the cached, ontology-free screen equals the full-ontology screen byte for byte."""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

from bve.cli.dealscreen import apply_fixture
from bve.dealscreen.workspace import Workspace, ontology_target_normalizer

ROOT = Path(__file__).resolve().parents[3]
SYN, REAL = ROOT / "examples/dealscreen", ROOT / "examples/dealscreen_real"
CASES = {
    "synthetic_200": (SYN / "landscape_200.csv", SYN / "profile_synthetic_vendor.yaml", SYN / "buyer_tl1a_ibd.yaml", None),
    "real_v1": (REAL / "landscape_fcrn_gmg.csv", REAL / "profile_public_landscape.yaml", REAL / "buyer_fcrn_gmg.yaml", None),
    "real_v2": (REAL / "landscape_fcrn_gmg_v2.csv", REAL / "profile_public_landscape_v2.yaml", REAL / "buyer_fcrn_gmg.yaml", None),
    "real_v1_with_cycle1_assertions": (REAL / "landscape_fcrn_gmg.csv", REAL / "profile_public_landscape.yaml",
                                       REAL / "buyer_fcrn_gmg.yaml",
                                       ROOT / "research/dealscreen_product_program/cycle1/simulated_analyst_fixture.csv"),
}


def main(out_dir: Path) -> dict:
    normalizer = ontology_target_normalizer()
    results = {}
    for name, (land, prof, buyer, fixture) in CASES.items():
        ws = Workspace(out_dir / name)
        shutil.rmtree(ws.root, ignore_errors=True)
        ws.import_landscape(land, prof, buyer, target_normalizer=normalizer)
        if fixture:
            from bve.dealscreen.agent import OfflineEvidenceProvider, Question

            ws.screen(normalizer)
            ws.research(OfflineEvidenceProvider(REAL / "evidence_library_public.json", normalizer),
                        [s["asset_id"] for s in ws.screening()["screens"]], list(Question))
            apply_fixture(ws, fixture, "1", normalizer=normalizer)
        ws.screen(normalizer)
        full = (ws.root / "screening.json").read_bytes()
        t = time.perf_counter()
        ws.screen(None)
        cached = (ws.root / "screening.json").read_bytes()
        results[name] = {"byte_identical": full == cached, "fast_path": ws.can_screen_without_ontology(),
                         "cached_screen_seconds_in_process": round(time.perf_counter() - t, 2)}
    return results


if __name__ == "__main__":
    out = main(Path(sys.argv[1]))
    print(json.dumps(out, indent=1))
    (Path(__file__).parent / "equivalence_result.json").write_text(json.dumps(out, indent=1) + "\n")
