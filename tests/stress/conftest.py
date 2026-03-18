from __future__ import annotations

from pathlib import Path

import pytest

_STRESS_DIR = Path(__file__).resolve().parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        item_path = Path(str(item.path)).resolve()
        if _STRESS_DIR in item_path.parents:
            item.add_marker(pytest.mark.stress)
