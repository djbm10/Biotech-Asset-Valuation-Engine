import pytest
from pydantic import ValidationError

from bve.se.acquisition.source_health import (
    SourceHealth,
    SourceHealthReport,
    SourceVerdict,
)


def _health(**updates) -> SourceHealth:
    values = {
        "source_family": "registry",
        "connector_succeeded": True,
        "query_returned_results": True,
        "raw_record_count": 2,
        "documents_parsed": 2,
        "documents_indexed": 2,
    }
    values.update(updates)
    return SourceHealth(**values)


def test_verdict_distinguishes_no_data_degraded_and_failed() -> None:
    assert _health().verdict is SourceVerdict.OK
    assert _health(
        query_returned_results=False,
        raw_record_count=0,
        documents_parsed=0,
        documents_indexed=0,
    ).verdict is SourceVerdict.NO_DATA
    assert _health(parse_failures=1, documents_parsed=1, documents_indexed=1).verdict is (
        SourceVerdict.DEGRADED
    )
    assert _health(connector_succeeded=False).verdict is SourceVerdict.FAILED
    assert _health(parse_failures=2, documents_parsed=0, documents_indexed=0).verdict is (
        SourceVerdict.FAILED
    )


def test_required_production_health_fails_closed_but_accepts_no_data() -> None:
    report = SourceHealthReport(
        sources=[
            _health(source_family="ok"),
            _health(
                source_family="empty",
                query_returned_results=False,
                raw_record_count=0,
                documents_parsed=0,
                documents_indexed=0,
            ),
            _health(
                source_family="partial",
                parse_failures=1,
                documents_parsed=1,
                documents_indexed=1,
            ),
        ]
    )

    assert report.production_failures({"ok", "empty"}) == []
    assert report.production_failures({"ok", "empty", "partial", "missing"}) == [
        "required source not configured: missing",
        "required source partial is DEGRADED",
    ]


@pytest.mark.parametrize(
    "field",
    [
        "raw_record_count",
        "documents_parsed",
        "documents_indexed",
        "parse_failures",
    ],
)
def test_health_counts_must_be_nonnegative(field: str) -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        _health(**{field: -1})


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        (
            {"raw_record_count": 0},
            "query_returned_results requires at least one raw record",
        ),
        (
            {"raw_record_count": 2, "documents_parsed": 2, "parse_failures": 1},
            "documents_parsed plus parse_failures cannot exceed raw_record_count",
        ),
        (
            {"documents_parsed": 1, "documents_indexed": 2},
            "documents_indexed cannot exceed documents_parsed",
        ),
    ],
)
def test_health_stage_counts_must_be_consistent(
    updates: dict[str, int],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        _health(**updates)
