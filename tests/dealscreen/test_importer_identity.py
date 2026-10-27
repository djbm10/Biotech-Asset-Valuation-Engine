"""Importer accounting, provenance and conservative identity (incl. the MB-102 regression)."""

from __future__ import annotations

import csv
import json

import pytest

from bve.dealscreen.identity import identity_flags
from bve.dealscreen.importer import LandscapeImportError, import_landscape
from bve.dealscreen.mapping import MappingProfile


@pytest.fixture
def profile(demo_dir) -> MappingProfile:
    return MappingProfile.from_yaml(demo_dir / "profile_synthetic_vendor.yaml")


def test_every_one_of_200_rows_is_accounted_for(demo_dir, profile):
    result = import_landscape(demo_dir / "landscape_200.csv", profile)
    m = result.manifest
    assert m.rows_read == 200
    assert m.rows_imported + m.rows_rejected + m.rows_exact_duplicate == 200
    assert m.rows_rejected == 2 and m.rows_exact_duplicate == 3
    reasons = " ".join(r for rej in result.rejected for r in rej.reasons)
    assert "external_id" in reasons and "does not match date formats" in reasons
    truth = json.loads((demo_dir / "ground_truth.json").read_text())
    assert {a.external_id for a in result.assets} == set(truth["programs"])


def test_raw_rows_survive_verbatim_and_xlsx_matches_csv(demo_dir, profile):
    csv_result = import_landscape(demo_dir / "landscape_200.csv", profile)
    xlsx_result = import_landscape(demo_dir / "landscape_200.xlsx", profile)
    with (demo_dir / "landscape_200.csv").open(encoding="utf-8") as handle:
        source_rows = list(csv.DictReader(handle))
    for row in csv_result.rows:
        assert row.raw == source_rows[row.row_number - 1]
    def values(result):
        return sorted((c.asset_id, c.field, c.value_as_written) for a in result.assets for c in a.claims)
    assert values(csv_result) == values(xlsx_result)


def test_claims_carry_row_column_source_and_dataset_version(demo_dir, profile):
    result = import_landscape(demo_dir / "landscape_200.csv", profile)
    claim = result.assets[0].claims[0]
    assert claim.row_number in result.assets[0].row_numbers
    assert claim.column in profile.columns.values()
    assert claim.dataset_version == result.manifest.dataset_version
    assert claim.origin.value == "SOURCE_PROVIDED"


def test_same_external_id_twice_is_one_asset_with_both_rows(demo_dir, profile):
    result = import_landscape(demo_dir / "landscape_200.csv", profile)
    multi = [a for a in result.assets if len(a.row_numbers) == 2]
    assert len(multi) == 3  # two phase conflicts and one target conflict


def test_missing_mapped_header_is_a_clear_file_level_error(tmp_path, profile):
    bad = tmp_path / "bad.csv"
    bad.write_text("Drug Name,Target(s)\nX,Y\n")
    with pytest.raises(LandscapeImportError, match="Drug ID"):
        import_landscape(bad, profile)


def test_ragged_csv_row_is_rejected_not_silently_truncated(tmp_path, profile):
    headers = list(profile.columns.values())
    path = tmp_path / "ragged.csv"
    good = ["A1", "Alpha-mab"] + [""] * (len(headers) - 2)
    path.write_text(",".join(headers) + "\n" + ",".join(good) + "\n" + ",".join(good) + ",extra\n")
    # reorder so external_id/program_name land in the right columns
    result = import_landscape(path, profile)
    assert result.manifest.rows_rejected == 1
    assert "more cells than the header" in result.rejected[0].reasons[0]


def test_profile_requires_license_metadata(demo_dir):
    import yaml

    data = yaml.safe_load((demo_dir / "profile_synthetic_vendor.yaml").read_text())
    data["license_status"] = "whatever"
    with pytest.raises(ValueError, match="license_status"):
        MappingProfile(**data)


# -- identity ---------------------------------------------------------------------------
def _two_mb102(profile, tmp_path, *, same_company: bool):
    headers = list(profile.columns.values())
    rows = [
        {"Drug ID": "V-1", "Drug Name": "MB-102", "Synonyms": "MB102", "Originator": "Mustang-like Bio",
         "Target(s)": "IL3RA", "Technology": "CAR-T"},
        {"Drug ID": "V-2", "Drug Name": "MB-102", "Synonyms": "relmapirazin",
         "Originator": "Mustang-like Bio" if same_company else "MediBeacon-like Inc",
         "Target(s)": "", "Technology": "Small molecule"},
    ]
    path = tmp_path / "mb102.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({h: row.get(h, "") for h in headers})
    return import_landscape(path, profile)


def test_mb102_regression_shared_code_is_never_merged(tmp_path, profile):
    result = _two_mb102(profile, tmp_path, same_company=False)
    assert len(result.assets) == 2
    authority = {"mb-102": "DRUG:RELMAPIRAZIN", "mb102": "DRUG:RELMAPIRAZIN",
                 "relmapirazin": "DRUG:RELMAPIRAZIN"}
    flags = identity_flags(result.assets, authority=lambda n: authority.get(n.casefold()))
    kinds = {f.kind for f in flags}
    assert kinds == {"SHARED_CODE"}  # the authority match across companies is NOT proposed
    assert all(f.relationship == "UNCERTAIN_RELATIONSHIP" for f in flags)


def test_authority_match_within_one_company_is_only_proposed(tmp_path, profile):
    result = _two_mb102(profile, tmp_path, same_company=True)
    flags = identity_flags(result.assets, authority=lambda n: "DRUG:X" if "102" in n else None)
    assert "PROPOSED_MERGE" in {f.kind for f in flags}
    assert len(result.assets) == 2  # still two records until an analyst applies it


def test_demo_xb102_pair_is_flagged_and_kept_apart(demo_dir, profile):
    result = import_landscape(demo_dir / "landscape_200.csv", profile)
    flags = [f for f in identity_flags(result.assets) if f.shared_value == "xb102"]
    assert len(flags) == 1 and len(flags[0].asset_ids) == 2
