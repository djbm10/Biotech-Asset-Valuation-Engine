"""Handoff integrity and conservative reference projection, not scientific validation."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "research/se_pilot_handoff_v1" / f"{name}.py"
    )
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def test_payload_roundtrip_and_corruption(tmp_path):
    cloud = module("cloud_payload")
    (tmp_path / "input").write_bytes(b"frozen\n")
    manifest = {"files": cloud.inventory(tmp_path), "code_head": "test"}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    cloud.verify(tmp_path)
    (tmp_path / "input").write_bytes(b"broken\n")
    with pytest.raises(ValueError, match="checksum"):
        cloud.verify(tmp_path)


@pytest.mark.parametrize("name", ["../outside", "/etc/passwd"])
def test_payload_rejects_path_escape(tmp_path, name):
    (tmp_path / "manifest.json").write_text(
        json.dumps({"files": {name: {"sha256": "", "bytes": 0}}, "code_head": "test"})
    )
    with pytest.raises(ValueError, match="unsafe"):
        module("cloud_payload").verify(tmp_path)


def test_reference_projection_preserves_labels_and_uncertainty(tmp_path):
    pilot = module("pilot")
    rows = pilot.build()
    original = json.loads((pilot.STUDY / "reference_frozen.json").read_text())["entries"]
    assert len(rows) == len({r["ref_id"] for r in rows}) == len(original)
    for row, entry in zip(rows, original, strict=True):
        for key, value in entry.items():
            assert row[key] == value
        for field in row["fields"].values():
            assert (field["status"] == "QUOTED_REFERENCE") == bool(field["evidence"])
        assert row["commercial_rights"].startswith("UNKNOWN")
        assert row["human_efficacy"].startswith("UNVERIFIED")
    pilot.main(tmp_path / "one")
    pilot.main(tmp_path / "two")
    for path in (tmp_path / "one").iterdir():
        assert path.read_bytes() == (tmp_path / "two" / path.name).read_bytes()
    with pytest.raises(FileExistsError):
        pilot.main(tmp_path / "one")


def test_payload_covers_nested_manifests_and_rejects_symlinks(tmp_path):
    cloud = module("cloud_payload")
    nested = tmp_path / "custody"
    nested.mkdir()
    (nested / "manifest.json").write_text("sealed bytes")
    assert "custody/manifest.json" in cloud.inventory(tmp_path)
    (tmp_path / "escape").symlink_to("/etc/passwd")
    (tmp_path / "manifest.json").write_text(
        json.dumps({"files": {"escape": {"bytes": 0, "sha256": ""}}, "code_head": "test"})
    )
    with pytest.raises(ValueError, match="escaping symlink"):
        cloud.verify(tmp_path)


def test_cloud_wrapper_refuses_without_authorization():
    import os
    import subprocess

    env = dict(os.environ, BVE_AUTHORIZED_CLOUD="")
    proc = subprocess.run(
        ["bash", str(ROOT / "research/se_pilot_handoff_v1/cloud_execute.sh")],
        check=False,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "authorized cloud execution" in proc.stderr


def test_environment_refuses_different_revision(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"code_head": "wrong", "python": "3.11.17"}))
    with pytest.raises(ValueError, match="code HEAD or Python"):
        module("cloud_payload").environment(tmp_path)


def test_prepare_dereferences_ontology_and_preserves_snapshot_bytes(tmp_path, monkeypatch):
    cloud = module("cloud_payload")
    source = tmp_path / "source"
    repo = tmp_path / "repo"
    source.mkdir()
    for name in cloud.RUN_INPUTS:
        path = source / name
        if name in {"A_base", "corpus_A"}:
            path.mkdir()
            (path / "snapshot.json").write_text('{"path":"/original/absolute/path"}')
        else:
            path.write_text("frozen input")
    (source / "A_full_failed").mkdir()
    (source / "credentials.env").write_text("must not transfer")
    ontology = repo / "data/se/ontology"
    ontology.mkdir(parents=True)
    authority = tmp_path / "authority"
    authority.mkdir()
    (authority / "records.json").write_text("frozen authority")
    (ontology / "current").symlink_to(authority, target_is_directory=True)
    monkeypatch.setattr(cloud, "ROOT", source)
    monkeypatch.setattr(cloud, "REPO", repo)
    monkeypatch.setattr(
        cloud.subprocess,
        "check_output",
        lambda args, **kwargs: "" if "status" in args else "test-head\n",
    )
    monkeypatch.setattr(cloud.importlib.metadata, "distributions", list)
    destination = tmp_path / "payload"
    cloud.prepare(destination)
    assert not (destination / "ontology/current").is_symlink()
    assert (destination / "ontology/current/records.json").read_text() == "frozen authority"
    assert (destination / "runs/A_base/snapshot.json").read_bytes() == (
        source / "A_base/snapshot.json"
    ).read_bytes()
    assert not (destination / "runs/credentials.env").exists()
    assert not (destination / "runs/A_full_failed").exists()
    with pytest.raises(FileExistsError):
        cloud.prepare(destination)
