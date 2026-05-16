"""Benchmark report rendering."""

from __future__ import annotations

from .benchmark_runner import BenchmarkResult


def render_benchmark_report(results: dict[str, list[BenchmarkResult]]) -> str:
    """Render benchmark comparison results as a Markdown table."""
    lines = ["# Benchmark Report", ""]
    lines.append("| Model | Metric | Model Value | Baseline | Improvement | Status | N |")
    lines.append("|-------|--------|-------------|----------|-------------|--------|---|")

    for section, section_results in results.items():
        for r in section_results:
            status = "PASS" if r.passed else "FAIL"
            direction = "+" if r.improvement_pct >= 0 else ""
            lines.append(
                f"| {r.model_name} | {r.metric} | {r.model_value:.4f} | "
                f"{r.baseline_value:.4f} | {direction}{r.improvement_pct:.1f}% | "
                f"{status} | {r.n_samples} |"
            )

    lines.append("")
    all_results = [r for section in results.values() for r in section]
    passed = sum(1 for r in all_results if r.passed)
    lines.append(f"**{passed}/{len(all_results)} checks passed**")
    return "\n".join(lines)
