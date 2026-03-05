from pathlib import Path

import yaml

_SETTINGS_PATH = Path(__file__).parent / "settings.yaml"

with open(_SETTINGS_PATH) as _f:
    SETTINGS: dict = yaml.safe_load(_f)


def get(key_path: str, default=None):
    """Dot-notation access into SETTINGS. E.g. get('valuation.default_discount_rate')."""
    keys = key_path.split(".")
    node = SETTINGS
    for k in keys:
        if not isinstance(node, dict):
            return default
        node = node.get(k, default)
    return node
