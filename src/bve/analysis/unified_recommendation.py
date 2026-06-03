"""Entry point that assembles a signal bundle from available stores and runs fusion."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from bve.analysis.signal_fusion import AssetSignalBundle, FusedSignalCard, SignalFusionEngine

if TYPE_CHECKING:
    from bve.persistence.gap_fill_store import GapFillStore


class UnifiedRecommendationEngine:
    """
    Assemble an AssetSignalBundle from available data stores and run SignalFusionEngine.

    All inputs are optional — the engine degrades gracefully when sources are missing.
    """

    def __init__(self, store: Optional["GapFillStore"] = None) -> None:  # type: ignore[name-defined]
        self._store = store
        self._fusion = SignalFusionEngine()

    def recommend(
        self,
        asset_id: str,
        ticker: str,
        *,
        # Optional overrides — callers can pass pre-computed signals directly
        model_pos: Optional[float] = None,
        model_ev_millions: Optional[float] = None,
        market_ev_millions: Optional[float] = None,
        science_score_override: Optional[float] = None,
        financing_risk_override: Optional[float] = None,
        catalyst_setup_score: Optional[float] = None,
        days_to_next_catalyst: Optional[int] = None,
        current_position_pct: float = 0.0,
    ) -> FusedSignalCard:
        """
        Build an AssetSignalBundle from store + overrides, then fuse.

        When store is available:
        - pull latest implied_expectation for market signals
        - pull latest financing_forecast for financing signals
        - pull active variant_thesis for thesis signals

        Override kwargs always take precedence over stored values.
        """
        bundle_kwargs: dict = {
            "asset_id": asset_id,
            "ticker": ticker,
            "as_of": datetime.now(timezone.utc),
            "current_position_pct": current_position_pct,
        }

        # Pull from store if available
        if self._store is not None:
            imp = self._store.get_latest_implied_expectation(asset_id)
            if imp is not None:
                bundle_kwargs.update(
                    {
                        "model_pos": imp.model_pos,
                        "implied_pos": imp.implied_pos,
                        "pos_gap": (
                            (imp.model_pos or 0) - (imp.implied_pos or 0)
                            if (imp.model_pos and imp.implied_pos)
                            else None
                        ),
                        "model_peak_sales_millions": imp.model_peak_sales_millions,
                        "implied_peak_sales_millions": imp.implied_peak_sales_millions,
                        "model_ev_millions": imp.model_rnpv_millions,
                        "market_ev_millions": imp.current_ev_millions,
                        "ev_gap_pct": (
                            (imp.model_rnpv_millions - imp.current_ev_millions)
                            / imp.current_ev_millions
                            if imp.model_rnpv_millions
                            and imp.current_ev_millions
                            and imp.current_ev_millions != 0
                            else None
                        ),
                    }
                )

            ff = self._store.get_latest_financing_forecast(asset_id)
            if ff is not None:
                bundle_kwargs.update(
                    {
                        "months_runway": ff.runway_months_base,
                        "financing_risk_score": (
                            1.0 - min(1.0, ff.runway_months_base / 24.0)
                            if ff.runway_months_base >= 0
                            else 0.9
                        ),
                    }
                )

            thesis = self._store.get_active_variant_thesis(asset_id)
            if thesis is not None:
                bundle_kwargs.update(
                    {
                        "thesis_confidence": thesis.confidence_score,
                        "thesis_conviction": thesis.overall_conviction,
                        "active_kill_criteria_count": sum(
                            1
                            for d in thesis.deltas
                            for k in d.kill_criteria
                            if k.is_triggered
                        ),
                    }
                )

        # Apply overrides
        if model_pos is not None:
            bundle_kwargs["model_pos"] = model_pos
        if model_ev_millions is not None:
            bundle_kwargs["model_ev_millions"] = model_ev_millions
        if market_ev_millions is not None:
            bundle_kwargs["market_ev_millions"] = market_ev_millions
            ev = bundle_kwargs.get("model_ev_millions")
            if ev and market_ev_millions != 0:
                bundle_kwargs["ev_gap_pct"] = (ev - market_ev_millions) / market_ev_millions
        if science_score_override is not None:
            bundle_kwargs["science_score"] = science_score_override
        if financing_risk_override is not None:
            bundle_kwargs["financing_risk_score"] = financing_risk_override
        if catalyst_setup_score is not None:
            bundle_kwargs["best_catalyst_setup_score"] = catalyst_setup_score
        if days_to_next_catalyst is not None:
            bundle_kwargs["days_to_next_catalyst"] = days_to_next_catalyst

        bundle = AssetSignalBundle(**bundle_kwargs)
        return self._fusion.fuse(bundle)

    def recommend_universe(
        self,
        assets: list[dict],  # list of {"asset_id": str, "ticker": str, ...override kwargs}
    ) -> list[FusedSignalCard]:
        cards = []
        for a in assets:
            a = dict(a)  # avoid mutating caller's dict
            asset_id = a.pop("asset_id")
            ticker = a.pop("ticker")
            cards.append(self.recommend(asset_id, ticker, **a))
        return sorted(cards, key=lambda c: c.composite_score, reverse=True)
