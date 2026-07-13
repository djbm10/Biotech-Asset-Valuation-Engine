"""Surfacing the Conviction Update trail into memo/JSON (Batch 2 follow-up).

Wires the PR-1 ``ConvictionRecord`` audit trail into the compact JSON summaries
and the BD memo — presentation only. Pins that the trail carries the fields an
analyst needs (prior -> per-update LR/informativeness/rationale/bucket ->
posterior), stays JSON-safe, is copied from thesis to BD result, and does NOT
alter POS / the science modifier.
"""
from __future__ import annotations

import json

from bve.intelligence.buyer_problem_library import BuyerProblemLibrary
from bve.intelligence.conviction_update import (
    build_conviction_summary,
    conviction_record_to_dict,
    interpret_readout,
    update_killer_question_posterior,
)
from bve.intelligence.killer_question import KillerArchetype, KillerQuestion
from bve.intelligence.layer15_buyer_match import Layer15BuyerMatchInput, Layer15BuyerMatcher
from bve.intelligence.science_thesis_builder import (
    ScienceThesisBuilder,
    ScienceThesisBuilderInput,
)
from bve.intelligence.science_thesis_summary import build_bd_summary, build_science_summary
from bve.reporting.memo_generator import _conviction_context


def _record():
    q = KillerQuestion(
        archetype=KillerArchetype.DIFFERENTIATION,
        question_text="Is the effect above the disease bar?",
        posterior=0.5,
    )
    hit = interpret_readout(21.0, bar=20.0)  # clean hit
    _, record = update_killer_question_posterior(q, [hit])
    return record


def _thesis():
    return ScienceThesisBuilder().build(
        ScienceThesisBuilderInput(
            asset_id="asset-1",
            asset_name="Asset 1",
            indication="autoimmune",
            phase="phase2",
            modality="antibody",
            target="BAFF",
            mechanism="BAFF inhibition",
            has_target_rationale=True,
            has_pkpd_evidence=True,
            has_human_pkpd_evidence=True,
            has_biomarker_validation=True,
            has_human_poc=True,
        )
    )


# --------------------------------------------------------------------------
# Serializer shape
# --------------------------------------------------------------------------

def test_record_to_dict_carries_analyst_fields() -> None:
    d = conviction_record_to_dict(_record())
    assert d["prior"] == 0.5
    assert d["posterior"] > 0.5
    assert d["updates"]
    row = d["updates"][0]
    for key in ("source", "direction", "label", "likelihood_ratio", "informativeness", "rationale"):
        assert key in row
    assert row["label"] == "clean_hit"
    assert row["source"] == "readout"
    json.dumps(d)  # JSON-safe


def test_build_conviction_summary_empty_is_none() -> None:
    assert build_conviction_summary(None) is None
    assert build_conviction_summary([]) is None
    assert build_conviction_summary([_record()]) is not None


# --------------------------------------------------------------------------
# JSON summaries — thesis + BD
# --------------------------------------------------------------------------

def test_science_summary_includes_conviction_trail_when_present() -> None:
    thesis = _thesis()
    baseline = build_science_summary(thesis, modifier_applied=False)
    assert "conviction_trail" not in baseline  # empty by default

    with_trail = thesis.model_copy(update={"conviction_records": [_record()]})
    summary = build_science_summary(with_trail, modifier_applied=False)
    assert summary["conviction_trail"][0]["archetype"] == "differentiation"
    # Surfacing must not disturb the science scoring facts.
    assert summary["science_modifier"] == baseline["science_modifier"]
    json.dumps(summary)


def test_bd_summary_carries_trail_copied_from_thesis() -> None:
    thesis = _thesis().model_copy(update={"conviction_records": [_record()]})
    buyer_problem = BuyerProblemLibrary.from_yaml(
        "examples/configs/buyer_problems/vertex.yaml"
    ).problems[0]
    bd_result = Layer15BuyerMatcher().match(
        Layer15BuyerMatchInput(
            science_thesis=thesis,
            buyer_problem=buyer_problem,
            therapeutic_area="autoimmune",
            target="BAFF",
            modality="antibody",
            solves_buyer_problem=True,
            problem_solution_fit=0.8,
        )
    )
    # Layer15 copies the trail onto the BD result.
    assert list(bd_result.conviction_records)

    summary = build_bd_summary(bd_result, buyer_problem=buyer_problem)
    assert summary["conviction_trail"][0]["updates"]
    json.dumps(summary)


# --------------------------------------------------------------------------
# Memo context + template compile
# --------------------------------------------------------------------------

def test_memo_context_renders_trail_or_none() -> None:
    assert _conviction_context(None) is None
    ctx = _conviction_context([_record()])
    assert ctx[0]["updates"][0]["label"] == "clean_hit"


def test_bd_memo_template_compiles_and_block_renders() -> None:
    from bve.reporting.memo_generator import _make_env

    env = _make_env()
    # Compiles the whole file, including the new conviction block (syntax guard).
    env.get_template("bd_memo.md.j2")

    # Render just the conviction block to prove it emits the trail.
    block = (
        "{% if science_thesis.conviction_trail %}\n"
        "### Conviction Trail\n"
        "{% for rec in science_thesis.conviction_trail %}\n"
        "**{{ rec.archetype | replace('_', ' ') }}** — prior "
        "{{ '%.0f'|format((rec.prior or 0) * 100) }}% → posterior "
        "{{ '%.0f'|format((rec.posterior or 0) * 100) }}%\n"
        "{% for u in rec.updates -%}\n"
        "| {{ u.source | replace('_', ' ') }} |"
        " {{ (u.label or u.direction) | replace('_', ' ') }} |"
        " {{ '%.2f'|format(u.likelihood_ratio or 0) }} |\n"
        "{% endfor %}\n"
        "{% endfor %}\n"
        "{% endif %}\n"
    )
    rendered = env.from_string(block).render(
        science_thesis={"conviction_trail": _conviction_context([_record()])}
    )
    assert "Conviction Trail" in rendered
    assert "differentiation" in rendered
    assert "clean hit" in rendered  # label with underscores replaced
