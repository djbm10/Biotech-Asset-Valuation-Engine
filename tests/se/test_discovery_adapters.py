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
