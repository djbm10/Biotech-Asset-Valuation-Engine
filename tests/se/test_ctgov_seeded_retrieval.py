"""ctgov_seeded_retrieval_v1: a drug-seeded CT.gov query must search for the drug.

Declared in ``docs/se_policies/ctgov_seeded_retrieval_v1.md`` before the change. A fake
registry stands in for CT.gov: it serves a protocol only when the request's intervention
expression names one of that protocol's intervention names, as the real API does. The
drug names are synthetic; the target is the fixture ontology's CD19.
"""

from __future__ import annotations

import re
from datetime import date

from bve.se.discovery.adapters import ClinicalTrialsGovAdapter, QueryVocabulary
from bve.se.discovery.seeding import SeedProvenance
from bve.se.schemas.contracts import CompiledQuery, SearchOutcome
from bve.se.universe.ctgov import ClinicalTrialsGovProvider

AS_OF = date(2026, 10, 25)


def _protocol(nct: str, *interventions: tuple[str, list[str]], title: str = "", updated="2026-05-01"):
    return {
        "identificationModule": {"nctId": nct, "briefTitle": title or f"Study {nct}"},
        "sponsorCollaboratorsModule": {"leadSponsor": {"name": "Example Bio"}},
        "statusModule": {"lastUpdatePostDateStruct": {"date": updated}},
        "designModule": {"phases": ["PHASE1"]},
        "armsInterventionsModule": {
            "interventions": [
                {"type": "DRUG", "name": name, "otherNames": other} for name, other in interventions
            ],
            "armGroups": [{"type": "EXPERIMENTAL", "label": "Arm A",
                           "interventionNames": [f"Drug: {n}" for n, _ in interventions]}],
        },
    }


#: A registry: two trials name the target in the title, the rest only name the drug.
REGISTRY = [
    _protocol("NCT00000001", ("Targetumab", []), title="CD19-directed Targetumab"),
    _protocol("NCT00000002", ("ABC-123", []), ("Gemcitabine", [])),
    _protocol("NCT00000003", ("ABC-123", []), ("XYZ-9", [])),  # overlap: both seeded drugs
    _protocol("NCT00000004", ("XYZ-9", ["OLD-77"])),
    _protocol("NCT00000005", ("OLD-77", [])),  # names only the historical code
    _protocol("NCT00000006", ("ABC-123", []), updated="2027-01-01"),  # after the as-of date
    _protocol("NCT00000007", ("Unrelatinib", []), title="CD19 study of Unrelatinib"),
]


class FakeRegistry:
    def __init__(self, protocols=REGISTRY):
        self.protocols = protocols
        self.expressions: list[str] = []

    def __call__(self, *, intervention: str = "", **_):
        self.expressions.append(intervention)
        wanted = {t.casefold() for t in re.findall(r'"([^"]+)"', intervention)}

        def names(p):
            ivs = p["armsInterventionsModule"]["interventions"]
            found = {iv["name"].casefold() for iv in ivs}
            found |= {o.casefold() for iv in ivs for o in iv["otherNames"]}
            return found

        def matches(p):
            title = (p["identificationModule"]["briefTitle"] + " "
                     + (p.get("descriptionModule") or {}).get("briefSummary", "")).casefold()
            return bool(names(p) & wanted) or any(w in title for w in wanted)

        return [p for p in self.protocols if matches(p)]


def _adapter(registry: FakeRegistry) -> ClinicalTrialsGovAdapter:
    return ClinicalTrialsGovAdapter(provider=ClinicalTrialsGovProvider(search_fn=registry))


def _seeded(*names: str) -> CompiledQuery:
    return CompiledQuery(
        query_id=f"query:{names[0]}", query="(" + " OR ".join(f'"{n}"' for n in names) + ")",
        target_ids=["CD19"], modality_ids=[], aliases=list(names),
        seed_provenance=SeedProvenance.AUTHORITY_SEEDED_ASSET, seed_drug_id=f"DRUG:{names[0]}",
    )


def _target_query() -> CompiledQuery:
    return CompiledQuery(query_id="query:target", query='("CD19")', target_ids=["CD19"],
                         modality_ids=[], aliases=["CD19"])


def _trials(result) -> set[str]:
    return {h.trial_id for h in result.hits}


class TestRequestTerms:
    def test_t0_seeded_query_searches_the_drug_not_the_target(self, se_ontology_snapshot) -> None:
        facets = QueryVocabulary.for_query(_seeded("ABC-123", "abc123")).query_facets()
        flat = {t.casefold() for facet in facets for t in facet}
        assert {"abc-123", "abc123"} <= flat
        assert "cd19" not in flat

    def test_t0_follow_up_searches_its_lead(self, se_ontology_snapshot) -> None:
        follow = CompiledQuery(query_id="query:f", query="XYZ-9", target_ids=["CD19"],
                               modality_ids=[], aliases=["XYZ-9"], expansion_depth=1)
        flat = {t.casefold() for f in QueryVocabulary.for_query(follow).query_facets() for t in f}
        assert flat == {"xyz-9"}

    def test_t9_target_query_is_unchanged(self, se_ontology_snapshot) -> None:
        flat = {t for f in QueryVocabulary.for_query(_target_query()).query_facets() for t in f}
        assert "CD19" in flat


class TestRetrieval:
    def test_t1_different_drugs_send_different_requests_and_get_different_trials(
        self, se_ontology_snapshot
    ) -> None:
        registry = FakeRegistry()
        adapter = _adapter(registry)
        a = adapter.search(_seeded("ABC-123"), as_of_date=AS_OF)
        x = adapter.search(_seeded("XYZ-9", "OLD-77"), as_of_date=AS_OF)
        assert registry.expressions[0] != registry.expressions[1]
        assert _trials(a) == {"NCT00000002", "NCT00000003"}
        assert _trials(x) == {"NCT00000003", "NCT00000004", "NCT00000005"}

    def test_t2_historical_alias_retrieves_a_trial_naming_only_it(self, se_ontology_snapshot) -> None:
        result = _adapter(FakeRegistry()).search(_seeded("XYZ-9", "OLD-77"), as_of_date=AS_OF)
        assert ("NCT00000005", "OLD-77") in {(h.trial_id, h.asset_name) for h in result.hits}

    def test_t3_overlapping_trial_is_materialized_once_and_nominated_per_drug(
        self, se_ontology_snapshot
    ) -> None:
        adapter = _adapter(FakeRegistry())
        a = adapter.search(_seeded("ABC-123"), as_of_date=AS_OF)
        x = adapter.search(_seeded("XYZ-9"), as_of_date=AS_OF)
        shared_a = {h.asset_name for h in a.hits if h.trial_id == "NCT00000003"}
        shared_x = {h.asset_name for h in x.hits if h.trial_id == "NCT00000003"}
        assert shared_a == {"ABC-123"} and shared_x == {"XYZ-9"}
        snaps = {m.snapshot_id for r in (a, x) for m in r.materializations if m.record_id == "NCT00000003"}
        assert len(snaps) == 1

    def test_t4_empty_result_is_no_evidence_not_failure(self, se_ontology_snapshot) -> None:
        result = _adapter(FakeRegistry()).search(_seeded("NOPE-1"), as_of_date=AS_OF)
        assert result.outcome is SearchOutcome.NO_EVIDENCE_FOUND
        assert result.hits == []

    def test_t5_partner_and_unrelated_interventions_are_not_the_seeded_drug(
        self, se_ontology_snapshot
    ) -> None:
        result = _adapter(FakeRegistry()).search(_seeded("ABC-123"), as_of_date=AS_OF)
        assert "Gemcitabine" not in {h.asset_name for h in result.hits}
        assert all(h.asset_name == "ABC-123" for h in result.hits)

    def test_t7_as_of_cutoff_still_withholds_later_records(self, se_ontology_snapshot) -> None:
        adapter = _adapter(FakeRegistry())
        result = adapter.search(_seeded("ABC-123"), as_of_date=AS_OF)
        assert "NCT00000006" not in _trials(result)
        assert any(
            (p.get("identificationModule") or {}).get("nctId") == "NCT00000006"
            for p in adapter.withheld_payloads
        )

    def test_target_query_still_reaches_target_named_trials(self, se_ontology_snapshot) -> None:
        result = _adapter(FakeRegistry()).search(_target_query(), as_of_date=AS_OF)
        assert {"NCT00000001", "NCT00000007"} <= {h.trial_id for h in result.hits} | {
            m.record_id for m in result.materializations}


class TestRetrievalEstablishesNothing:
    def test_t6_seeded_hits_carry_context_not_target_assertions(self, se_ontology_snapshot) -> None:
        """The seed's target appears only as discovery context on the hit."""

        from bve.se.resolution.registry import AssetRegistry

        result = _adapter(FakeRegistry()).search(_seeded("ABC-123"), as_of_date=AS_OF)
        registry = AssetRegistry()
        for hit in result.hits:
            registry.ingest_hit(hit)
        [asset] = [a for a in registry.assets.values() if a.canonical_name == "ABC-123"]
        # The seed's target is recorded as where the asset was found, nothing more. The
        # fixture authority has no edge for this synthetic drug, so no assertion exists.
        assert "CD19" in {t.removeprefix("TARGET:") for t in asset.discovery_target_context}
        assert asset.target_assertions == []
        assert asset.target_ids == []


class TestAmendment1:
    def test_t5b_single_arm_trial_mentioning_the_seed_does_not_nominate_its_intervention(
        self, se_ontology_snapshot
    ) -> None:
        """A device or another drug in a trial that only *mentions* the seeded drug."""

        protocol = _protocol("NCT00000009", ("PrepDevice-1", []), title="Bowel prep study")
        protocol["descriptionModule"] = {"briefSummary": "Patients previously failed ABC-123."}
        result = _adapter(FakeRegistry([protocol])).search(
            _seeded("ABC-123"), as_of_date=AS_OF
        )
        assert {m.record_id for m in result.materializations} == {"NCT00000009"}  # retrieved
        assert result.hits == []  # but nothing nominated for the seed

    def test_t5b_the_named_intervention_is_still_nominated(self, se_ontology_snapshot) -> None:
        protocol = _protocol("NCT00000010", ("ABC-123", []), title="A study")
        result = _adapter(FakeRegistry([protocol])).search(_seeded("ABC-123"), as_of_date=AS_OF)
        assert [h.asset_name for h in result.hits] == ["ABC-123"]
