"""Static independence checks for the PDCD1 rebase v1 Milestone 8 benchmark
finalization assemblers.

Mirrors the pattern established at Milestone 6
(``test_pdcd1_rebase_v1_row_identity_mapping_mapper_independence.py``) and
Milestone 7
(``test_pdcd1_rebase_v1_candidate_chronology_mapper_independence.py``):
Assembler B (``scripts/pdcd1_rebase_v1_m8_benchmark_finalization_assembler_b.py``)
must not import, call, or delegate to Assembler A
(``scripts/pdcd1_rebase_v1_m8_benchmark_finalization.py``) in any form, and
must not read Assembler A's own output ledgers as an evidence source. Both
assemblers reconstruct the same M8 benchmark package independently from the
same frozen M1-M7 evidence.
"""

from __future__ import annotations

import ast
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"

ASSEMBLER_A_PATH = SCRIPTS_DIR / "pdcd1_rebase_v1_m8_benchmark_finalization.py"
ASSEMBLER_B_PATH = SCRIPTS_DIR / "pdcd1_rebase_v1_m8_benchmark_finalization_assembler_b.py"


def test_assembler_a_and_assembler_b_exist_as_standalone_modules() -> None:
    for path in (ASSEMBLER_A_PATH, ASSEMBLER_B_PATH):
        assert path.exists(), f"Expected assembler script not found at {path}"
        source = path.read_text()
        assert source.strip(), f"{path} is empty"
        ast.parse(source, filename=str(path))


def test_assembler_b_does_not_import_assembler_a() -> None:
    """Static AST check: no `import`/`from ... import ...` naming Assembler A."""
    source = ASSEMBLER_B_PATH.read_text()
    tree = ast.parse(source, filename=str(ASSEMBLER_B_PATH))

    forbidden_fragments = [
        "m8_benchmark_finalization_assembler_a",
        "pdcd1_rebase_v1_m8_benchmark_finalization",  # catches Assembler A's
        # exact module name; Assembler B's own filename is excluded below
        # (it also contains this fragment as a prefix).
    ]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if "assembler_b" in name:
                    continue
                for fragment in forbidden_fragments:
                    assert fragment not in name, (
                        f"Assembler B imports a module matching Assembler A's "
                        f"naming pattern: `import {name}`"
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if "assembler_b" in module:
                continue
            for fragment in forbidden_fragments:
                assert fragment not in module, (
                    f"Assembler B imports from a module matching Assembler A's "
                    f"naming pattern: `from {module} import ...`"
                )


def test_assembler_b_source_never_references_assembler_a_by_path_or_name() -> None:
    """Assembler B's source text must not reference Assembler A's script
    filename, call into it via subprocess/exec/importlib, or read
    Assembler A's output artifacts as an input source (which would make B
    derivative of A's answers rather than of the frozen M1-M7 evidence)."""
    source = ASSEMBLER_B_PATH.read_text()

    assert ASSEMBLER_A_PATH.name not in source, (
        f"Assembler B source references Assembler A's filename "
        f"({ASSEMBLER_A_PATH.name}); Assembler B must be built independently "
        "from frozen M1-M7 evidence, not from Assembler A's script or its "
        "outputs."
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
            f"Assembler B source contains `{token}`, which could be used to "
            "dynamically delegate to Assembler A at runtime; static import "
            "analysis alone would not catch that."
        )

    # Assembler A's exact archive filename pattern (run_id immediately after
    # "benchmark-final-", no "assembler-b-" infix) must never appear in B's
    # source as a read target.
    assert "pdcd1-rebase-v1-benchmark-final-{run_id}" not in source.replace(
        '"', ""
    ).replace("'", ""), (
        "Assembler B source appears to reference Assembler A's exact archive "
        "naming pattern; Assembler B must derive its answers from frozen "
        "M1-M7 evidence only, never from Assembler A's output."
    )


def test_assembler_a_source_never_reads_assembler_b_output() -> None:
    """Symmetric guard: Assembler A must not read Assembler B's output
    artifacts either, so neither build can be accused of quietly matching
    the other."""
    source = ASSEMBLER_A_PATH.read_text()
    forbidden_markers = [
        "assembler_b",
        "pdcd1-rebase-v1-benchmark-final-assembler-b-",
    ]
    for marker in forbidden_markers:
        assert marker not in source, (
            f"Assembler A source references `{marker}` (Assembler B's own "
            "naming); each build must derive its answers independently from "
            "frozen evidence."
        )


def test_assembler_b_defines_its_own_driver_and_uses_distinct_internal_structures() -> None:
    """Assembler B must define its own genuine assembly/validation logic
    (not a thin pass-through), organized via a class + typed dataclasses
    rather than Assembler A's flat module-level-function-over-dict style."""
    source = ASSEMBLER_B_PATH.read_text()
    tree = ast.parse(source, filename=str(ASSEMBLER_B_PATH))

    class_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    assert "AssemblerB" in class_names, (
        "Assembler B is expected to organize its assembly/validation logic "
        "as a class (`AssemblerB`), a structurally different organization "
        "from Assembler A's flat module-level functions."
    )
    assert {"CandidateIndex", "RowIndex"} <= class_names, (
        "Assembler B is expected to define its own typed index dataclasses "
        "(CandidateIndex, RowIndex) rather than Assembler A's single loosely "
        "typed `sources: dict[str, Any]` blob."
    )

    method_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }
    assert "build_modality_intent_ledger" in method_names, (
        "Assembler B does not define its own modality/intent derivation "
        "logic; expected independently authored logic, not a thin "
        "pass-through of Assembler A's output."
    )


def test_assembler_a_and_assembler_b_use_structurally_different_data_organization() -> None:
    """Lightweight guard against the two assemblers silently converging on
    identical internal structure: Assembler A is documented (and
    implemented) as a flat dict-of-lists over module-level functions;
    Assembler B is documented (and implemented) as dataclass-backed typed
    indices driven by a class."""
    a_source = ASSEMBLER_A_PATH.read_text()
    b_source = ASSEMBLER_B_PATH.read_text()

    a_tree = ast.parse(a_source, filename=str(ASSEMBLER_A_PATH))
    b_tree = ast.parse(b_source, filename=str(ASSEMBLER_B_PATH))

    a_classes = {node.name for node in ast.walk(a_tree) if isinstance(node, ast.ClassDef)}
    b_classes = {node.name for node in ast.walk(b_tree) if isinstance(node, ast.ClassDef)}

    assert "AssemblerB" not in a_classes, (
        "Assembler A unexpectedly defines an `AssemblerB` class; if this "
        "changes, revisit whether the two assemblers are still structurally "
        "distinct."
    )
    assert "AssemblerB" in b_classes, "Assembler B must define its `AssemblerB` driver class."
    assert "dataclass" in b_source, "Assembler B is expected to use dataclasses for its typed indices."
