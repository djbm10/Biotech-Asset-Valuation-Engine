"""Snapshot builder: bulk parsing, paged fetching, and version pinning."""

from __future__ import annotations

import json
from datetime import date
from io import BytesIO

import pytest

from bve.se.ontology.build import build_open_targets_records, build_snapshot, fetch_chembl_records
from bve.se.ontology.resolver import BiomedicalEntityResolver

OPEN_TARGETS_ROWS = [
    {
        "id": "ENSG00000188389",
        "approvedSymbol": "PDCD1",
        "approvedName": "programmed cell death 1",
        "proteinIds": [{"id": "Q15116", "source": "uniprot_swissprot"}],
        "synonyms": [{"label": "PD-1"}, {"label": "CD279"}],
    },
    {
        "id": "ENSG00000133703",
        "approvedSymbol": "KRAS",
        "approvedName": "KRAS proto-oncogene, GTPase",
        "proteinIds": [{"id": "P01116", "source": "uniprot_swissprot"}],
        "synonyms": [{"label": "K-RAS"}],
    },
]


def _write_shard(directory, rows, name="targets.jsonl"):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text("\n".join(json.dumps(row) for row in rows) + "\n")
    return directory


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._buffer = BytesIO(json.dumps(payload).encode())

    def read(self) -> bytes:
        return self._buffer.read()

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _paging_opener(pages: list[dict]):
    calls: list[int] = []

    def opener(request):
        index = len(calls)
        calls.append(index)
        return _FakeResponse(pages[index])

    opener.calls = calls  # type: ignore[attr-defined]
    return opener


class TestOpenTargetsBulk:
    def test_parses_every_shard(self, tmp_path) -> None:
        _write_shard(tmp_path / "ot", OPEN_TARGETS_ROWS)
        records, digest, files = build_open_targets_records(tmp_path / "ot")
        assert {record.canonical_symbol for record in records} == {"PDCD1", "KRAS"}
        assert digest
        # Every shard read is hashed, so the snapshot can name the bytes it came from.
        assert [file.rows for file in files] == [2]

    def test_digest_is_stable_across_rebuilds(self, tmp_path) -> None:
        _write_shard(tmp_path / "a", OPEN_TARGETS_ROWS)
        _write_shard(tmp_path / "b", OPEN_TARGETS_ROWS)
        assert build_open_targets_records(tmp_path / "a")[1] == build_open_targets_records(tmp_path / "b")[1]

    def test_missing_export_is_an_explicit_error(self, tmp_path) -> None:
        (tmp_path / "empty").mkdir()
        with pytest.raises(FileNotFoundError, match="no bulk shards found"):
            build_open_targets_records(tmp_path / "empty")


class TestChemblPaging:
    def test_follows_pages_until_exhausted(self) -> None:
        opener = _paging_opener(
            [
                {
                    "targets": [
                        {
                            "target_chembl_id": "CHEMBL1",
                            "target_type": "SINGLE PROTEIN",
                            "target_components": [{"accession": "Q1", "target_component_synonyms": []}],
                        }
                    ],
                    "page_meta": {"next": "/next"},
                },
                {
                    "targets": [
                        {
                            "target_chembl_id": "CHEMBL2",
                            "target_type": "SINGLE PROTEIN",
                            "target_components": [{"accession": "Q2", "target_component_synonyms": []}],
                        }
                    ],
                    "page_meta": {"next": None},
                },
            ]
        )
        records, _ = fetch_chembl_records(limit=1, opener=opener)
        assert [record.source_id for record in records] == ["CHEMBL1", "CHEMBL2"]
        assert len(opener.calls) == 2  # type: ignore[attr-defined]

    def test_max_records_stops_early(self) -> None:
        opener = _paging_opener(
            [
                {
                    "targets": [
                        {"target_chembl_id": f"CHEMBL{index}", "target_type": "SINGLE PROTEIN"}
                        for index in range(5)
                    ],
                    "page_meta": {"next": "/next"},
                }
            ]
        )
        records, _ = fetch_chembl_records(limit=5, max_records=2, opener=opener)
        assert len(records) == 2


class TestSnapshotAssembly:
    def test_release_is_required_to_pin_the_version(self, tmp_path) -> None:
        _write_shard(tmp_path / "ot", OPEN_TARGETS_ROWS)
        with pytest.raises(ValueError, match="open_targets_release is required"):
            build_snapshot(open_targets_dir=tmp_path / "ot")

    def test_no_source_enabled_is_an_error(self) -> None:
        with pytest.raises(ValueError, match="at least one source"):
            build_snapshot()

    def test_built_snapshot_resolves_and_records_counts(self, tmp_path) -> None:
        _write_shard(tmp_path / "ot", OPEN_TARGETS_ROWS)
        snapshot, _ = build_snapshot(
            open_targets_dir=tmp_path / "ot",
            open_targets_release="26.06",
            retrieved_at=date(2026, 8, 15),
        )
        assert snapshot.ontology_version == "open_targets_26.06__resolver_v1"
        assert snapshot.sources[0].record_count == 2

        resolver = BiomedicalEntityResolver(snapshot)
        assert resolver.resolve("CD279").canonical_id == "TARGET:PDCD1"
        assert resolver.resolve("K-RAS").canonical_id == "TARGET:KRAS"

    def test_two_sources_produce_a_combined_version(self, tmp_path) -> None:
        _write_shard(tmp_path / "ot", OPEN_TARGETS_ROWS)
        opener = _paging_opener(
            [
                {
                    "targets": [
                        {
                            "target_chembl_id": "CHEMBL3307223",
                            "pref_name": "Programmed cell death protein 1",
                            "target_type": "SINGLE PROTEIN",
                            "target_components": [
                                {
                                    "accession": "Q15116",
                                    "target_component_synonyms": [
                                        {"component_synonym": "PDCD1", "syn_type": "GENE_SYMBOL"}
                                    ],
                                }
                            ],
                        }
                    ],
                    "page_meta": {"next": None},
                }
            ]
        )
        snapshot, _ = build_snapshot(
            open_targets_dir=tmp_path / "ot",
            open_targets_release="26.06",
            chembl_release="36",
            opener=opener,
            retrieved_at=date(2026, 8, 15),
            verify_release=False,
        )
        assert snapshot.ontology_version == "chembl_36__open_targets_26.06__resolver_v1"
        # The ChEMBL row joins the Open Targets row on Q15116 rather than adding an entity.
        assert len(BiomedicalEntityResolver(snapshot).entities()) == 2
