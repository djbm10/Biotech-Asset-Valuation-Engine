import json
from datetime import datetime, timezone

import pytest

from bve.cli.replay_document import _build_parser, _extract_science_evidence_output
from bve.intelligence.extraction.llm_client import FakeLLMClient
from bve.intelligence.extraction.raw_document import EntityHints, RawDocument


def _doc() -> RawDocument:
    return RawDocument(
        id="doc-1",
        source="press_release",
        source_url="https://example.com/doc-1",
        title="Clinical update",
        raw_text="Phase 2 patients showed dose-dependent target engagement.",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        retrieved_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        entity_hints=EntityHints(
            asset_id="asset-1",
            company_id="company-1",
            drug_name="Asset 1",
            indication="ulcerative colitis",
        ),
        document_hash="a" * 64,
    )


def _client(payload: dict | str) -> FakeLLMClient:
    response = payload if isinstance(payload, str) else json.dumps(payload)
    return FakeLLMClient(default_response=response)


def _valid_payload(**item_overrides) -> dict:
    item = {
        "evidence_id": "ev-1",
        "quote": "Phase 2 patients showed dose-dependent target engagement.",
        "mapped_component": "D",
        "mapped_field": "target_engagement",
        "direction": "supportive",
        "confidence": 0.82,
    }
    item.update(item_overrides)
    return {"items": [item], "bundle_warnings": [], "unresolved_gaps": []}


def test_extract_science_evidence_flag_off_parser_default_unchanged() -> None:
    args = _build_parser().parse_args(["--db", "x.db", "--document-id", "doc-1"])

    assert args.extract_science_evidence is False
    assert args.science_thesis is False


def test_extract_science_evidence_flag_on_creates_bundle() -> None:
    output = _extract_science_evidence_output(_doc(), _client(_valid_payload()))

    bundle = output["science_evidence_bundle"]
    assert len(bundle["items"]) == 1
    assert bundle["items"][0]["mapped_component"] == "D"
    assert "science_thesis_summary" not in output


def test_invalid_llm_output_preserves_warning() -> None:
    output = _extract_science_evidence_output(_doc(), _client("not json"))

    assert output["science_evidence_bundle"]["items"] == []
    assert "llm_evidence_invalid_json" in output["science_evidence_warnings"]


def test_missing_quote_or_source_rejects_item() -> None:
    output = _extract_science_evidence_output(
        _doc(),
        _client(_valid_payload(quote=None, text_span=None)),
    )

    assert output["science_evidence_bundle"]["items"] == []
    assert "llm_evidence_missing_quote_or_span" in output["science_evidence_warnings"]


def test_bundle_feeds_thesis_only_when_science_thesis_enabled() -> None:
    without_thesis = _extract_science_evidence_output(_doc(), _client(_valid_payload()))
    with_thesis = _extract_science_evidence_output(
        _doc(),
        _client(_valid_payload()),
        include_science_thesis=True,
    )

    assert "science_thesis_summary" not in without_thesis
    assert with_thesis["science_thesis_summary"]["science_binding_question"]
    assert with_thesis["science_thesis_summary"]["science_modifier_applied"] is False


def test_no_pos_change_without_apply_science_pos_modifier() -> None:
    output = _extract_science_evidence_output(
        _doc(),
        _client(_valid_payload()),
        include_science_thesis=True,
    )

    assert output["science_thesis_summary"]["science_modifier_applied"] is False
    assert "pos" not in output
    assert "bd_summary" not in output


def test_llm_output_does_not_create_bd_actionability() -> None:
    output = _extract_science_evidence_output(
        _doc(),
        _client(
            {
                "bd_actionability": {"bd_route": "acquisition"},
                "items": [_valid_payload()["items"][0]],
                "bundle_warnings": [],
                "unresolved_gaps": [],
            }
        ),
    )

    assert "bd_actionability" not in output["science_evidence_bundle"]
    assert "bd_summary" not in output
    assert "llm_output_contained_forbidden_scoring_fields" in output["science_evidence_warnings"]


def test_science_thesis_flag_requires_extract_science_evidence(monkeypatch) -> None:
    from bve.cli import replay_document

    monkeypatch.setattr(
        "sys.argv",
        ["bve-replay-document", "--db", "x.db", "--document-id", "doc-1", "--science-thesis"],
    )
    with pytest.raises(SystemExit) as exc:
        replay_document.main()
    assert exc.value.code == 2
