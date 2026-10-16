"""Streaming writes are byte-identical to the whole-string writes they replace.

The custody seal and ``result.json`` used to build each file as one Python string before
writing it; at production scale that was a ~0.6 GB attempts string (plus every line, plus
the encoded bytes) and a ~0.4 GB result string. Streaming changes memory, never bytes: these
tests pin the exact output, and the seal's own recorded hashes, against the old encoding.
"""

from __future__ import annotations

import json
from pathlib import Path

from bve.se.discovery.custody import (
    ACQUISITION_LEDGER_FILE,
    QUERY_ATTEMPTS_FILE,
    QUERY_RECORD_MAP_FILE,
    _canonical_line,
    validate_seal,
)
from bve.se.reporting.run_artifacts import write_json_file
from tests.se.test_acquisition_custody import _live_run


def _old_bytes(models) -> bytes:
    return "".join(_canonical_line(m) + "\n" for m in models).encode()


def test_sealed_jsonl_files_match_the_old_whole_string_encoding(tmp_path: Path) -> None:
    _live_run(tmp_path, flaky=True)
    root = tmp_path / "custody"
    sealed = validate_seal(root)
    assert sealed.attempts, "fixture must produce attempts"
    assert (root / QUERY_ATTEMPTS_FILE).read_bytes() == _old_bytes(sealed.attempts)
    assert (root / QUERY_RECORD_MAP_FILE).read_bytes() == _old_bytes(sealed.mappings)
    assert (root / ACQUISITION_LEDGER_FILE).read_bytes() == _old_bytes(sealed.ledger)


def test_streamed_json_file_matches_json_dumps_indent_2(tmp_path: Path) -> None:
    payload = {
        "b": [1, 2.5, None, True, "é ✓"],
        "a": {"nested": [{"x": "y"}, []], "empty": {}},
        "unicode": "CAR-γδT – “quoted”",
    }
    out = tmp_path / "result.json"
    write_json_file(out, payload)
    assert out.read_bytes() == (json.dumps(payload, indent=2) + "\n").encode()
