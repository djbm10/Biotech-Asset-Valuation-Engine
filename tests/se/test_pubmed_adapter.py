from __future__ import annotations

from datetime import date

from bve.se.discovery.adapters import PubMedDiscoveryAdapter, UnavailableSourceAdapter
from bve.se.schemas.contracts import CompiledQuery, SearchOutcome


def test_pubmed_adapter_normalizes_matching_abstract_and_snapshot(tmp_path) -> None:
    adapter = PubMedDiscoveryAdapter(
        lambda query, limit: [
            {
                "pmid": "12345",
                "title": "A phase 1 study of CLN-978 CD19 T-cell engager",
                "abstract": "A CD19 x CD3 bispecific T-cell engager was evaluated.",
                "publication_date": "2026",
            }
        ],
        snapshot_root=tmp_path / "snapshots",
    )
    result = adapter.search(
        CompiledQuery(
            query_id="q",
            query="CD19 T-cell engager",
            target_ids=["CD19"],
            modality_ids=["T_CELL_ENGAGER"],
        ),
        as_of_date=date(2026, 7, 10),
    )
    assert result.outcome == SearchOutcome.SUCCESS
    assert result.hits[0].asset_name == "CLN-978"
    assert result.source_documents[0].source_url.endswith("/12345/")
    assert result.source_documents[0].snapshot_path


def test_pubmed_adapter_does_not_turn_nonmatching_abstract_into_candidate() -> None:
    adapter = PubMedDiscoveryAdapter(
        lambda query, limit: [
            {"pmid": "1", "title": "BCMA antibody", "abstract": "An ADC study."}
        ]
    )
    result = adapter.search(
        CompiledQuery(query_id="q", query="CD19", target_ids=["CD19"], modality_ids=["T_CELL_ENGAGER"]),
        as_of_date=date(2026, 7, 10),
    )
    assert result.hits == []


def _abstract_adapter(title: str, abstract: str) -> PubMedDiscoveryAdapter:
    return PubMedDiscoveryAdapter(
        lambda query, limit: [
            {"pmid": "9", "title": title, "abstract": abstract, "publication_date": "2026"}
        ]
    )


def test_pubmed_admits_a_target_named_by_alias_under_a_prefixed_canonical_id() -> None:
    """A canonical id is an identifier, not a string that appears in prose.

    The adapter used to gate document intake on ``target.casefold() in text`` over
    ``query.target_ids``. That only ever worked for targets whose bare gene symbol is
    unambiguous enough to be usable as the canonical id itself. As soon as a symbol is
    contested -- HRH1 is claimed by DHX8, PD-1 by RPL17 -- the canonical id has to carry
    its ``TARGET:`` prefix, and no abstract ever written contains the literal text
    ``target:hrh1``. Every PubMed record for such a target was silently discarded: in the
    M15 HRH1 run, 4833 of 4833.

    The target is named here the way literature actually names it, and nothing about the
    phrasing is HRH1-specific.
    """

    adapter = _abstract_adapter(
        "EXM-101, a histamine H1 receptor antagonist",
        "EXM-101 was evaluated against the histamine H1 receptor in healthy volunteers.",
    )
    result = adapter.search(
        CompiledQuery(
            query_id="q",
            query="histamine H1 receptor",
            target_ids=["TARGET:HRH1"],
            aliases=["histamine H1 receptor"],
        ),
        as_of_date=date(2026, 7, 10),
    )
    assert result.source_documents, "abstract naming the target by an alias produced no document"
    assert "EXM-101" in {hit.asset_name for hit in result.hits}


def test_pubmed_admits_a_different_target_by_the_same_rule() -> None:
    """Target-agnostic: the rule is about the vocabulary, not about which target it is."""

    adapter = _abstract_adapter(
        "ABC-222 and the norepinephrine transporter",
        "ABC-222 inhibits the norepinephrine transporter.",
    )
    result = adapter.search(
        CompiledQuery(
            query_id="q",
            query="norepinephrine transporter",
            target_ids=["TARGET:SLC6A2"],
            aliases=["norepinephrine transporter"],
        ),
        as_of_date=date(2026, 7, 10),
    )
    assert result.source_documents
    assert "ABC-222" in {hit.asset_name for hit in result.hits}


def test_pubmed_still_rejects_an_abstract_that_names_no_target_term() -> None:
    """The gate is widened to the target's vocabulary, not removed.

    Co-occurrence is never identity (M11) and relevance is not identity either, but an
    abstract that does not mention the target in any of its names is not evidence about
    the target at all and must not become a document.
    """

    adapter = _abstract_adapter(
        "ABC-222 in advanced solid tumours",
        "ABC-222 was administered to 30 patients. No receptor pharmacology is reported.",
    )
    result = adapter.search(
        CompiledQuery(
            query_id="q",
            query="histamine H1 receptor",
            target_ids=["TARGET:HRH1"],
            aliases=["histamine H1 receptor"],
        ),
        as_of_date=date(2026, 7, 10),
    )
    assert result.source_documents == []
    assert result.hits == []


def test_unavailable_source_is_explicitly_not_configured() -> None:
    """Not FAILED: nothing was attempted, so nothing broke.

    The distinction is load-bearing. While these were the same outcome, seven unbuilt
    connectors made run B6 unscoreable even though its CT.gov acquisition was clean.
    """

    result = UnavailableSourceAdapter("conference_ash").search(
        CompiledQuery(query_id="q", query="CD19"), as_of_date=date(2026, 7, 10)
    )
    assert result.outcome == SearchOutcome.NOT_CONFIGURED
    assert result.error == "connector not configured"
