"""
Memo generator: ValuationOutput → rendered Markdown memo.

Uses Jinja2 templates. One engine, three memo skins:
  "bd"  → Vertex-style BD acquisition memo
  "vc"  → VC investment memo
  "hf"  → Hedge fund event-driven / mispricing memo
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from jinja2 import Environment, FileSystemLoader, select_autoescape

from bve.config.constants import MEMO_AUTHOR, MEMO_DISCLAIMER
from bve.reporting.evidence_builder import MemoEvidenceBuilder
from bve.valuation.outputs import ValuationOutput

MemoType = Literal["bd", "vc", "hf"]

_TEMPLATE_DIR = Path(__file__).parent / "templates"
_TEMPLATE_FILES: dict[MemoType, str] = {
    "bd": "bd_memo.md.j2",
    "vc": "vc_memo.md.j2",
    "hf": "hf_memo.md.j2",
}


def _build_context(output: ValuationOutput, memo_type: MemoType) -> dict:
    """Flatten ValuationOutput into a template-friendly context dict."""
    d = output.summary_dict
    d.update({
        "mc_p5": output.monte_carlo.percentile_5_millions,
        "mc_p25": output.monte_carlo.percentile_25_millions,
        "mc_p75": output.monte_carlo.percentile_75_millions,
        "mc_n_simulations": output.monte_carlo.n_simulations,
        "rnpv_gross_revenue_pv": output.rnpv.gross_revenue_pv_millions,
        "rnpv_prob_adj_revenue_pv": output.rnpv.probability_adjusted_revenue_pv_millions,
        "rnpv_trial_costs_pv": output.rnpv.trial_costs_pv_millions,
        "shares_outstanding_millions": output.company.shares_outstanding_millions,
        # Falsification section helpers
        "combined_pos_pct": round(output.rnpv.cumulative_success_probability * 100, 1),
        "n_competitors": len(output.asset.competitor_assets),
    })

    # Phases detail (for timeline tables)
    phases = []
    for pb in output.rnpv.phase_breakdown:
        # Find matching trial for cost/enrollment
        trial_match = next(
            (t for t in output.trials if t.phase.value == pb.phase), None
        )
        phases.append({
            "phase": pb.phase,
            "success_probability": pb.success_probability,
            "duration_years": pb.duration_years,
            "cost_millions": trial_match.cost_millions if trial_match else 0,
            "pv_cost_weighted": pb.pv_cost_weighted,
        })

    return {
        "d": d,
        "asset": output.asset,
        "company": output.company,
        "trials": output.trials,
        "market": output.market_model,
        "indication": output.indication,
        "rnpv": output.rnpv,
        "scenarios": output.scenarios,
        "mc": output.monte_carlo,
        "phases": phases,
        "sensitivities": output.sensitivities,
        "upcoming_catalysts": output.asset.upcoming_catalysts,
        "assumption_log": output.assumption_log,
        "decision_framing": output.decision_framing,
        "implied_pos_pct": f"{output.implied_pos:.1%}" if output.implied_pos is not None else None,
        "implied_pos": output.implied_pos,
        "lifecycle_events": output.lifecycle_events_applied,
        "comps": output.comps_fair_value_band,
        "author": MEMO_AUTHOR,
        "disclaimer": MEMO_DISCLAIMER,
        "memo_type": memo_type,
        # Structured evidence bundle — always present (empty sections if no data)
        "evidence": MemoEvidenceBuilder.build(output),
    }


def _make_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    # Custom filter: format large integers with commas
    def format_int(value) -> str:
        try:
            return f"{int(value):,}"
        except (TypeError, ValueError):
            return str(value)

    env.filters["format_int"] = format_int
    return env


class MemoGenerator:
    """Thin class wrapper around generate_memo / save_memo for test and API convenience."""

    def generate(self, output: ValuationOutput, memo_type: MemoType = "bd") -> str:
        return generate_memo(output, memo_type=memo_type)

    def save(
        self,
        output: ValuationOutput,
        memo_type: MemoType = "bd",
        output_dir: str | Path = "memos",
        filename: str | None = None,
    ) -> Path:
        return save_memo(output, memo_type=memo_type, output_dir=output_dir, filename=filename)


def generate_memo(
    output: ValuationOutput,
    memo_type: MemoType = "bd",
) -> str:
    """
    Render a memo as a Markdown string.

    Parameters
    ----------
    output:     ValuationOutput from ValuationEngine.run()
    memo_type:  "bd" | "vc" | "hf"

    Returns
    -------
    Rendered Markdown string
    """
    env = _make_env()
    template_file = _TEMPLATE_FILES.get(memo_type)
    if not template_file:
        raise ValueError(f"Unknown memo_type: {memo_type}. Choose from: {list(_TEMPLATE_FILES)}")

    template = env.get_template(template_file)
    context = _build_context(output, memo_type)
    rendered = template.render(**context)

    # Attach rendered memo and evidence to output object for convenience
    output.memo_markdown = rendered
    output.memo_evidence = context["evidence"]
    return rendered


def save_memo(
    output: ValuationOutput,
    memo_type: MemoType = "bd",
    output_dir: str | Path = "memos",
    filename: str | None = None,
) -> Path:
    """
    Generate and save memo as a .md file.

    Returns the Path of the saved file.
    """
    md = generate_memo(output, memo_type)

    output_dir = Path(output_dir) / memo_type
    output_dir.mkdir(parents=True, exist_ok=True)

    if filename is None:
        safe_name = output.asset.name.replace(" ", "_").replace("/", "-")
        filename = f"{safe_name}_{memo_type}_memo_{output.analysis_date}.md"

    path = output_dir / filename
    path.write_text(md, encoding="utf-8")
    return path
