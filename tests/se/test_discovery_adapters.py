from __future__ import annotations

from datetime import date

from bve.se.discovery.adapters import ClinicalTrialsGovAdapter
from bve.se.schemas.contracts import CompiledQuery, SearchOutcome


def _protocol(*, title: str = "Study of Asset A CD19 x CD3 bispecific") -> dict:
    return {
        "identificationModule": {"nctId": "NCT00000001", "briefTitle": title},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Example Bio"}},
        "statusModule": {"lastUpdatePostDateStruct": {"date": "2026-01-01"}},
        "armsInterventionsModule": {
            "interventions": [{"name": "Asset A", "description": "CD19 T-cell engager"}]
        },
    }


def test_ctgov_adapter_normalizes_program_and_traceability() -> None:
    def search_fn(**kwargs):
        assert "CD19" in kwargs["intervention"]
        return [_protocol()]

    result = ClinicalTrialsGovAdapter(search_fn).search(
        CompiledQuery(
            query_id="q:1",
            query="CD19 T-cell engager",
            target_ids=["CD19"],
            modality_ids=["T_CELL_ENGAGER"],
        ),
        as_of_date=date(2026, 7, 10),
    )
    assert result.outcome == SearchOutcome.SUCCESS
    assert result.hits[0].asset_name == "Asset A"
    assert result.hits[0].company_name == "Example Bio"
    assert result.hits[0].trial_id == "NCT00000001"
    assert result.snapshot_ids


def test_ctgov_adapter_filters_wrong_target_and_future_evidence() -> None:
    query = CompiledQuery(
        query_id="q:1",
        query="BCMA T-cell engager",
        target_ids=["BCMA"],
        modality_ids=["T_CELL_ENGAGER"],
    )
    wrong_target = ClinicalTrialsGovAdapter(lambda **_: [_protocol()]).search(
        query, as_of_date=date(2026, 7, 10)
    )
    future = _protocol(title="BCMA x CD3 bispecific")
    future["statusModule"]["lastUpdatePostDateStruct"]["date"] = "2027-01-01"
    future_result = ClinicalTrialsGovAdapter(lambda **_: [future]).search(
        query, as_of_date=date(2026, 7, 10)
    )
    assert wrong_target.hits == []
    assert future_result.hits == []


def test_ctgov_adapter_surfaces_connector_failure() -> None:
    def fail(**kwargs):
        raise RuntimeError("offline")

    result = ClinicalTrialsGovAdapter(fail).search(
        CompiledQuery(query_id="q", query="CD19", target_ids=["CD19"]),
        as_of_date=date(2026, 7, 10),
    )
    assert result.outcome == SearchOutcome.FAILED
    assert result.error == "offline"


def test_ctgov_adapter_recognizes_source_observed_tce_wording_variants() -> None:
    query = CompiledQuery(
        query_id="q:tce-variants",
        query="BCMA T-cell engager",
        target_ids=["BCMA"],
        modality_ids=["T_CELL_ENGAGER"],
    )
    for asset, description in (
        ("AZD0486", "BCMA x CD3 T-cell engaging bispecific antibody"),
        ("SIM0500", "GPRC5D-BCMA-CD3 tri-specific antibody"),
        ("MGD011", "BCMA x CD3 dual-affinity re-targeting DART protein"),
    ):
        protocol = _protocol(title=f"Study of {asset} in BCMA disease")
        protocol["armsInterventionsModule"]["interventions"] = [
            {"name": asset, "description": description}
        ]
        result = ClinicalTrialsGovAdapter(lambda **_: [protocol]).search(
            query,
            as_of_date=date(2026, 7, 10),
        )
        assert [hit.asset_name for hit in result.hits] == [asset]


def _pdcd1_query() -> CompiledQuery:
    return CompiledQuery(query_id="q:pdcd1", query="PDCD1", target_ids=["PDCD1"])


def test_other_names_supplies_the_asset_name_when_the_intervention_name_has_none() -> None:
    """Regression: NCT05017012, MK-3475A.

    CT.gov records the product identity in ``otherNames`` when the intervention ``name`` is
    a descriptive label. That field must participate in asset-name extraction.
    """

    protocol = {
        "identificationModule": {"nctId": "NCT05017012", "briefTitle": "SC pembrolizumab"},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Example Bio"}},
        "statusModule": {"lastUpdatePostDateStruct": {"date": "2026-01-01"}},
        "armsInterventionsModule": {
            "interventions": [
                {
                    "name": "Fixed-dose subcutaneous coformulation",
                    "otherNames": ["MK-3475A"],
                    "description": "anti-PD-1 antibody, PDCD1",
                }
            ]
        },
    }
    result = ClinicalTrialsGovAdapter(lambda **_: [protocol]).search(
        _pdcd1_query(), as_of_date=date(2026, 7, 10)
    )
    assert [hit.asset_name for hit in result.hits] == ["MK-3475A"]


def test_other_names_bind_as_aliases_of_the_same_intervention() -> None:
    """Regression: NCT07743632 / "SMT112, AK112" and NCT04673448 / dostarlimab.

    ``otherNames`` is CT.gov asserting the strings denote the same intervention, so they
    bind as aliases. Structural descriptions in the same field must not.
    """

    protocol = {
        "identificationModule": {"nctId": "NCT04673448", "briefTitle": "Dostarlimab study"},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Example Bio"}},
        "statusModule": {"lastUpdatePostDateStruct": {"date": "2026-01-01"}},
        "armsInterventionsModule": {
            "interventions": [
                {
                    "name": "Dostarlimab",
                    "otherNames": [
                        "TSR-042",
                        "Dostarlimab-gxly",
                        "Immunoglobulin G4",
                        "Disulfide with Humanized Clone ABT1 Kappa-chain, Dimer",
                    ],
                    "description": "anti-PD-1 antibody, PDCD1",
                }
            ]
        },
    }
    result = ClinicalTrialsGovAdapter(lambda **_: [protocol]).search(
        _pdcd1_query(), as_of_date=date(2026, 7, 10)
    )
    (hit,) = result.hits
    assert hit.asset_name == "Dostarlimab"
    assert set(hit.aliases) == {"TSR-042", "Dostarlimab-gxly"}


def test_multi_code_other_names_entry_binds_every_code() -> None:
    """Regression: NCT07743632, ``otherNames == ["SMT112, AK112"]``."""

    protocol = {
        "identificationModule": {"nctId": "NCT07743632", "briefTitle": "Ivonescimab study"},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Example Bio"}},
        "statusModule": {"lastUpdatePostDateStruct": {"date": "2026-01-01"}},
        "armsInterventionsModule": {
            "interventions": [
                {
                    "name": "Ivonescimab",
                    "otherNames": ["SMT112, AK112"],
                    "description": "PD-1 x VEGF bispecific, PDCD1",
                }
            ]
        },
    }
    result = ClinicalTrialsGovAdapter(lambda **_: [protocol]).search(
        _pdcd1_query(), as_of_date=date(2026, 7, 10)
    )
    (hit,) = result.hits
    assert hit.asset_name == "Ivonescimab"
    assert set(hit.aliases) == {"SMT112", "AK112"}


def test_other_names_do_not_rename_an_intervention_that_already_names_itself() -> None:
    """Regression: NCT04223804. ``name='ABBV-181'`` already is the identity; the fix must
    not let ``otherNames`` displace it, and must not merge unrelated background drugs."""

    protocol = {
        "identificationModule": {"nctId": "NCT04223804", "briefTitle": "ABBV-181 study"},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Example Bio"}},
        "statusModule": {"lastUpdatePostDateStruct": {"date": "2026-01-01"}},
        "armsInterventionsModule": {
            "interventions": [
                {
                    "name": "ABBV-181",
                    "otherNames": ["Budigalimab"],
                    "description": "anti-PD-1 antibody, PDCD1",
                },
                {"name": "Placebo", "description": "Intravenous infusion"},
            ]
        },
    }
    result = ClinicalTrialsGovAdapter(lambda **_: [protocol]).search(
        _pdcd1_query(), as_of_date=date(2026, 7, 10)
    )
    (hit,) = result.hits
    assert hit.asset_name == "ABBV-181"
    assert set(hit.aliases) == {"Budigalimab"}
