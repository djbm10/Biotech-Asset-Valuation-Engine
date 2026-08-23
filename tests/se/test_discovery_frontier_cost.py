"""M9E1c: the discovery loop must not re-materialize the corpus per query.

Removing the 250-record cap was correct, but it exposed a quadratic: every trial the
sweep retrieves contributes its NCT id and intervention name back to the query frontier,
and every frontier query then re-serialized, re-hashed and re-stat'd every protocol in
the corpus *before* deciding whether the protocol was relevant. On 2,908 trials that
saturated the 5,000-query cap and burned 5h26m of CPU without producing a scoreable run.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from bve.se.discovery.adapters import ClinicalTrialsGovAdapter
from bve.se.schemas.contracts import CompiledQuery


def _protocol(nct: str, intervention: str) -> dict:
    return {
        "identificationModule": {"nctId": nct, "briefTitle": f"study {nct}"},
        "armsInterventionsModule": {
            "interventions": [{"name": intervention, "type": "DRUG"}]
        },
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Acme Bio"}},
        "statusModule": {"overallStatus": "RECRUITING"},
        "conditionsModule": {"conditions": ["melanoma"]},
    }


def _adapter(protocols: list[dict], monkeypatch, tmp_path) -> ClinicalTrialsGovAdapter:
    adapter = ClinicalTrialsGovAdapter(snapshot_root=tmp_path)
    monkeypatch.setattr(
        ClinicalTrialsGovAdapter, "_acquire", lambda self, v, q, d: list(protocols)
    )
    return adapter


def _query(depth: int = 0, text: str = "PDCD1") -> CompiledQuery:
    return CompiledQuery(
        query_id="q1",
        query=text,
        target_ids=[],
        modality_ids=[],
        aliases=[text],
        expansion_depth=depth,
    )


class TestRetrievedTrialsAreNotDiscoveryLeads:
    def test_an_nct_id_already_in_the_corpus_is_not_queued_as_a_query(
        self, monkeypatch, tmp_path
    ):
        """An NCT id you just retrieved cannot discover anything you do not have.

        Re-searching it returns the same trial, so it costs a full corpus pass to
        rediscover a record already held. With 2,908 trials that is 2,908 of the
        5,000 permitted queries spent on guaranteed-zero yield.
        """
        protocols = [_protocol(f"NCT{i:08d}", f"drug-{i}") for i in range(5)]
        adapter = _adapter(protocols, monkeypatch, tmp_path)

        result = adapter.search(_query(), as_of_date=date(2026, 8, 22))

        queued = set(result.follow_up_queries)
        assert not {q for q in queued if q.startswith("NCT")}, (
            f"retrieved NCT ids were queued as discovery queries: {sorted(queued)}"
        )

    def test_intervention_names_are_still_leads(self, monkeypatch, tmp_path):
        # The useful half of expansion must survive: a drug name seen in one trial
        # can find trials the target/modality query did not reach.
        protocols = [_protocol("NCT00000001", "pembrolizumab")]
        adapter = _adapter(protocols, monkeypatch, tmp_path)

        result = adapter.search(_query(), as_of_date=date(2026, 8, 22))

        assert "pembrolizumab" in set(result.follow_up_queries)


class TestTheCorpusIsMaterializedOncePerRun:
    """Preserve every payload examined -- but compute it once, not once per query.

    Narrowing the snapshot set to matched protocols would be cheaper and wrong:
    ``snapshot_ids`` is the record of what the run examined, not of what it liked.
    The redundancy to remove is re-serializing and re-hashing the *same* protocol
    on every query that retrieves it.
    """

    def test_the_same_protocol_is_written_once_across_queries(
        self, monkeypatch, tmp_path
    ):
        protocols = [_protocol(f"NCT{i:08d}", f"drug-{i}") for i in range(5)]
        adapter = _adapter(protocols, monkeypatch, tmp_path)

        first = adapter.search(_query(text="PDCD1"), as_of_date=date(2026, 8, 22))
        writes_after_first = len(list(tmp_path.glob("*.json")))
        second = adapter.search(_query(text="CD279"), as_of_date=date(2026, 8, 22))

        assert len(list(tmp_path.glob("*.json"))) == writes_after_first == 5
        assert first.snapshot_ids == second.snapshot_ids, (
            "the evidence record must not depend on which query retrieved the trial"
        )

    def test_serialization_work_does_not_repeat_per_query(
        self, monkeypatch, tmp_path
    ):
        protocols = [_protocol(f"NCT{i:08d}", f"drug-{i}") for i in range(5)]
        adapter = _adapter(protocols, monkeypatch, tmp_path)

        import bve.se.discovery.adapters as mod

        calls = {"n": 0}
        real = mod.json.dumps

        def counting(*a, **k):
            calls["n"] += 1
            return real(*a, **k)

        monkeypatch.setattr(mod.json, "dumps", counting)

        adapter.search(_query(text="PDCD1"), as_of_date=date(2026, 8, 22))
        after_first = calls["n"]
        adapter.search(_query(text="CD279"), as_of_date=date(2026, 8, 22))
        after_second = calls["n"] - after_first

        assert after_second == 0, (
            f"re-serialized the corpus on the second query ({after_second} json.dumps "
            "calls); this is the quadratic that burned 5h26m of CPU"
        )
