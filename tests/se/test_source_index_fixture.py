from pathlib import Path

import yaml


def test_source_index_fixture_declares_all_non_ctgov_mandatory_families() -> None:
    root = Path(__file__).resolve().parents[2]
    index = yaml.safe_load((root / "examples/configs/se/source_index_fixture.yaml").read_text())
    assert set(index) == {
        "company_pipeline_or_presentation",
        "company_press_release",
        "sec_edgar",
        "conference_ash",
        "conference_asco",
        "conference_aacr",
        "conference_eha",
    }
