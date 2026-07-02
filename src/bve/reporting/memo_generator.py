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
from bve.intelligence.conviction_update import build_conviction_summary
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
        "strategic_takeout": output.strategic_takeout,
        "strategic_takeout_note": output.strategic_takeout_note,
        "author": MEMO_AUTHOR,
        "disclaimer": MEMO_DISCLAIMER,
        "memo_type": memo_type,
        # Structured evidence bundle — always present (empty sections if no data)
        "evidence": MemoEvidenceBuilder.build(output),
        "science_thesis": _science_thesis_context(getattr(output, "science_thesis", None)),
        "bd_actionability": _bd_actionability_context(getattr(output, "bd_actionability", None)),
    }


def _science_thesis_context(science_thesis: object | None) -> dict | None:
    if science_thesis is None:
        return None
    modifier = getattr(science_thesis, "modifier_result", None)
    binding_question = getattr(science_thesis, "binding_science_question", "")
    return {
        "core_biological_hypothesis": getattr(science_thesis, "core_biological_hypothesis", ""),
        "binding_science_question": getattr(binding_question, "value", str(binding_question)),
        "what_must_be_true": getattr(science_thesis, "what_must_be_true", []),
        "missing_critical_evidence": getattr(science_thesis, "missing_critical_evidence", []),
        "next_readout_requirement": getattr(science_thesis, "next_readout_requirement", ""),
        "killer_question_set": _killer_question_context(
            getattr(science_thesis, "killer_question_set", None)
        ),
        "conviction_trail": _conviction_context(
            getattr(science_thesis, "conviction_records", None)
        ),
        "heuristic_science_modifier": getattr(modifier, "heuristic_science_modifier", None),
        "warnings": getattr(modifier, "warnings", []) if modifier is not None else [],
    }


def _killer_question_context(killer_question_set: object | None) -> dict | None:
    if killer_question_set is None:
        return None

    def _question_context(question: object) -> dict:
        archetype = getattr(question, "archetype", "")
        evidence_touched = getattr(question, "evidence_touched", "")
        return {
            "archetype": getattr(archetype, "value", str(archetype)),
            "question_text": getattr(question, "question_text", ""),
            "voi_score": getattr(question, "voi_score", None),
            "posterior": getattr(question, "posterior", None),
            "confidence": getattr(question, "confidence", None),
            "openness": getattr(question, "openness", None),
            "value_if_confirmed_m": getattr(question, "value_if_confirmed_m", None),
            "value_if_refuted_m": getattr(question, "value_if_refuted_m", None),
            "swing_m": getattr(question, "swing_m", None),
            "resolving_readout": getattr(question, "resolving_readout", ""),
            "evidence_touched": getattr(evidence_touched, "value", str(evidence_touched)),
            "diligence_question": getattr(question, "diligence_question", ""),
            "why_fired": getattr(question, "why_fired", ""),
            "flags": getattr(question, "flags", []),
        }

    return {
        "abstained": getattr(killer_question_set, "abstained", False),
        "abstain_reason": getattr(killer_question_set, "abstain_reason", ""),
        "company_focus_mismatch": getattr(killer_question_set, "company_focus_mismatch", None),
        "decisive": [
            _question_context(question)
            for question in (getattr(killer_question_set, "decisive", []) or [])
        ],
        "candidates": [
            _question_context(question)
            for question in (getattr(killer_question_set, "candidates", []) or [])
        ],
    }


def _conviction_context(records: object | None) -> list[dict] | None:
    """Compact conviction trail for the memo (prior -> updates -> posterior).

    Presentation only — the posterior never re-enters POS or the science modifier.
    """
    return build_conviction_summary(records)


def _bd_actionability_context(bd_actionability: object | None) -> dict | None:
    if bd_actionability is None:
        return None
    route = getattr(bd_actionability, "recommended_bd_route", "")
    return {
        "passed_hard_gates": getattr(bd_actionability, "passed_hard_gates", None),
        "failed_gates": getattr(bd_actionability, "failed_gates", []),
        "buyer_problem_fit": getattr(bd_actionability, "buyer_problem_fit", None),
        "science_thesis_fit": getattr(bd_actionability, "science_thesis_fit", None),
        "buyer_owner_advantage": getattr(bd_actionability, "buyer_owner_advantage", None),
        "diligence_questions": getattr(bd_actionability, "diligence_questions", []),
        "killer_question_set": _killer_question_context(
            getattr(bd_actionability, "killer_question_set", None)
        ),
        "conviction_trail": _conviction_context(
            getattr(bd_actionability, "conviction_records", None)
        ),
        "recommended_bd_route": getattr(route, "value", str(route)),
        "route_rationale": getattr(bd_actionability, "route_rationale", ""),
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
