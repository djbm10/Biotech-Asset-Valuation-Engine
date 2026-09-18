"""Static independence checks for the PDCD1 rebase v1 Milestone 7 candidate
chronology mappers.

Milestone 6's first release (v1) claimed two independent mapping builds with
0 disagreements, but v1's "Build B" was in fact Build A's own function
re-invoked with its input list reversed -- not a separate implementation.
Milestone 7 must not repeat that failure mode. This test guards Mapper B
(``scripts/pdcd1_rebase_v1_candidate_chronology_mapper_b.py``), the genuinely
independent second implementation built for Milestone 7, against regressing
into the same defect: it must not import, call, or delegate to Mapper A in
any form, and must not read Mapper A's own output ledger as an evidence
source.
"""

from __future__ import annotations

import ast
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"

MAPPER_A_PATH = SCRIPTS_DIR / "pdcd1_rebase_v1_candidate_chronology_mapper_a.py"
MAPPER_B_PATH = SCRIPTS_DIR / "pdcd1_rebase_v1_candidate_chronology_mapper_b.py"


def test_mapper_a_and_mapper_b_exist_as_standalone_modules() -> None:
    for path in (MAPPER_A_PATH, MAPPER_B_PATH):
        assert path.exists(), f"Expected mapper script not found at {path}"
        source = path.read_text()
        assert source.strip(), f"{path} is empty"
        ast.parse(source, filename=str(path))


def test_mapper_b_does_not_import_mapper_a() -> None:
    """Static AST check: no `import`/`from ... import ...` naming Mapper A."""
    source = MAPPER_B_PATH.read_text()
    tree = ast.parse(source, filename=str(MAPPER_B_PATH))

    forbidden_fragments = [
        "candidate_chronology_mapper_a",
        "pdcd1_rebase_v1_candidate_chronology",  # catches any historical/renamed
        # Mapper A module name; Mapper B's own filename is excluded below.
    ]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if "mapper_b" in name:
                    continue
                for fragment in forbidden_fragments:
                    assert fragment not in name, (
                        f"Mapper B imports a module matching Mapper A's naming "
                        f"pattern: `import {name}`"
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if "mapper_b" in module:
                continue
            for fragment in forbidden_fragments:
                assert fragment not in module, (
                    f"Mapper B imports from a module matching Mapper A's naming "
                    f"pattern: `from {module} import ...`"
                )


def test_mapper_b_source_never_references_mapper_a_by_path_or_name() -> None:
    """Mapper B's source text must not reference Mapper A's script filename,
    call into it via subprocess/exec/importlib, or read Mapper A's output
    ledger as an input source (which would make B derivative of A's answers
    rather than of the frozen M2/M5/M6-v2 evidence)."""
    source = MAPPER_B_PATH.read_text()

    assert MAPPER_A_PATH.name not in source, (
        f"Mapper B source references Mapper A's filename ({MAPPER_A_PATH.name}); "
        "Mapper B must be built independently from frozen M2/M5/M6-v2 evidence, "
        "not from Mapper A's script or its outputs."
    )

    forbidden_calls = [
        "importlib.import_module",
        "__import__(",
        "subprocess.run",
        "subprocess.Popen",
        "subprocess.call",
        "exec(",
        "eval(",
    ]
    for token in forbidden_calls:
        assert token not in source, (
            f"Mapper B source contains `{token}`, which could be used to "
            "dynamically delegate to Mapper A at runtime; static import "
            "analysis alone would not catch that."
        )

    forbidden_input_markers = [
        "build_a_candidate_chronology_ledger.jsonl",
    ]
    for marker in forbidden_input_markers:
        assert marker not in source, (
            f"Mapper B source references `{marker}`, Mapper A's own output "
            "ledger; Mapper B must derive its answers from frozen M2/M5/M6-v2 "
            "evidence only, never from Mapper A's output."
        )


def test_mapper_a_source_never_reads_mapper_b_output() -> None:
    """Symmetric guard: Mapper A must not read Mapper B's output ledger
    either, so neither build can be accused of quietly matching the other."""
    source = MAPPER_A_PATH.read_text()
    assert "build_b_candidate_chronology_ledger.jsonl" not in source, (
        "Mapper A source references Mapper B's own output ledger; each "
        "build must derive its answers independently from frozen evidence."
    )


def test_mapper_b_is_not_reachable_by_reversing_mapper_a_input_order() -> None:
    """Regression guard for the exact M6-v1 defect: v1's "Build B" was Build
    A's row-mapping function called a second time with input order reversed.
    Assert Mapper B defines its own genuine driver function(s), and that
    reversal (if present at all) is never the sole transformation applied
    immediately before producing output."""
    source = MAPPER_B_PATH.read_text()
    tree = ast.parse(source, filename=str(MAPPER_B_PATH))

    driver_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    assert any(
        "chronology" in name or "derive" in name or "match" in name
        for name in driver_names
    ), (
        "Mapper B does not define its own chronology-derivation driver "
        "function(s); expected independently authored logic, not a thin "
        "pass-through."
    )

    reversal_markers = ["[::-1]", "reversed(", ".reverse()"]
    has_reversal = any(marker in source for marker in reversal_markers)
    if has_reversal:
        assert "derive_candidate_chronology(sig, list(reversed(" not in source
        assert "[::-1])" not in source.replace(" ", "")


def test_mapper_a_and_mapper_b_use_structurally_different_iteration_order() -> None:
    """Mapper A is documented (and implemented) as NCT-outer / version-inner
    with candidates checked per version; Mapper B is candidate-outer /
    history-index-inner. Confirm each module's own docstring records this
    distinction, as a lightweight guard against the two builds silently
    converging on identical control flow."""
    a_source = MAPPER_A_PATH.read_text()
    b_source = MAPPER_B_PATH.read_text()
    assert "history_index" not in a_source, (
        "Mapper A is expected to read only the per-version ledger/version "
        "files (not M2's history_index.json artifact); if this changes, "
        "revisit whether the two builds are still structurally distinct."
    )
    assert "history_index" in b_source, (
        "Mapper B is expected to read M2's history_index.json artifact as "
        "part of its independent control flow."
    )
