"""Current scientific compatibility and immutable historical acceptance provenance."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('target_reference_evaluation',
                                             ROOT / 'scripts/evaluate_target_reference_v1.py')
EVALUATION = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVALUATION)


@pytest.fixture(scope='module')
def current_rows():
    return EVALUATION.current_compatibility()


@pytest.mark.parametrize('index', range(103))
def test_current_scientific_compatibility(current_rows, index):
    assert current_rows[index]['matches'], current_rows[index]


def test_original_historical_source_certificates():
    rows = EVALUATION.historical_certificates()
    assert [r['checks'] for r in rows] == [894, 897]
