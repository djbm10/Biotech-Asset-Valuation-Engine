from __future__ import annotations

from datetime import datetime, timezone

from bve.cli.data_quality_report import main
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.ops.data_quality import DataQualityScore


def test_data_quality_cli_gated_only_filters_rows(tmp_path, monkeypatch, capsys) -> None:
    db_path = tmp_path / "knowledge.db"
    store = KnowledgeStore(db_path)
    try:
        now = datetime.now(timezone.utc)
        store.log_data_quality(
            DataQualityScore(
                asset_id="asset-gated",
                overall_score=0.5,
                checks=[],
                failing_checks=["doc_freshness"],
                gated=True,
                generated_at=now,
            )
        )
        store.log_data_quality(
            DataQualityScore(
                asset_id="asset-ok",
                overall_score=1.0,
                checks=[],
                failing_checks=[],
                gated=False,
                generated_at=now,
            )
        )
    finally:
        store.close()

    monkeypatch.setattr(
        "sys.argv",
        ["bve-data-quality", "--db", str(db_path), "--gated-only"],
    )
    main()
    out = capsys.readouterr().out
    assert "asset-gated" in out
    assert "asset-ok" not in out
