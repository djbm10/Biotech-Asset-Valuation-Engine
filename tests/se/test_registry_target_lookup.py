"""Pinned CT.gov lookup by asset name: ``registry_target_lookup_v1.md``."""

from __future__ import annotations

import json
from datetime import date

import pytest

from bve.se.evidence.registry_target_lookup import (
    EXTRACTION_METHOD,
    MAX_STUDIES_PER_QUERY,
    LiveLookup,
    LookupCustodyError,
    PinnedLookup,
    lookup_eligible,
    name_in_intervention,
    query_names_for,
    registry_target_evidence,
)
from bve.se.schemas.contracts import NormalizedFact

CD19 = "TARGET:CD19"
BCMA = "TARGET:TNFRSF17"
AS_OF = date(2026, 9, 24)


@pytest.fixture(autouse=True)
def _ontology(se_ontology_snapshot):
    return se_ontology_snapshot


def _study(nct: str, *interventions: tuple[str, str]) -> dict:
    return {
        "identificationModule": {"nctId": nct},
        "armsInterventionsModule": {
            "interventions": [
                {"type": "BIOLOGICAL", "name": name, "description": description}
                for name, description in interventions
            ]
        },
    }


class _Source:
    def __init__(self, by_query: dict[str, list[dict] | None]) -> None:
        self.by_query = by_query
        self.asked: list[str] = []

    def studies(self, query: str) -> list[dict] | None:
        self.asked.append(query)
        return self.by_query.get(query, [])


def _evidence(source, names=("ALLO-715",)):
    return registry_target_evidence(
        "asset:1", query_names=list(names), source=source, as_of_date=AS_OF
    )


# L1 / L2 ----------------------------------------------------------------------------------


def _fact(asset_id: str, fact_type: str = "construct_target_set") -> NormalizedFact:
    return NormalizedFact(
        fact_id=f"fact:{asset_id}:{fact_type}",
        subject_id=asset_id,
        fact_type=fact_type,
        value=[CD19],
        supporting_claim_ids=[f"claim:{asset_id}"],
        confidence=0.95,
    )


def test_only_qualified_assets_without_a_target_fact_are_eligible() -> None:
    facts = {"a": [_fact("a")], "b": [_fact("b", "development_status")]}
    assert lookup_eligible(["a", "b", "c"], facts) == ["b", "c"]


def test_query_names_are_the_canonical_name_then_authority_names() -> None:
    assert query_names_for("CT053", ("zevorcabtagene autoleucel", "CT053")) == [
        "CT053",
        "zevorcabtagene autoleucel",
    ]
    assert query_names_for("CNCT19", ()) == ["CNCT19"]


# L3 -------------------------------------------------------------------------------------


def test_name_matches_whole_tokens_only() -> None:
    assert name_in_intervention("ALLO-715", "ALLO-715 CAR T cells")
    assert name_in_intervention("CT053", "Autologous CT053 injection")
    assert not name_in_intervention("CT053", "CT0531")
    assert not name_in_intervention("ALLO-715", "ALLO-7150")
    assert not name_in_intervention("ALLO-715", "Lenalidomide")


def test_an_intervention_that_does_not_name_the_asset_is_not_admitted() -> None:
    source = _Source(
        {
            "ALLO-715": [
                _study(
                    "NCT1",
                    ("Fludarabine", "anti-CD19 lymphodepletion partner"),
                )
            ]
        }
    )
    assert _evidence(source) is None


# L4 / L5 ----------------------------------------------------------------------------------


def test_admitted_intervention_yields_the_reader_target_set() -> None:
    source = _Source(
        {"ALLO-715": [_study("NCT1", ("ALLO-715", "BCMA-directed allogeneic CAR T"))]}
    )
    evidence = _evidence(source)
    assert evidence is not None
    assert evidence.fact.value == [BCMA]
    assert evidence.fact.fact_type == "construct_target_set"
    [claim] = evidence.claims
    assert claim.extraction_method == EXTRACTION_METHOD
    assert "NCT1" in claim.supporting_passage
    assert "ALLO-715" in claim.supporting_passage
    assert evidence.fact.confidence < 0.95


def test_empty_readings_are_ignored_and_agreeing_sets_combine() -> None:
    source = _Source(
        {
            "ALLO-715": [
                _study("NCT1", ("ALLO-715", "allogeneic CAR T")),
                _study("NCT2", ("ALLO-715", "anti-BCMA CAR T")),
                _study("NCT3", ("ALLO-715", "BCMA-directed")),
            ]
        }
    )
    evidence = _evidence(source)
    assert evidence is not None
    assert evidence.fact.value == [BCMA]
    assert len(evidence.claims) == 2


def test_disagreeing_sets_give_no_fact() -> None:
    source = _Source(
        {
            "ALLO-715": [
                _study("NCT1", ("ALLO-715", "anti-BCMA CAR T")),
                _study("NCT2", ("ALLO-715", "anti-CD19 CAR T")),
            ]
        }
    )
    assert _evidence(source) is None


def test_the_reader_is_the_existing_one_so_a_dual_construct_is_one_set() -> None:
    source = _Source(
        {"ALLO-715": [_study("NCT1", ("ALLO-715", "CD19/BCMA-directed CAR T"))]}
    )
    evidence = _evidence(source)
    assert evidence is not None
    assert evidence.fact.value == [CD19, BCMA]


# L6 / L7 ----------------------------------------------------------------------------------


def test_no_studies_gives_no_fact_and_no_placeholder() -> None:
    assert _evidence(_Source({})) is None


def test_a_failed_query_gives_no_fact_even_when_another_name_answers() -> None:
    # Fail closed: a name that could not be read might have disagreed.
    source = _Source(
        {
            "ALLO-715": [_study("NCT1", ("ALLO-715", "anti-BCMA CAR T"))],
            "nendocabtagene onogedleucel": None,
        }
    )
    assert _evidence(source, names=("ALLO-715", "nendocabtagene onogedleucel")) is None


def test_a_study_found_by_two_names_is_read_once() -> None:
    study = _study("NCT1", ("ALLO-715", "anti-BCMA CAR T"))
    source = _Source({"ALLO-715": [study], "nendocabtagene onogedleucel": [study]})
    evidence = _evidence(source, names=("ALLO-715", "nendocabtagene onogedleucel"))
    assert evidence is not None
    assert len(evidence.claims) == 1


def test_live_lookup_keeps_the_lowest_nct_ids_and_pins_them(tmp_path) -> None:
    returned = [_study(f"NCT{n:08d}", ("X-1", "anti-CD19")) for n in range(40, 0, -1)]
    live = LiveLookup(tmp_path, search=lambda name: returned, fetched_at="2026-09-30T00:00:00Z")
    studies = live.studies("X-1")
    ids = [s["identificationModule"]["nctId"] for s in studies]
    assert len(ids) == MAX_STUDIES_PER_QUERY
    assert ids == sorted(ids)
    assert ids[0] == "NCT00000001"

    pinned = PinnedLookup(tmp_path)
    assert pinned.studies("X-1") == studies


def test_live_lookup_records_failure_and_replay_reproduces_it(tmp_path) -> None:
    def boom(name):
        raise TimeoutError("ct.gov")

    live = LiveLookup(tmp_path, search=boom, fetched_at="2026-09-30T00:00:00Z")
    assert live.studies("X-1") is None
    assert PinnedLookup(tmp_path).studies("X-1") is None


def test_replay_of_an_unrecorded_query_is_fatal(tmp_path) -> None:
    LiveLookup(tmp_path, search=lambda name: [], fetched_at="t").studies("X-1")
    with pytest.raises(LookupCustodyError):
        PinnedLookup(tmp_path).studies("Y-2")


def test_replay_of_a_mutated_custody_is_fatal(tmp_path) -> None:
    LiveLookup(tmp_path, search=lambda name: [], fetched_at="t").studies("X-1")
    [record] = (tmp_path / "queries").iterdir()
    payload = json.loads(record.read_text())
    payload["studies"] = [_study("NCT9", ("X-1", "anti-CD19"))]
    record.write_text(json.dumps(payload))
    with pytest.raises(LookupCustodyError):
        PinnedLookup(tmp_path).studies("X-1")


def test_pinned_and_live_evidence_are_identical(tmp_path) -> None:
    returned = [_study("NCT1", ("ALLO-715", "anti-BCMA CAR T"))]
    live = LiveLookup(tmp_path, search=lambda name: returned, fetched_at="2026-09-30T00:00:00Z")
    first = _evidence(live)
    second = _evidence(PinnedLookup(tmp_path))
    assert first is not None and second is not None
    assert first.model_dump() == second.model_dump()


def test_network_exemption_lifts_the_replay_guard_only_while_active() -> None:
    import socket

    from bve.se.discovery.replay import NetworkBlocked, block_network, network_exemption

    real = socket.getaddrinfo
    with block_network():
        with pytest.raises(NetworkBlocked):
            socket.getaddrinfo("localhost", 80)
        with network_exemption():
            assert socket.getaddrinfo is real
        with pytest.raises(NetworkBlocked):
            socket.getaddrinfo("localhost", 80)
    assert socket.getaddrinfo is real
