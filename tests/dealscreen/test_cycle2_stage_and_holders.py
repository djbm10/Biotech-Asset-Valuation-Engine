"""Cycle 2: commercial-stage valuation block (V1-V2) and cross-holder same-molecule flag (I1-I3)."""

from __future__ import annotations

from pathlib import Path

from bve.dealscreen.identity import identity_flags
from bve.dealscreen.importer import import_landscape
from bve.dealscreen.mapping import MappingProfile
from bve.dealscreen.valuation_handoff import COMMERCIAL_STAGE_REASON, check_readiness

REAL = Path(__file__).resolve().parents[2] / "examples" / "dealscreen_real"
COMPLETE = {
    "therapeutic_area": "immunology", "stage": "phase_3", "modality": "biologic", "discount_rate": 0.1,
    "ownership": {"royalty_rate": 0.0},
    "market": {"addressable_patients_annual": 1000, "net_price_per_patient_usd": 1, "peak_penetration": 0.1,
               "years_to_peak": 5, "patent_life_years": 10},
    "trials": [{"phase": "phase_3", "success_probability": 0.5, "duration_years": 2, "cost_millions": 10}],
}


def _real_assets():
    profile = MappingProfile.from_yaml(REAL / "profile_public_landscape.yaml")
    return import_landscape(REAL / "landscape_fcrn_gmg.csv", profile).assets


def test_v1_marketed_program_is_not_valued_even_with_complete_inputs():
    asset = _real_assets()[0]
    readiness = check_readiness(asset, COMPLETE, screened_stage_order=6)
    assert not readiness.ready and readiness.missing == [COMMERCIAL_STAGE_REASON]
    approved = check_readiness(asset, {**COMPLETE, "stage": "approved"}, screened_stage_order=None)
    assert not approved.ready


def test_v2_pre_approval_program_with_complete_inputs_is_ready():
    asset = _real_assets()[0]
    assert check_readiness(asset, COMPLETE, screened_stage_order=4).ready
    assert check_readiness(asset, COMPLETE).ready


#: The ChEMBL synonyms the S&E authority resolves for these names (checked 2026-10-28).
AUTHORITY = {"batoclimab": "DRUG:BATOCLIMAB", "hbm9161": "DRUG:BATOCLIMAB", "rvt-1401": "DRUG:BATOCLIMAB",
             "gefurulimab": "DRUG:GEFURULIMAB", "alxn1720": "DRUG:GEFURULIMAB",
             "eculizumab": "DRUG:ECULIZUMAB", "eculizumab-aeeb (bkemv)": None}


def test_i1_i3_real_cross_holder_pair_is_flagged_and_nothing_merges():
    assets = _real_assets()
    flags = identity_flags(assets, authority=lambda n: AUTHORITY.get(n.casefold()))
    by_ext = {a.asset_id: a.external_id for a in assets}
    kinds = {(f.kind, tuple(sorted(by_ext[i] for i in f.asset_ids))) for f in flags}
    assert ("SAME_MOLECULE_DIFFERENT_HOLDER", ("RW-05", "RW-06")) in kinds  # Immunovant / Harbour
    assert ("SAME_MOLECULE_DIFFERENT_HOLDER", ("RW-06", "RW-07")) in kinds  # Harbour / Immunovant code
    assert ("PROPOSED_MERGE", ("RW-05", "RW-07")) in kinds                  # same company
    assert ("PROPOSED_MERGE", ("RW-15", "RW-16")) in kinds
    assert len({a.asset_id for a in assets}) == 40
    assert all(f.relationship == "UNCERTAIN_RELATIONSHIP" for f in flags if f.kind == "SAME_MOLECULE_DIFFERENT_HOLDER")


def test_i2_shared_code_across_companies_is_not_called_the_same_molecule(tmp_path):
    import csv

    profile = MappingProfile.from_yaml(REAL / "profile_public_landscape.yaml")
    headers = list(profile.columns.values())
    path = tmp_path / "mb.csv"
    with path.open("w", newline="") as h:
        w = csv.DictWriter(h, fieldnames=headers)
        w.writeheader()
        w.writerow({**dict.fromkeys(headers, ""), "Program ID": "A", "Program": "MB-102", "Company": "Co A"})
        w.writerow({**dict.fromkeys(headers, ""), "Program ID": "B", "Program": "MB-102", "Company": "Co B"})
    assets = import_landscape(path, profile).assets
    flags = identity_flags(assets, authority=lambda n: "DRUG:RELMAPIRAZIN")
    assert {f.kind for f in flags} == {"SHARED_CODE"}
