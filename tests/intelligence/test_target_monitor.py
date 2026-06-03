from __future__ import annotations

from pathlib import Path

import yaml

from bve.intelligence.target_monitor import TargetMonitorLoader


def test_target_monitor_loader_parses_yaml(tmp_path: Path):
    path = tmp_path / "target_monitor.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "as_of_date": "2026-03-22",
                "targets": [
                    {
                        "company_name": "Tango Therapeutics",
                        "ticker": "TNGX",
                        "status": "independent_public_target",
                        "therapeutic_area": "oncology",
                        "lead_assets": "TNG462 / TNG456 / TNG348",
                        "stage": "phase_1 / phase_2",
                        "source_url": "https://example.com/tngx",
                        "notes": "Independent public target.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    dataset = TargetMonitorLoader.load(path)

    assert dataset.as_of_date.isoformat() == "2026-03-22"
    assert len(dataset.targets) == 1
    assert dataset.targets[0].ticker == "TNGX"
