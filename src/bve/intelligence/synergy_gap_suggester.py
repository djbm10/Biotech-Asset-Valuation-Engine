"""
Block 4C: Synergy-aware gap suggester.

Given an acquirer's existing portfolio (derived from recent deals + partnerships),
identify which synergy rules are half-matched (one side present, other side missing)
and rank the resulting gap-fill opportunities.

Usage::

    from bve.intelligence.synergy_gap_suggester import suggest_synergy_gaps

    suggestions = suggest_synergy_gaps(acquirer_portfolio)
    for s in suggestions[:5]:
        print(s)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from bve.analysis.synergy_graph import (
    SynergyAssetProfile,
    SynergyGraph,
    SynergyRule,
    SynergyType,
    _CANONICAL_RULES,
    _SYNERGY_TYPE_WEIGHTS,
)


# ---------------------------------------------------------------------------
# Gap suggestion result
# ---------------------------------------------------------------------------

@dataclass
class SynergyGapSuggestion:
    """One suggested gap-fill opportunity."""
    rule_id: str
    synergy_type: SynergyType
    present_asset_ids: list[str]           # Portfolio asset(s) satisfying the matched side
    present_signals: list[str]             # Signals that matched in the portfolio
    missing_signals: frozenset[str]        # Signals the acquirer needs to acquire
    gap_score: float                       # Priority score 0–1 (higher = higher value gap)
    description: str
    evidence: str

    def __str__(self) -> str:
        missing = ", ".join(sorted(self.missing_signals)[:5])
        present = ", ".join(self.present_asset_ids[:3])
        return (
            f"[{self.gap_score:.2f}] {self.synergy_type.value}: "
            f"present=({present}) → need signals: {missing}\n"
            f"  {self.description}"
        )


@dataclass
class SynergyGapReport:
    """Full gap analysis for an acquirer portfolio."""
    portfolio_asset_ids: list[str]
    current_synergy_score: float
    suggestions: list[SynergyGapSuggestion]
    covered_synergy_types: list[str]
    uncovered_synergy_types: list[str]

    @property
    def top_suggestions(self) -> list[SynergyGapSuggestion]:
        return self.suggestions[:5]

    def print_summary(self, *, top_n: int = 5) -> None:
        print(f"\nSynergy Gap Analysis — {len(self.portfolio_asset_ids)} portfolio assets")
        print(f"  Current synergy score: {self.current_synergy_score:.2f}")
        print(f"  Covered types: {', '.join(self.covered_synergy_types) or 'none'}")
        print(f"  Gap opportunities: {len(self.suggestions)}")
        if self.suggestions:
            print(f"\n  Top {min(top_n, len(self.suggestions))} gap-fill suggestions:")
            for s in self.suggestions[:top_n]:
                print(f"    {s}")


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _match_one_side(
    portfolio_assets: list[SynergyAssetProfile],
    rule_signals: frozenset[str],
    graph: SynergyGraph,
) -> tuple[list[str], list[str]]:
    """
    Return (matched_asset_ids, matched_signals) for portfolio assets that satisfy
    at least one token in rule_signals.
    """
    matched_asset_ids: list[str] = []
    matched_signals: list[str] = []
    for asset in portfolio_assets:
        hits = graph._tokens_match(asset.all_tokens, rule_signals)
        if hits:
            matched_asset_ids.append(asset.asset_id)
            matched_signals.extend(h for h in hits if h not in matched_signals)
    return matched_asset_ids, matched_signals


def suggest_synergy_gaps(
    portfolio: list[SynergyAssetProfile],
    *,
    rules: Optional[list[SynergyRule]] = None,
    min_gap_score: float = 0.10,
) -> SynergyGapReport:
    """
    Analyse an acquirer's portfolio against canonical synergy rules and return
    ranked gap-fill suggestions.

    A gap is identified when the portfolio matches ONE side of a synergy rule
    but not the other.  The gap score reflects how valuable filling that gap
    would be (rule base_score × synergy type weight).

    Args:
        portfolio: List of SynergyAssetProfile objects representing the
                   acquirer's current holdings.
        rules: Override canonical rules (default: all 14 canonical rules).
        min_gap_score: Suppress suggestions below this threshold.

    Returns:
        SynergyGapReport with ranked suggestions and coverage summary.
    """
    graph = SynergyGraph.from_rules(rules=rules)
    active_rules = rules if rules is not None else _CANONICAL_RULES

    # ── Current synergy score ────────────────────────────────────────────────
    from bve.analysis.synergy_graph import score_portfolio_synergy
    current_result = score_portfolio_synergy(portfolio)
    current_score = current_result.total_synergy_score
    covered_types = {e.synergy_type.value for e in current_result.edges}

    # ── Gap detection ────────────────────────────────────────────────────────
    suggestions: list[SynergyGapSuggestion] = []

    for rule in active_rules:
        a_ids, a_signals = _match_one_side(portfolio, rule.asset_a_signals, graph)
        b_ids, b_signals = _match_one_side(portfolio, rule.asset_b_signals, graph)

        a_matched = len(a_ids) > 0
        b_matched = len(b_ids) > 0

        if a_matched == b_matched:
            # Both sides present (already synergized) OR neither side (not relevant)
            continue

        # Exactly one side is present — this is a gap
        type_weight = _SYNERGY_TYPE_WEIGHTS.get(rule.synergy_type, 0.5)
        gap_score = round(rule.base_score * type_weight, 4)

        if gap_score < min_gap_score:
            continue

        if a_matched:
            # Portfolio has side-A; acquirer should add something with side-B signals
            suggestions.append(SynergyGapSuggestion(
                rule_id=rule.rule_id,
                synergy_type=rule.synergy_type,
                present_asset_ids=a_ids,
                present_signals=a_signals,
                missing_signals=rule.asset_b_signals,
                gap_score=gap_score,
                description=rule.description,
                evidence=rule.evidence,
            ))
        else:
            # Portfolio has side-B; acquirer should add something with side-A signals
            # Only suggest if the rule is bidirectional or naturally directional
            if rule.bidirectional:
                suggestions.append(SynergyGapSuggestion(
                    rule_id=rule.rule_id,
                    synergy_type=rule.synergy_type,
                    present_asset_ids=b_ids,
                    present_signals=b_signals,
                    missing_signals=rule.asset_a_signals,
                    gap_score=gap_score,
                    description=rule.description,
                    evidence=rule.evidence,
                ))

    # Sort by gap_score descending
    suggestions.sort(key=lambda s: s.gap_score, reverse=True)

    all_types = {st.value for st in SynergyType}
    uncovered = sorted(all_types - covered_types)

    return SynergyGapReport(
        portfolio_asset_ids=[a.asset_id for a in portfolio],
        current_synergy_score=current_score,
        suggestions=suggestions,
        covered_synergy_types=sorted(covered_types),
        uncovered_synergy_types=uncovered,
    )
