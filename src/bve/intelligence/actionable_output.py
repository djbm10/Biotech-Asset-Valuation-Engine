"""
Wave K — Weekly Actionable Output Generator.

Compresses ranked opportunities into a short, forced-decision list that
the analyst can act on immediately.  The system MUST produce output — even
"no actionable opportunities this week" is a valid, explicit result.

Design principles
-----------------
- Forced output: ``generate()`` always returns a ``WeeklyActionableReport``.
  Silence is never an acceptable result.
- Score versioning: every report logs ``score_version`` and ``score_weights``
  so future analysis can compare scoring regimes over time.
- Recommended vs executed are separate: the report records only what the
  system recommends.  ``DecisionLayer.update_execution()`` records what the
  analyst actually did.
- Full score decomposition: ``ranking_component``, ``thesis_component``, and
  ``opportunity_component`` are stored on each opportunity so downstream
  attribution can determine *why* something ranked high.
- Critic caution → downgrade, not filter: a CAUTION finding changes the
  recommended action from "buy"/"add" to "monitor".  It does not remove the
  opportunity from the output, because opacity is worse than flagged caution.

Score version registry
----------------------
  v1.0   ranking=0.50, thesis=0.30, opportunity=0.20   (initial weights, 2026-Q1)
  v2.0   same base weights + six additive signal layers (catalyst_ev, enrollment,
         phase_correlation, endpoint_z, competitor_impact, capital_risk)

Action taxonomy
---------------
  buy       — open new position; high conviction (composite ≥ 0.70)
  add       — increase existing position; medium conviction (0.50 ≤ composite < 0.70)
  monitor   — watch only; caution flag raised or below buy/add threshold (0.30 ≤ composite < 0.50)
  avoid     — do not act; composite below minimum threshold (< 0.30)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from bve.intelligence.composite_scorer import CompositeScoreContext


# ---------------------------------------------------------------------------
# Score registry — version → weights
# ---------------------------------------------------------------------------

SCORE_VERSIONS: dict[str, dict[str, float]] = {
    "v1.0": {"ranking": 0.50, "thesis": 0.30, "opportunity": 0.20},
    # v2.0 uses the same base weights; the signal adjustment amounts are logged
    # per-opportunity in ActionableOpportunity.signal_adjustments.
    "v2.0": {"ranking": 0.50, "thesis": 0.30, "opportunity": 0.20},
}

CURRENT_SCORE_VERSION = "v1.0"


# ---------------------------------------------------------------------------
# Input: ScoredCandidate
# ---------------------------------------------------------------------------

@dataclass
class ScoredCandidate:
    """
    Minimal input to the actionable generator.

    Callers populate this from whatever ranking / opportunity sources they
    have.  All fields except ``asset_id``, ``ticker``, and ``ranking_score``
    are optional.
    """

    asset_id: str
    ticker: str
    ranking_score: float            # 0.0–1.0, from ranking engine
    opportunity_score: float = 0.0  # 0.0–1.0, from OpportunityScanner
    thesis_strength: Optional[float] = None   # from ThesisTracker.snapshot()
    critic_severity: Optional[str] = None     # "caution" | "warning" | None
    catalyst_description: str = ""
    indication: str = ""
    company_id: str = ""
    extra_risk_flags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Output: ActionableOpportunity
# ---------------------------------------------------------------------------

class ActionableOpportunity(BaseModel):
    """
    One actionable opportunity with full score decomposition.

    Attributes
    ----------
    asset_id, ticker:
        Asset identifiers.
    recommended_action:
        What the system recommends: ``"buy"`` / ``"add"`` / ``"monitor"`` /
        ``"avoid"``.
    recommended_size_pct:
        Suggested portfolio weight (0.0–1.0).
    composite_score:
        Weighted combination of component scores (0.0–1.0).
    ranking_component, thesis_component, opportunity_component:
        Each component's weighted contribution to ``composite_score``.
        They sum to ``composite_score``.
    score_version:
        Version tag of the scoring regime used.
    thesis_strength:
        Raw thesis_strength from ThesisTracker, or None.
    critic_severity:
        Highest CriticAgent severity for this asset, or None.
    risk_flags:
        Short human-readable flags (e.g. "CAUTION: low confidence",
        "weak thesis: 0.30").
    one_line_summary:
        Full context in one sentence.
    """

    model_config = {"frozen": True}

    asset_id: str
    ticker: str
    recommended_action: str
    recommended_size_pct: float
    catalyst_description: str = ""
    composite_score: float
    ranking_component: float
    thesis_component: float
    opportunity_component: float
    score_version: str
    thesis_strength: Optional[float] = None
    critic_severity: Optional[str] = None
    risk_flags: list[str] = Field(default_factory=list)
    one_line_summary: str = ""
    # v2.0 signal attribution — empty for v1.0 runs
    signal_adjustments: dict[str, float] = Field(default_factory=dict)
    signal_adjustment_total: float = 0.0


# ---------------------------------------------------------------------------
# Output: WeeklyActionableReport
# ---------------------------------------------------------------------------

class WeeklyActionableReport(BaseModel):
    """
    Forced weekly decision output.

    Always generated, even when no opportunities meet the threshold.
    ``has_actionable=False`` is explicit — the system never goes silent.

    Attributes
    ----------
    generated_at:
        UTC timestamp.
    week_ending:
        The Monday–Sunday week this report covers.
    score_version:
        Version tag of the scoring weights used.
    score_weights:
        The actual weights used, logged for longitudinal comparison.
    opportunities:
        Up to ``top_n`` opportunities ordered by composite_score descending.
    n_considered:
        Total candidates evaluated.
    n_filtered_by_min_score:
        Candidates dropped because composite < ``min_composite_score``.
    n_elevated_by_critic:
        Candidates whose action was downgraded to ``"monitor"`` due to a
        CAUTION critic finding.
    has_actionable:
        True when at least one opportunity with action ``"buy"`` or ``"add"``
        is in the list.
    """

    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    week_ending: date = Field(default_factory=date.today)
    score_version: str = CURRENT_SCORE_VERSION
    score_weights: dict[str, float] = Field(
        default_factory=lambda: dict(SCORE_VERSIONS[CURRENT_SCORE_VERSION])
    )
    opportunities: list[ActionableOpportunity] = Field(default_factory=list)
    n_considered: int = 0
    n_filtered_by_min_score: int = 0
    n_elevated_by_critic: int = 0
    has_actionable: bool = False


# ---------------------------------------------------------------------------
# ActionableGenerator
# ---------------------------------------------------------------------------

class ActionableGenerator:
    """
    Compresses ranked candidates into a ``WeeklyActionableReport``.

    Parameters
    ----------
    score_version:
        Score regime to use.  Must be a key in ``SCORE_VERSIONS``.
    min_composite_score:
        Candidates below this composite score are filtered out entirely
        (action = ``"avoid"``).
    max_position_pct:
        Maximum recommended size for any single position (0.0–1.0).
    min_position_pct:
        Minimum recommended size when a position is actionable (0.0–1.0).
    """

    def __init__(
        self,
        *,
        score_version: str = CURRENT_SCORE_VERSION,
        min_composite_score: float = 0.0,
        max_position_pct: float = 0.20,
        min_position_pct: float = 0.01,
    ) -> None:
        if score_version not in SCORE_VERSIONS:
            raise ValueError(
                f"Unknown score version {score_version!r}. "
                f"Valid: {sorted(SCORE_VERSIONS)}"
            )
        self.score_version = score_version
        self.weights = SCORE_VERSIONS[score_version]
        self.min_composite_score = min_composite_score
        self.max_position_pct = max_position_pct
        self.min_position_pct = min_position_pct

    def generate(
        self,
        candidates: list[ScoredCandidate],
        *,
        top_n: int = 5,
        week_ending: Optional[date] = None,
        contexts: Optional[dict[str, "CompositeScoreContext"]] = None,
    ) -> WeeklyActionableReport:
        """
        Generate a ``WeeklyActionableReport`` from *candidates*.

        Parameters
        ----------
        candidates:
            List of ``ScoredCandidate`` objects.
        top_n:
            Maximum number of opportunities to include.
        week_ending:
            Week-end date for the report.  Defaults to today.
        contexts:
            Optional dict mapping ``asset_id`` → ``CompositeScoreContext``.
            When provided for an asset, six additional signal layers are
            applied additively to the composite score.  Enables v2.0 scoring.
            Missing context for an asset → signal adjustments are all 0.0.

        Returns
        -------
        WeeklyActionableReport — always populated, never None.
        """
        from bve.intelligence.composite_scorer import CompositeScorer

        n_considered = len(candidates)
        n_filtered = 0
        n_elevated = 0
        results: list[ActionableOpportunity] = []

        # Build the signal scorer lazily — only when contexts are supplied
        scorer = CompositeScorer() if contexts else None
        effective_version = "v2.0" if contexts else self.score_version

        w_r = self.weights["ranking"]
        w_t = self.weights["thesis"]
        w_o = self.weights["opportunity"]

        for cand in candidates:
            thesis_val = cand.thesis_strength if cand.thesis_strength is not None else 0.0

            # Base weighted components (unchanged from v1.0)
            r_comp = w_r * cand.ranking_score
            t_comp = w_t * thesis_val
            o_comp = w_o * cand.opportunity_score
            base_composite = r_comp + t_comp + o_comp

            # Signal adjustments (v2.0 path)
            signal_adj: dict[str, float] = {}
            signal_total = 0.0
            if scorer is not None and contexts is not None:
                ctx = contexts.get(cand.asset_id)
                if ctx is not None:
                    signal_adj = scorer.compute_adjustments(ctx)
                    signal_total = CompositeScorer.total(signal_adj)

            composite = max(0.0, min(1.0, base_composite + signal_total))

            if composite < self.min_composite_score:
                n_filtered += 1
                continue

            # Determine action
            action, was_elevated = self._determine_action(
                composite, cand.critic_severity
            )
            if was_elevated:
                n_elevated += 1

            # Sizing: proportional to composite, clipped
            raw_size = composite * self.max_position_pct
            size = max(self.min_position_pct, min(self.max_position_pct, raw_size))
            if action in ("monitor", "avoid"):
                size = 0.0

            risk_flags = self._build_risk_flags(cand, composite)

            summary = self._build_summary(cand, action, composite)

            results.append(ActionableOpportunity(
                asset_id=cand.asset_id,
                ticker=cand.ticker,
                recommended_action=action,
                recommended_size_pct=round(size, 4),
                catalyst_description=cand.catalyst_description,
                composite_score=round(composite, 4),
                ranking_component=round(r_comp, 4),
                thesis_component=round(t_comp, 4),
                opportunity_component=round(o_comp, 4),
                score_version=effective_version,
                thesis_strength=cand.thesis_strength,
                critic_severity=cand.critic_severity,
                risk_flags=risk_flags,
                one_line_summary=summary,
                signal_adjustments=signal_adj,
                signal_adjustment_total=round(signal_total, 4),
            ))

        # Sort by composite descending, take top_n
        results.sort(key=lambda x: x.composite_score, reverse=True)
        results = results[:top_n]

        has_actionable = any(r.recommended_action in ("buy", "add") for r in results)

        return WeeklyActionableReport(
            week_ending=week_ending or date.today(),
            score_version=effective_version,
            score_weights=dict(self.weights),
            opportunities=results,
            n_considered=n_considered,
            n_filtered_by_min_score=n_filtered,
            n_elevated_by_critic=n_elevated,
            has_actionable=has_actionable,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _determine_action(
        self,
        composite: float,
        critic_severity: Optional[str],
    ) -> tuple[str, bool]:
        """
        Return ``(action, was_elevated_by_critic)``.

        Critic CAUTION downgrades buy/add → monitor.
        """
        if composite >= 0.70:
            base_action = "buy"
        elif composite >= 0.50:
            base_action = "add"
        elif composite >= 0.30:
            base_action = "monitor"
        else:
            base_action = "avoid"

        was_elevated = False
        if critic_severity == "caution" and base_action in ("buy", "add"):
            base_action = "monitor"
            was_elevated = True

        return base_action, was_elevated

    @staticmethod
    def _build_risk_flags(cand: ScoredCandidate, composite: float) -> list[str]:
        flags: list[str] = []
        if cand.critic_severity == "caution":
            flags.append("CAUTION: critic flagged high-severity concern")
        elif cand.critic_severity == "warning":
            flags.append("WARNING: critic flagged moderate concern")
        if cand.thesis_strength is not None and cand.thesis_strength < 0.40:
            flags.append(f"weak thesis: {cand.thesis_strength:.0%}")
        if composite < 0.40:
            flags.append(f"borderline score: {composite:.2f}")
        flags.extend(cand.extra_risk_flags)
        return flags

    @staticmethod
    def _build_summary(
        cand: ScoredCandidate,
        action: str,
        composite: float,
    ) -> str:
        parts = [f"{cand.ticker}: {action.upper()}"]
        if cand.catalyst_description:
            parts.append(cand.catalyst_description)
        if cand.indication:
            parts.append(cand.indication)
        if cand.thesis_strength is not None:
            parts.append(f"thesis={cand.thesis_strength:.0%}")
        parts.append(f"score={composite:.2f}")
        return " | ".join(parts)
