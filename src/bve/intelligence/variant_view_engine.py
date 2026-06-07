"""Phase J structured variant-view engine."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

from bve.intelligence.market_expectations import (
    MarketExpectationComparison,
    MarketExpectationComparisonValue,
)
from bve.intelligence.thesis_tracker import ThesisSnapshot


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VariantViewModuleOutput(BaseModel):
    value: Any
    confidence: float = Field(ge=0.0, le=1.0)
    provenance: list[str] = Field(default_factory=list)
    freshness: datetime
    explainability: str
    downstream_dependencies: list[str] = Field(default_factory=list)


class VariantDelta(BaseModel):
    dimension: str
    consensus_assumption: str
    model_assumption: str
    delta: str
    evidence_supporting_delta: list[str] = Field(default_factory=list)
    falsifier: str
    expected_time_to_resolution_days: Optional[int] = Field(default=None, ge=0)
    confidence: float = Field(ge=0.0, le=1.0)


class ThesisCard(BaseModel):
    headline: str
    market_is_pricing: str
    model_thinks: str
    gap_exists_because: str
    catalysts_to_resolve: list[str] = Field(default_factory=list)


class VariantViewValue(BaseModel):
    asset_id: str
    company_id: Optional[str] = None
    thesis_card: ThesisCard
    deltas: list[VariantDelta] = Field(default_factory=list)


class VariantViewAssessment(BaseModel):
    asset_id: str
    output: VariantViewModuleOutput
    plain_english_summary: str


class VariantViewEngine:
    """Turn model-vs-market disagreement into structured thesis deltas."""

    def build(
        self,
        *,
        asset_id: str,
        company_id: Optional[str],
        market_expectation: MarketExpectationComparison,
        thesis_snapshot: Optional[ThesisSnapshot] = None,
        catalyst_calendar: Optional[list[dict[str, Any]]] = None,
        now: Optional[datetime] = None,
    ) -> VariantViewAssessment:
        now = now or _utcnow()
        market_value = MarketExpectationComparisonValue.model_validate(market_expectation.output.value)
        catalysts = list(catalyst_calendar or [])
        deltas = self._build_deltas(market_value, thesis_snapshot, catalysts, now)
        thesis_card = self._build_card(market_value, thesis_snapshot, deltas, catalysts)
        confidence = self._confidence(market_value, thesis_snapshot, deltas)
        value = VariantViewValue(
            asset_id=asset_id,
            company_id=company_id,
            thesis_card=thesis_card,
            deltas=deltas,
        )
        output = VariantViewModuleOutput(
            value=value.model_dump(),
            confidence=confidence,
            provenance=self._provenance(market_expectation, thesis_snapshot),
            freshness=now,
            explainability=(
                "Variant view encodes each disagreement as consensus assumption, model assumption, "
                "delta, supporting evidence, falsifier, timing, and confidence."
            ),
            downstream_dependencies=[
                "catalyst_payoff_trees",
                "portfolio_decision_engine",
                "daily_scanner",
            ],
        )
        summary = (
            f"{asset_id} variant view tracks {len(deltas)} explicit disagreement(s); "
            f"headline: {thesis_card.headline}"
        )
        return VariantViewAssessment(
            asset_id=asset_id,
            output=output,
            plain_english_summary=summary,
        )

    def _build_deltas(
        self,
        market_value: MarketExpectationComparisonValue,
        thesis_snapshot: Optional[ThesisSnapshot],
        catalyst_calendar: list[dict[str, Any]],
        now: datetime,
    ) -> list[VariantDelta]:
        deltas: list[VariantDelta] = []
        if market_value.model_pos is not None and market_value.implied_pos is not None:
            deltas.append(
                self._delta(
                    dimension="PoS",
                    consensus=f"Market-implied PoS {market_value.implied_pos:.0%}",
                    model=f"Model PoS {market_value.model_pos:.0%}",
                    delta=f"{(market_value.model_pos - market_value.implied_pos):+.1%}",
                    evidence=self._claim_evidence(thesis_snapshot, limit=3),
                    falsifier=self._falsifier(thesis_snapshot, fallback="A readout or regulatory outcome that validates the market view."),
                    eta=self._resolution_days(catalyst_calendar, now),
                    confidence=self._delta_confidence(market_value.pos_delta, thesis_snapshot),
                )
            )
        if (
            market_value.model_peak_sales_millions is not None
            and market_value.implied_peak_sales_millions is not None
        ):
            deltas.append(
                self._delta(
                    dimension="Peak sales",
                    consensus=f"Market-implied peak sales ${market_value.implied_peak_sales_millions:,.0f}M",
                    model=f"Model peak sales ${market_value.model_peak_sales_millions:,.0f}M",
                    delta=f"${market_value.peak_sales_delta_millions:+,.0f}M",
                    evidence=self._peak_sales_evidence(thesis_snapshot),
                    falsifier="Launch access, uptake, or pricing data that converges to the market view.",
                    eta=self._resolution_days(catalyst_calendar, now),
                    confidence=self._delta_confidence(market_value.peak_sales_delta_millions, thesis_snapshot),
                )
            )
        if (
            market_value.model_dilution_pct is not None
            and market_value.implied_dilution_pct is not None
        ):
            deltas.append(
                self._delta(
                    dimension="Financing",
                    consensus=f"Market-implied dilution {market_value.implied_dilution_pct:.0%}",
                    model=f"Model dilution {market_value.model_dilution_pct:.0%}",
                    delta=f"{(market_value.model_dilution_pct - market_value.implied_dilution_pct):+.1%}",
                    evidence=["Financing engine raise timing and dilution band."],
                    falsifier="A financing event priced inside the model dilution band.",
                    eta=self._resolution_days(catalyst_calendar, now),
                    confidence=self._delta_confidence(market_value.dilution_delta, thesis_snapshot),
                )
            )
        return deltas

    def _build_card(
        self,
        market_value: MarketExpectationComparisonValue,
        thesis_snapshot: Optional[ThesisSnapshot],
        deltas: list[VariantDelta],
        catalyst_calendar: list[dict[str, Any]],
    ) -> ThesisCard:
        market_text = (
            f"PoS {market_value.implied_pos:.0%}, peak sales ${market_value.implied_peak_sales_millions:,.0f}M"
            if market_value.implied_pos is not None and market_value.implied_peak_sales_millions is not None
            else "an incomplete expectation set"
        )
        model_text = (
            f"PoS {market_value.model_pos:.0%}, peak sales ${market_value.model_peak_sales_millions:,.0f}M"
            if market_value.model_pos is not None and market_value.model_peak_sales_millions is not None
            else "a different intrinsic profile"
        )
        because = (
            "; ".join(self._claim_evidence(thesis_snapshot, limit=3))
            if thesis_snapshot is not None and self._claim_evidence(thesis_snapshot, limit=3)
            else "our evidence stack differs from the market on probability, commercialization, or financing."
        )
        catalyst_labels = [
            str(item.get("description") or item.get("label") or item.get("date") or "catalyst")
            for item in catalyst_calendar[:3]
        ]
        headline = deltas[0].dimension if deltas else "Variant view"
        return ThesisCard(
            headline=f"{headline} disagreement is the primary variant",
            market_is_pricing=market_text,
            model_thinks=model_text,
            gap_exists_because=because,
            catalysts_to_resolve=catalyst_labels,
        )

    @staticmethod
    def _delta(
        *,
        dimension: str,
        consensus: str,
        model: str,
        delta: str,
        evidence: list[str],
        falsifier: str,
        eta: Optional[int],
        confidence: float,
    ) -> VariantDelta:
        return VariantDelta(
            dimension=dimension,
            consensus_assumption=consensus,
            model_assumption=model,
            delta=delta,
            evidence_supporting_delta=evidence,
            falsifier=falsifier,
            expected_time_to_resolution_days=eta,
            confidence=confidence,
        )

    @staticmethod
    def _claim_evidence(thesis_snapshot: Optional[ThesisSnapshot], *, limit: int) -> list[str]:
        if thesis_snapshot is None:
            return []
        confirmed = thesis_snapshot.confirmed_claims[:limit]
        return [claim.assertion for claim in confirmed if claim.assertion]

    @staticmethod
    def _peak_sales_evidence(thesis_snapshot: Optional[ThesisSnapshot]) -> list[str]:
        evidence = VariantViewEngine._claim_evidence(thesis_snapshot, limit=2)
        if not evidence:
            return ["Market-expectation engine shows the market is not pricing the modeled commercial profile."]
        return evidence

    @staticmethod
    def _falsifier(thesis_snapshot: Optional[ThesisSnapshot], *, fallback: str) -> str:
        if thesis_snapshot is None:
            return fallback
        open_claims = [claim.assertion for claim in thesis_snapshot.open_claims if claim.assertion]
        if not open_claims:
            return fallback
        return f"If the next claim fails to resolve favorably: {open_claims[0]}"

    @staticmethod
    def _resolution_days(catalyst_calendar: list[dict[str, Any]], now: datetime) -> Optional[int]:
        candidates: list[date] = []
        for item in catalyst_calendar:
            raw = item.get("date") or item.get("expected_date")
            if not raw:
                continue
            try:
                candidates.append(date.fromisoformat(str(raw)[:10]))
            except ValueError:
                continue
        if not candidates:
            return None
        nearest = min(candidates)
        delta = (nearest - now.date()).days
        return max(0, delta)

    @staticmethod
    def _delta_confidence(delta_value: Optional[float], thesis_snapshot: Optional[ThesisSnapshot]) -> float:
        base = 0.55 if delta_value is not None else 0.40
        if thesis_snapshot is not None and thesis_snapshot.weighted_thesis_strength is not None:
            base += min(0.30, thesis_snapshot.weighted_thesis_strength * 0.30)
        return round(min(0.95, base), 4)

    @staticmethod
    def _confidence(
        market_value: MarketExpectationComparisonValue,
        thesis_snapshot: Optional[ThesisSnapshot],
        deltas: list[VariantDelta],
    ) -> float:
        confidence = 0.45
        if market_value.implied_pos is not None:
            confidence += 0.15
        if market_value.implied_peak_sales_millions is not None:
            confidence += 0.15
        if thesis_snapshot is not None and thesis_snapshot.weighted_thesis_strength is not None:
            confidence += min(0.15, thesis_snapshot.weighted_thesis_strength * 0.15)
        if deltas:
            confidence += 0.05
        return round(min(0.95, confidence), 4)

    @staticmethod
    def _provenance(
        market_expectation: MarketExpectationComparison,
        thesis_snapshot: Optional[ThesisSnapshot],
    ) -> list[str]:
        provenance = ["market_expectation_engine"]
        provenance.extend(market_expectation.output.provenance)
        if thesis_snapshot is not None:
            provenance.append(f"thesis_snapshot:{thesis_snapshot.asset_id}")
        return provenance
