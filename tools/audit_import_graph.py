"""tools/audit_import_graph.py — Intelligence module static-analysis audit.

Scans src/bve/intelligence/*.py using AST (no runtime imports) and classifies
every module by how it is consumed:

  LIVE_CORE           — directly imported by CLI, API, ops, or workflow layer
  LIVE_SUPPORTING     — imported only by other intelligence modules that are
                        LIVE_CORE or LIVE_SUPPORTING (transitive live chain)
  TEST_ONLY           — has test coverage but no live consumer chain
  ARCHIVE_CANDIDATE   — no live consumer chain AND no test coverage
  DUPLICATE_CANDIDATE — shares a name prefix with another module covering the
                        same concept (e.g. ma_layer3_gate vs ma_layer3_pair_realism)

No files are modified or deleted.  Run:

    python tools/audit_import_graph.py
    python tools/audit_import_graph.py --output docs/intelligence_module_audit.md
    python tools/audit_import_graph.py --json   # prints JSON to stdout

The script exits 0 on success and writes docs/intelligence_module_audit.md by
default.
"""
from __future__ import annotations

import ast
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Repo layout constants
# ---------------------------------------------------------------------------

REPO_ROOT   = Path(__file__).resolve().parent.parent
INTEL_DIR   = REPO_ROOT / "src" / "bve" / "intelligence"
CLI_DIR     = REPO_ROOT / "src" / "bve" / "cli"
OPS_DIR     = REPO_ROOT / "src" / "bve" / "ops"
WORKFLOW_DIR = REPO_ROOT / "src" / "bve" / "workflows"
API_DIR     = REPO_ROOT / "apps" / "api"
TEST_DIRS   = [
    REPO_ROOT / "tests",
    REPO_ROOT / "tests" / "intelligence",
]
DEFAULT_OUTPUT = REPO_ROOT / "docs" / "intelligence_module_audit.md"

# Canonical duplicate-candidate pairs (manually identified from naming patterns)
# Each tuple is (module_a, module_b, note)
KNOWN_DUPLICATE_CANDIDATES: list[tuple[str, str, str]] = [
    (
        "ma_layer3_gate",
        "ma_layer3_pair_realism",
        "Both implement Layer 3 deal-gate logic. ma_layer3_pair_realism is the "
        "current wired version; ma_layer3_gate is an earlier standalone design "
        "with its own test suite.",
    ),
    (
        "ma_layer4_routing",
        "ma_layer4_bd_routing",
        "Both implement Layer 4 routing/watchlist classification. "
        "ma_layer4_bd_routing is consumed by ma_probability; ma_layer4_routing "
        "is a broader earlier design with deal-type overlay logic.",
    ),
    (
        "variant_view",
        "variant_view_engine",
        "Both model variant thesis / market-vs-model PoS gap. "
        "variant_view_engine is the newer agent-oriented version; "
        "variant_view is a simpler Pydantic model used in earlier sprints.",
    ),
    (
        "acquisition_likelihood",
        "acquisition_readiness",
        "Both gate whether an asset is ready for acquisition consideration. "
        "acquisition_readiness is the current live version; "
        "acquisition_likelihood is a two-stage model used only by ma_calibration.",
    ),
    (
        "mapping",
        "knowledge_layer",
        "mapping.py loads event-to-assumption YAML rules that are also "
        "partially handled inside knowledge_layer. Overlap is partial, not full.",
    ),
]


# ---------------------------------------------------------------------------
# Step 1: collect all Python files in the repo (excluding venv / cache)
# ---------------------------------------------------------------------------

def _iter_py_files(root: Path) -> list[Path]:
    return [
        p for p in root.rglob("*.py")
        if ".venv" not in str(p)
        and "__pycache__" not in str(p)
        and ".git" not in str(p)
    ]


# ---------------------------------------------------------------------------
# Step 2: extract bve.intelligence.* imports from a file via AST
# ---------------------------------------------------------------------------

_INTEL_PREFIX = "bve.intelligence."

def _extract_intel_imports(path: Path) -> set[str]:
    """Return the set of bve.intelligence.<module> names imported by *path*."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return set()

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "bve.intelligence" or mod.startswith(_INTEL_PREFIX):
                # e.g. from bve.intelligence.knowledge_layer import KnowledgeStore
                # → module = "knowledge_layer"
                if mod.startswith(_INTEL_PREFIX):
                    found.add(mod[len(_INTEL_PREFIX):].split(".")[0])
                else:
                    # from bve.intelligence import X  → X is a submodule name
                    for alias in node.names:
                        found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name.startswith(_INTEL_PREFIX):
                    found.add(name[len(_INTEL_PREFIX):].split(".")[0])
                elif name == "bve.intelligence":
                    pass  # package-level; ignore
    return found


# ---------------------------------------------------------------------------
# Step 3: build the full consumer map
# ---------------------------------------------------------------------------

def _bucket(path: Path) -> str:
    """Return a consumer bucket label for a file path."""
    s = str(path)
    if "/cli/" in s:
        return "cli"
    if "/apps/" in s or "/api/" in s:
        return "api"
    if "/workflows/" in s:
        return "workflow"
    if "/ops/" in s:
        return "ops"
    if "/intelligence/" in s and "/tests/" not in s and "/test" not in path.name:
        return "intelligence"
    if "/tests/" in s or "test_" in path.name:
        return "test"
    return "other"


def build_consumer_map(repo_root: Path, intel_modules: list[str]) -> dict[str, dict]:
    """Return a dict: module_name → consumer info dict."""
    module_set = set(intel_modules)

    # consumers[mod][bucket] = list of file paths
    consumers: dict[str, dict[str, list[Path]]] = {
        m: defaultdict(list) for m in intel_modules
    }
    # within-intelligence imports
    intel_imports: dict[str, set[str]] = {m: set() for m in intel_modules}

    all_py = _iter_py_files(repo_root)
    intel_dir_str = str(INTEL_DIR)

    for py_file in all_py:
        imported = _extract_intel_imports(py_file)
        if not imported:
            continue
        bucket = _bucket(py_file)
        for mod in imported:
            if mod in module_set:
                consumers[mod][bucket].append(py_file)
                if str(py_file).startswith(intel_dir_str) and bucket == "intelligence":
                    # record which intelligence module imports this one
                    pass  # we need the reverse: what does this file's module import

    # Build intra-intelligence import graph: mod → set of mods it imports
    for mod in intel_modules:
        path = INTEL_DIR / f"{mod}.py"
        if path.exists():
            intel_imports[mod] = _extract_intel_imports(path) & module_set

    return consumers, intel_imports


# ---------------------------------------------------------------------------
# Step 4: classify each module
# ---------------------------------------------------------------------------

_LIVE_EXTERNAL_BUCKETS = {"cli", "api", "workflow", "ops"}


def _has_tests(mod: str, consumers: dict) -> bool:
    return bool(consumers[mod].get("test"))


def _live_external_consumers(mod: str, consumers: dict) -> list[str]:
    """Short names of files in CLI/API/workflow/ops that import this module."""
    result = []
    for bucket in _LIVE_EXTERNAL_BUCKETS:
        for p in consumers[mod].get(bucket, []):
            result.append(p.name)
    return sorted(set(result))


def classify_modules(
    intel_modules: list[str],
    consumers: dict,
    intel_imports: dict,
) -> dict[str, str]:
    """Return module → status string."""

    # Pass 1: mark LIVE_CORE
    status: dict[str, str] = {}
    for mod in intel_modules:
        if _live_external_consumers(mod, consumers):
            status[mod] = "LIVE_CORE"

    # Pass 2: mark LIVE_SUPPORTING (transitively reachable from LIVE_CORE)
    # Build reverse graph: who imports me?
    imported_by: dict[str, set[str]] = defaultdict(set)
    for mod, imps in intel_imports.items():
        for dep in imps:
            imported_by[dep].add(mod)

    changed = True
    while changed:
        changed = False
        for mod in intel_modules:
            if mod in status:
                continue
            # If any module that imports this one is LIVE_CORE or LIVE_SUPPORTING
            for importer in imported_by.get(mod, set()):
                if status.get(importer) in ("LIVE_CORE", "LIVE_SUPPORTING"):
                    status[mod] = "LIVE_SUPPORTING"
                    changed = True
                    break

    # Pass 3: TEST_ONLY vs ARCHIVE_CANDIDATE
    for mod in intel_modules:
        if mod in status:
            continue
        if _has_tests(mod, consumers):
            status[mod] = "TEST_ONLY"
        else:
            status[mod] = "ARCHIVE_CANDIDATE"

    return status


# ---------------------------------------------------------------------------
# Step 5: build the full module record
# ---------------------------------------------------------------------------

def build_records(
    intel_modules: list[str],
    consumers: dict,
    intel_imports: dict,
    status: dict[str, str],
) -> list[dict]:
    imported_by_all: dict[str, set[str]] = defaultdict(set)
    for mod, imps in intel_imports.items():
        for dep in imps:
            imported_by_all[dep].add(mod)

    records = []
    for mod in sorted(intel_modules):
        path = INTEL_DIR / f"{mod}.py"
        line_count = len(path.read_text(encoding="utf-8", errors="replace").splitlines()) if path.exists() else 0

        cli_consumers = sorted({p.name for p in consumers[mod].get("cli", [])})
        api_consumers = sorted({p.name for p in consumers[mod].get("api", [])})
        wf_consumers  = sorted({p.name for p in consumers[mod].get("workflow", [])})
        ops_consumers = sorted({p.name for p in consumers[mod].get("ops", [])})
        test_files    = sorted({p.name for p in consumers[mod].get("test", [])})
        intel_consumers = sorted(imported_by_all.get(mod, set()))
        intel_deps    = sorted(intel_imports.get(mod, set()))

        records.append({
            "module": mod,
            "status": status[mod],
            "lines": line_count,
            "imported_by_intel": intel_consumers,
            "imports_intel": intel_deps,
            "cli_consumers": cli_consumers,
            "api_consumers": api_consumers,
            "workflow_consumers": wf_consumers,
            "ops_consumers": ops_consumers,
            "test_files": test_files,
            "has_tests": bool(test_files),
            "has_cli_consumer": bool(cli_consumers),
            "has_api_consumer": bool(api_consumers),
            "has_workflow_consumer": bool(wf_consumers),
            "has_ops_consumer": bool(ops_consumers),
        })
    return records


# ---------------------------------------------------------------------------
# Step 6: render Markdown report
# ---------------------------------------------------------------------------

_STATUS_EMOJI = {
    "LIVE_CORE":          "🟢",
    "LIVE_SUPPORTING":    "🔵",
    "TEST_ONLY":          "🟡",
    "ARCHIVE_CANDIDATE":  "🔴",
}

_STATUS_DESC = {
    "LIVE_CORE":
        "Directly imported by CLI, API, ops, or workflow layer.",
    "LIVE_SUPPORTING":
        "Imported by LIVE_CORE/LIVE_SUPPORTING modules; part of the live call chain.",
    "TEST_ONLY":
        "Has test coverage but no live consumer chain. Not wired into any CLI, "
        "API, ops, or workflow entry point.",
    "ARCHIVE_CANDIDATE":
        "No test coverage and no live consumer chain. Safe to archive after review.",
}


def _short_list(items: list[str], limit: int = 4) -> str:
    if not items:
        return "—"
    shown = items[:limit]
    suffix = f" +{len(items) - limit}" if len(items) > limit else ""
    return ", ".join(shown) + suffix


def render_markdown(
    records: list[dict],
    duplicate_candidates: list[tuple[str, str, str]],
    as_of: str,
) -> str:
    by_status: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_status[r["status"]].append(r)

    lines: list[str] = []

    lines += [
        f"# Intelligence Module Audit — {as_of}",
        "",
        "> Auto-generated by `tools/audit_import_graph.py`. "
        "Do not edit manually — re-run the script to refresh.",
        "",
        "---",
        "",
    ]

    # Summary table
    lines += ["## Summary", "", "| Status | Count | Description |", "|---|---|---|"]
    for status_key in ("LIVE_CORE", "LIVE_SUPPORTING", "TEST_ONLY", "ARCHIVE_CANDIDATE"):
        count = len(by_status.get(status_key, []))
        emoji = _STATUS_EMOJI[status_key]
        desc  = _STATUS_DESC[status_key]
        lines.append(f"| {emoji} {status_key} | {count} | {desc} |")
    lines += [
        "",
        f"**Total modules scanned:** {len(records)}",
        "",
        "---",
        "",
    ]

    # Duplicate candidates
    lines += [
        "## Duplicate / Superseded Candidates",
        "",
        "These pairs cover the same concept. One should be archived after human review.",
        "",
        "| Module A | Module B | Recommendation |",
        "|---|---|---|",
    ]
    dc_mods: set[str] = set()
    for a, b, note in duplicate_candidates:
        lines.append(f"| `{a}` | `{b}` | {note} |")
        dc_mods.update([a, b])
    lines += ["", "---", ""]

    # Full table
    lines += [
        "## Full Module Table",
        "",
        "| Module | Status | Lines | imported_by | imports | CLI | API | Ops/Workflow | Tests |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in records:
        status_cell = f"{_STATUS_EMOJI.get(r['status'], '')} {r['status']}"
        dup_flag = " ⚠" if r["module"] in dc_mods else ""
        lines.append(
            f"| `{r['module']}`{dup_flag} | {status_cell} | {r['lines']} "
            f"| {_short_list(r['imported_by_intel'])} "
            f"| {_short_list(r['imports_intel'])} "
            f"| {'✓' if r['has_cli_consumer'] else '—'} "
            f"| {'✓' if r['has_api_consumer'] else '—'} "
            f"| {'✓' if (r['has_ops_consumer'] or r['has_workflow_consumer']) else '—'} "
            f"| {'✓' if r['has_tests'] else '—'} |"
        )
    lines += ["", "---", ""]

    # LIVE_CORE detail
    lines += ["## LIVE_CORE — Detail", "", "Modules directly consumed by CLI, API, ops, or workflows.", ""]
    for r in sorted(by_status.get("LIVE_CORE", []), key=lambda x: x["module"]):
        consumers_str = ", ".join(
            r["cli_consumers"] + r["api_consumers"] +
            r["ops_consumers"] + r["workflow_consumers"]
        )
        lines.append(f"- **`{r['module']}`** ({r['lines']} lines) — consumed by: {consumers_str or '(see table)'}")
    lines += ["", "---", ""]

    # TEST_ONLY detail
    lines += [
        "## TEST_ONLY — Detail",
        "",
        "These modules have test coverage but are not wired into any CLI, API, ops, or workflow "
        "entry point. They may be experimental features or partially complete implementations. "
        "**No immediate action required** — review before the next major refactor.",
        "",
    ]
    for r in sorted(by_status.get("TEST_ONLY", []), key=lambda x: x["module"]):
        tests_str = ", ".join(r["test_files"])
        deps_str  = ", ".join(r["imports_intel"]) if r["imports_intel"] else "none"
        lines.append(f"- **`{r['module']}`** ({r['lines']} lines)")
        lines.append(f"  - Tests: {tests_str}")
        lines.append(f"  - Imports: {deps_str}")
        lines.append(f"  - Imported by: {', '.join(r['imported_by_intel']) or 'nothing (within intelligence)'}")
        lines.append("")

    lines += ["---", ""]

    # ARCHIVE_CANDIDATE detail
    lines += [
        "## ARCHIVE_CANDIDATE — Detail",
        "",
        "These modules have **no test coverage** and **no live consumer chain**. "
        "They are the safest candidates for archival. "
        "**Recommended action:** move to `src/bve/intelligence/_archive/` after confirming "
        "no runtime behavior depends on them.",
        "",
    ]
    for r in sorted(by_status.get("ARCHIVE_CANDIDATE", []), key=lambda x: x["module"]):
        deps_str = ", ".join(r["imports_intel"]) if r["imports_intel"] else "none"
        lines.append(f"- **`{r['module']}`** ({r['lines']} lines)")
        lines.append(f"  - Imports: {deps_str}")
        lines.append(f"  - Imported by: {', '.join(r['imported_by_intel']) or 'nothing'}")
        lines.append("")

    lines += ["---", ""]

    # Action items
    lines += [
        "## Action Items",
        "",
        "### Immediate (no code changes required)",
        "",
        "- [ ] Review each DUPLICATE_CANDIDATE pair above. "
        "Confirm which version is canonical and add a comment to the other.",
        "- [ ] For each ARCHIVE_CANDIDATE, verify by reading the file that no "
        "runtime side-effect (e.g. module-level singleton, config loader) is triggered at import.",
        "",
        "### Before next major feature block",
        "",
        "- [ ] For TEST_ONLY modules: decide KEEP (wire into a workflow) or ARCHIVE.",
        "  Priority: modules with >200 lines and no clear path to live wiring.",
        "- [ ] For LIVE_SUPPORTING modules: confirm the full chain from LIVE_CORE "
        "still reaches them (run this script after any module rename/delete).",
        "",
        "### Do not do yet",
        "",
        "- ❌ Do not delete any file based solely on this report.",
        "- ❌ Do not rename modules (breaks imports silently if any test stubs mock the path).",
        "- ❌ Do not merge DUPLICATE_CANDIDATEs until the canonical version has 100% "
        "test coverage of the superseded module's behaviour.",
        "",
        "---",
        "",
        f"*Generated: {as_of} by `tools/audit_import_graph.py`*",
    ]

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_audit(
    output_path: Optional[Path] = None,
    emit_json: bool = False,
) -> int:
    """Run the audit and write the Markdown report.

    Returns 0 on success, 1 on error.
    """
    if not INTEL_DIR.exists():
        print(f"ERROR: intelligence directory not found: {INTEL_DIR}", file=sys.stderr)
        return 1

    intel_modules = sorted([
        f.stem for f in INTEL_DIR.glob("*.py")
        if f.stem not in ("__init__",)
    ])
    print(f"[audit] Found {len(intel_modules)} intelligence modules.", file=sys.stderr)

    print("[audit] Building consumer map (AST scan)...", file=sys.stderr)
    consumers, intel_imports = build_consumer_map(REPO_ROOT, intel_modules)

    print("[audit] Classifying modules...", file=sys.stderr)
    status = classify_modules(intel_modules, consumers, intel_imports)

    counts = defaultdict(int)
    for s in status.values():
        counts[s] += 1
    for s in ("LIVE_CORE", "LIVE_SUPPORTING", "TEST_ONLY", "ARCHIVE_CANDIDATE"):
        print(f"  {s}: {counts[s]}", file=sys.stderr)

    records = build_records(intel_modules, consumers, intel_imports, status)

    if emit_json:
        print(json.dumps(records, indent=2, default=str))
        return 0

    as_of = date.today().isoformat()
    report = render_markdown(records, KNOWN_DUPLICATE_CANDIDATES, as_of)

    out = output_path or DEFAULT_OUTPUT
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(f"[audit] Report written to {out}", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="audit_import_graph",
        description=(
            "Static-analysis audit of src/bve/intelligence/*.py. "
            "Classifies every module as LIVE_CORE, LIVE_SUPPORTING, TEST_ONLY, "
            "or ARCHIVE_CANDIDATE and writes docs/intelligence_module_audit.md."
        ),
    )
    parser.add_argument(
        "--output", default=None,
        help=f"Output Markdown path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--json", action="store_true", dest="emit_json",
        help="Emit JSON to stdout instead of writing Markdown.",
    )
    args = parser.parse_args(argv)

    return run_audit(
        output_path=Path(args.output) if args.output else None,
        emit_json=args.emit_json,
    )


if __name__ == "__main__":
    raise SystemExit(main())
