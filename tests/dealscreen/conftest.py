"""Shared fixtures: synthetic data in a temp dir, offline target map, no ontology load."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from bve.dealscreen.synthetic import generate

EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "dealscreen"


@pytest.fixture(autouse=True)
def _no_ontology(monkeypatch, tmp_path_factory):
    """The gate engine resolves target ids through the S&E ontology when one is installed.

    Tests point it at an empty location so they never load the 1.6 GB snapshot; the offline
    target map below supplies the same symbols the ontology resolves for this landscape.
    """
    from bve.se.ontology.targets import reset_resolver_cache

    monkeypatch.setenv("BVE_SE_ONTOLOGY_SNAPSHOT", str(tmp_path_factory.mktemp("none") / "absent"))
    reset_resolver_cache()
    yield
    reset_resolver_cache()


@pytest.fixture(scope="session")
def demo_dir(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("dealscreen_demo")
    generate(out)
    for name in ("profile_synthetic_vendor.yaml", "buyer_tl1a_ibd.yaml", "target_map.yaml"):
        shutil.copyfile(EXAMPLES / name, out / name)
    return out


@pytest.fixture(scope="session")
def target_map(demo_dir) -> dict[str, str]:
    data = yaml.safe_load((demo_dir / "target_map.yaml").read_text())
    return {str(k).casefold(): v for k, v in data.items()}


@pytest.fixture(scope="session")
def normalizer(target_map):
    return lambda text: target_map.get(text.strip().casefold())
