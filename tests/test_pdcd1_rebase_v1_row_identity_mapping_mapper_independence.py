"""Static independence checks for the PDCD1 rebase v1 Milestone 6 v2 mappers.

Milestone 6 v1's release claimed "two independent mapping builds with 0
disagreements," but v1's Build B was in fact Build A's own ``map_rows()``
re-invoked with its input list reversed -- not a separate implementation.
Reversing the input order of a per-row-independent, order-agnostic mapping
function trivially reproduces identical output; it proves nothing about
independence.

This test guards Mapper B
(``scripts/pdcd1_rebase_v1_row_identity_mapping_mapper_b.py``), the genuine
second implementation built for Milestone 6 v2, against regressing into the
same defect: it must not import, call, or delegate to Mapper A in any form.
"""

from __future__ import annotations

import ast
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"

MAPPER_A_CANDIDATES = [
    "pdcd1_rebase_v1_row_identity_mapping.py",
    "pdcd1_rebase_v1_row_identity_mapping_mapper_a.py",
    "pdcd1_rebase_v1_row_identity_mapping_lib.py",
]
MAPPER_B_PATH = SCRIPTS_DIR / "pdcd1_rebase_v1_row_identity_mapping_mapper_b.py"


def _find_mapper_a() -> pathlib.Path | None:
    for name in MAPPER_A_CANDIDATES:
        candidate = SCRIPTS_DIR / name
        if candidate.exists():
            return candidate
    # Fall back to any sibling script whose name matches the row-identity-mapping
    # family but is not Mapper B itself -- Mapper A's original filename in this
    # repo may differ from the candidates above.
    for path in SCRIPTS_DIR.glob("pdcd1_rebase_v1_row_identity_mapping*.py"):
        if path.resolve() != MAPPER_B_PATH.resolve() and "mapper_b" not in path.name:
            return path
    return None


def test_mapper_b_exists_and_is_a_standalone_module() -> None:
    assert MAPPER_B_PATH.exists(), f"Mapper B script not found at {MAPPER_B_PATH}"
    source = MAPPER_B_PATH.read_text()
    assert source.strip(), "Mapper B script is empty"
    # Must be parseable as a standalone Python module.
    ast.parse(source, filename=str(MAPPER_B_PATH))


def test_mapper_b_does_not_import_mapper_a() -> None:
    """Static AST check: no `import`/`from ... import ...` naming Mapper A."""
    source = MAPPER_B_PATH.read_text()
    tree = ast.parse(source, filename=str(MAPPER_B_PATH))

    forbidden_fragments = [
        "row_identity_mapping_mapper_a",
        "row_identity_mapping_lib",
        "row_identity_mapping",  # catches `pdcd1_rebase_v1_row_identity_mapping` (Mapper A's
        # own historical module name) while still allowing this test file / Mapper B's own
        # name to be excluded explicitly below.
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
    call into it via subprocess/exec/importlib, or read its output ledgers as
    an input source (which would make B derivative of A's answers rather than
    of the frozen M1-M5 evidence)."""
    source = MAPPER_B_PATH.read_text()

    mapper_a = _find_mapper_a()
    if mapper_a is not None:
        assert mapper_a.name not in source, (
            f"Mapper B source references Mapper A's filename ({mapper_a.name}); "
            "Mapper B must be built independently from frozen M1-M5 evidence, "
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

    # Mapper B must not read the v1 Milestone 6 output ledgers (Build A's
    # *answers*) as an input source. It is only permitted to read frozen
    # M3/M4/M5 upstream artifacts.
    forbidden_input_markers = [
        "row_outcome_ledger.jsonl",
        "row_candidate_mapping_ledger.jsonl",
        "unresolved_row_ledger.jsonl",
    ]
    for marker in forbidden_input_markers:
        assert marker not in source, (
            f"Mapper B source references `{marker}`, one of Milestone 6's own "
            "output ledgers; Mapper B must derive its answers from frozen "
            "M1-M5 evidence only, never from Build A's M6 output."
        )


def test_mapper_b_is_not_reachable_by_reversing_mapper_a_input_order() -> None:
    """Regression guard for the exact v1 defect: v1's "Build B" was Build A's
    map_rows() called a second time with input order reversed. Assert that
    Mapper B's driver function is a distinct top-level function object (not
    an alias/wrapper) and that Mapper B's module does not define its output
    by calling a function named like Mapper A's with a reversed row list.
    """
    source = MAPPER_B_PATH.read_text()
    tree = ast.parse(source, filename=str(MAPPER_B_PATH))

    reversal_markers = ["[::-1]", "reversed(", ".reverse()"]
    has_reversal = any(marker in source for marker in reversal_markers)

    # It is fine for Mapper B to happen to use reversal for unrelated reasons,
    # but it must never be the *entire* mechanism by which its main row-mapping
    # driver produces output -- i.e. there must be a genuine, independent
    # driver function defined in this module.
    driver_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    assert any("map_rows" in name or "resolve" in name for name in driver_names), (
        "Mapper B does not define its own row-mapping driver/resolution "
        "function(s); expected independently authored logic, not a thin "
        "pass-through."
    )

    if has_reversal:
        # If reversal is present, it must not be the sole transformation
        # applied immediately before producing output rows (that would be
        # exactly v1's defect pattern).
        assert "map_rows(list(reversed(" not in source
        assert "map_rows(rows[::-1])" not in source
