"""Validate curated acquirer profiles against historical public biotech deals."""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median
import yaml
from pydantic import BaseModel, Field

from bve.intelligence.acquirer_fit import (
    AcquirerFitCandidate,
    AcquirerFitConfig,
    AcquirerFitEngine,
    AcquirerFitIntegrationConfig,
)
from bve.intelligence.acquirer_profiles import AcquirerProfile, AcquirerProfileLoader
from bve.intelligence.comparable_deals import ComparableDealLoader, ComparableDealMatcher
from bve.pipeline.watchlist_runner import WatchlistAsset, load_watchlist_config


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _norm_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).strip().lower().replace("_", " ").split())
    return normalized or None


def _norm_ticker(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized or None


class HistoricalAcquisitionDeal(BaseModel):
    """One public-company deal used to validate acquirer profile quality."""

    target_name: str
    target_ticker: str
    acquirer: str
    announcement_date: date
    headline_value_millions: float | None = None
    lead_asset: str | None = None
    indication: str | None = None
    therapeutic_area: str | None = None
    phase_at_acquisition: str | None = None
    notes: str | None = None

    @property
    def normalized_ticker(self) -> str:
        return _norm_ticker(self.target_ticker) or self.target_ticker


class DealProfileValidationRow(BaseModel):
    """One ranked validation result for a historical takeout target."""

    announcement_date: date
    target_name: str
    ticker: str
    candidate_source: str
    actual_acquirer_id: str
    actual_acquirer_name: str
    actual_acquirer_rank: int
    actual_acquirer_fit_score: float
    actual_acquirer_raw_fit_score: float
    actual_acquirer_matched_gap: str | None = None
    predicted_acquirer_id: str
    predicted_acquirer_name: str
    predicted_fit_score: float
    predicted_matched_gap: str | None = None
    top1_hit: bool
    top3_hit: bool
    stage: str | None = None
    therapeutic_area: str | None = None
    modality: str | None = None
    enterprise_value_millions: float | None = None
    notes: list[str] = Field(default_factory=list)


class DealProfileValidationAcquirerStat(BaseModel):
    """Per-acquirer summary of historical validation performance."""

    acquirer_id: str
    acquirer_name: str
    n_deals: int
    top1_hits: int
    top3_hits: int
    top1_rate: float
    top3_rate: float
    median_rank: float | None = None


class DealProfileValidationResult(BaseModel):
    """Aggregate validation result for a set of curated acquirer profiles."""

    evaluated_at: datetime = Field(default_factory=_utcnow)
    profiles_path: str
    deal_universe_path: str
    watchlist_path: str | None = None
    n_public_tickered_deals: int
    n_profile_covered_deals: int
    n_scored_deals: int
    n_watchlist_backed: int
    n_fallback_only: int
    top1_hits: int
    top3_hits: int
    top1_rate: float
    top3_rate: float
    median_actual_rank: float | None = None
    rows: list[DealProfileValidationRow] = Field(default_factory=list)
    by_acquirer: list[DealProfileValidationAcquirerStat] = Field(default_factory=list)

    def write_csv(self, path: str | Path) -> Path:
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(self.rows[0].model_dump(mode="json").keys()) if self.rows else []
        with out_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            if fieldnames:
                writer.writeheader()
                for row in self.rows:
                    writer.writerow(row.model_dump(mode="json"))
        return out_path


class AcquirerProfileDealValidator:
    """Retroactively rank real deal targets against current curated acquirer profiles."""

    def __init__(
        self,
        *,
        profiles_path: str | Path = "examples/research/acquirer_profiles",
        deal_universe_path: str | Path = "research/mna/deal_universe_2020_2026.yaml",
        comparable_deals_path: str | Path = "research/mna/comparable_deals.yaml",
        watchlist_path: str | Path | None = None,
        knowledge_store=None,
        context_provider=None,
    ) -> None:
        self.profiles_path = str(profiles_path)
        self.deal_universe_path = str(deal_universe_path)
        self.comparable_deals_path = str(comparable_deals_path)
        self.watchlist_path = str(watchlist_path) if watchlist_path is not None else None
        self.dataset = AcquirerProfileLoader.load(self.profiles_path)
        self.profile_by_id = {
            profile.acquirer_id: profile
            for profile in self.dataset.acquirers
        }
        self.watchlist_by_ticker = self._load_watchlist(self.watchlist_path)
        self.comparable_deals = ComparableDealLoader.load(self.comparable_deals_path).deals
        self.fit_engine = AcquirerFitEngine(
            knowledge_store=knowledge_store,
            context_provider=context_provider,
            fit_config=AcquirerFitConfig(require_acquisition_readiness=False),
            integration_config=AcquirerFitIntegrationConfig(
                acquirer_profiles_path=self.profiles_path,
                comparable_deals_path=self.comparable_deals_path,
                top_n=max(len(self.dataset.acquirers), 1),
                acquisition_threshold=0.000001,
                require_acquisition_readiness=False,
                persist_acquisition_snapshots=False,
            ),
        )

    def validate(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> DealProfileValidationResult:
        deals = self._load_deals(self.deal_universe_path)
        public_tickered_deals = [
            deal
            for deal in deals
            if (start_date is None or deal.announcement_date >= start_date)
            and (end_date is None or deal.announcement_date <= end_date)
        ]
        covered_deals = [
            deal for deal in public_tickered_deals if self._resolve_actual_profile(deal.acquirer) is not None
        ]

        rows: list[DealProfileValidationRow] = []
        watchlist_backed = 0
        fallback_only = 0

        for deal in covered_deals:
            actual_profile = self._resolve_actual_profile(deal.acquirer)
            if actual_profile is None:
                continue

            candidate, candidate_source, candidate_notes = self._build_candidate_for_deal(deal)
            if candidate_source == "watchlist_config":
                watchlist_backed += 1
            else:
                fallback_only += 1

            comparable_analysis = ComparableDealMatcher.analyze(
                asset_indication=candidate.indication,
                asset_therapeutic_area=candidate.therapeutic_area,
                asset_stage=candidate.stage,
                asset_ev_to_peak_sales=candidate.ev_to_peak_sales,
                deals=self.comparable_deals,
            )
            scores = [
                self.fit_engine.scorer.score_target(
                    acquirer=profile,
                    target=candidate,
                    comparable_analysis=comparable_analysis,
                )
                for profile in self.dataset.acquirers
            ]
            scores.sort(
                key=lambda score: (
                    -score.fit_score,
                    -score.raw_fit_score,
                    score.acquirer_id,
                )
            )
            actual_rank = next(
                idx + 1
                for idx, score in enumerate(scores)
                if score.acquirer_id == actual_profile.acquirer_id
            )
            actual_score = next(
                score for score in scores if score.acquirer_id == actual_profile.acquirer_id
            )
            predicted = scores[0]

            rows.append(
                DealProfileValidationRow(
                    announcement_date=deal.announcement_date,
                    target_name=deal.target_name,
                    ticker=deal.normalized_ticker,
                    candidate_source=candidate_source,
                    actual_acquirer_id=actual_profile.acquirer_id,
                    actual_acquirer_name=actual_profile.company_name,
                    actual_acquirer_rank=actual_rank,
                    actual_acquirer_fit_score=round(float(actual_score.fit_score), 6),
                    actual_acquirer_raw_fit_score=round(float(actual_score.raw_fit_score), 6),
                    actual_acquirer_matched_gap=actual_score.matched_therapeutic_gap,
                    predicted_acquirer_id=predicted.acquirer_id,
                    predicted_acquirer_name=self.profile_by_id[predicted.acquirer_id].company_name,
                    predicted_fit_score=round(float(predicted.fit_score), 6),
                    predicted_matched_gap=predicted.matched_therapeutic_gap,
                    top1_hit=actual_rank == 1,
                    top3_hit=actual_rank <= 3,
                    stage=candidate.stage,
                    therapeutic_area=candidate.therapeutic_area,
                    modality=candidate.modality,
                    enterprise_value_millions=candidate.enterprise_value_millions,
                    notes=candidate_notes,
                )
            )

        rows.sort(
            key=lambda row: (
                row.announcement_date,
                row.actual_acquirer_rank,
                row.ticker,
            )
        )
        top1_hits = sum(1 for row in rows if row.top1_hit)
        top3_hits = sum(1 for row in rows if row.top3_hit)
        by_acquirer = self._summarize_by_acquirer(rows)

        return DealProfileValidationResult(
            profiles_path=self.profiles_path,
            deal_universe_path=self.deal_universe_path,
            watchlist_path=self.watchlist_path,
            n_public_tickered_deals=len(public_tickered_deals),
            n_profile_covered_deals=len(covered_deals),
            n_scored_deals=len(rows),
            n_watchlist_backed=watchlist_backed,
            n_fallback_only=fallback_only,
            top1_hits=top1_hits,
            top3_hits=top3_hits,
            top1_rate=round(top1_hits / len(rows), 6) if rows else 0.0,
            top3_rate=round(top3_hits / len(rows), 6) if rows else 0.0,
            median_actual_rank=float(median([row.actual_acquirer_rank for row in rows])) if rows else None,
            rows=rows,
            by_acquirer=by_acquirer,
        )

    def _build_candidate_for_deal(
        self,
        deal: HistoricalAcquisitionDeal,
    ) -> tuple[AcquirerFitCandidate, str, list[str]]:
        ticker = deal.normalized_ticker
        watchlist_asset = self.watchlist_by_ticker.get(ticker)
        notes: list[str] = []
        if watchlist_asset is not None and watchlist_asset.valuation_config:
            as_of = max(deal.announcement_date - timedelta(days=1), date(2000, 1, 1))
            acquisition_row = self.fit_engine.acquisition_screener._screen_asset(
                watchlist_asset,
                snapshot_date=as_of,
                comparable_deals=self.comparable_deals,
            )
            candidate = self.fit_engine._build_candidate(
                asset=watchlist_asset,
                acquisition_row=acquisition_row,
            )
            update: dict[str, object] = {}
            if candidate.enterprise_value_millions is None and deal.headline_value_millions is not None:
                update["enterprise_value_millions"] = float(deal.headline_value_millions)
                notes.append("headline_value_used_for_enterprise_value")
            if candidate.model_rnpv_millions is None and deal.headline_value_millions is not None:
                update["model_rnpv_millions"] = float(deal.headline_value_millions)
            if candidate.stage is None and deal.phase_at_acquisition is not None:
                update["stage"] = _normalize_deal_stage(deal.phase_at_acquisition)
            refined_therapeutic_area = _refine_watchlist_therapeutic_area(
                existing=candidate.therapeutic_area,
                inferred=deal.therapeutic_area,
            )
            if (
                refined_therapeutic_area is not None
                and refined_therapeutic_area != candidate.therapeutic_area
            ):
                update["therapeutic_area"] = refined_therapeutic_area
                notes.append("fallback_therapeutic_area_inference")
            if candidate.indication is None and deal.indication is not None:
                update["indication"] = deal.indication
            inferred_modality = _infer_modality_from_deal(deal)
            refined_modality = _refine_watchlist_modality(
                existing=candidate.modality,
                inferred=inferred_modality,
            )
            if refined_modality is not None and refined_modality != candidate.modality:
                update["modality"] = refined_modality
                notes.append("fallback_modality_inference")
            merged_priority_tags = list(candidate.priority_tags)
            for value in [
                deal.indication,
                deal.lead_asset,
            ]:
                if value and value not in merged_priority_tags:
                    merged_priority_tags.append(value)
            if merged_priority_tags != list(candidate.priority_tags):
                update["priority_tags"] = merged_priority_tags
            if update:
                candidate = candidate.model_copy(update=update)
            return candidate, "watchlist_config", notes

        inferred_modality = _infer_modality_from_deal(deal)
        if inferred_modality is not None:
            notes.append("fallback_modality_inference")
        candidate = AcquirerFitCandidate(
            asset_id=f"deal-{ticker.lower()}",
            company_name=deal.target_name,
            ticker=ticker,
            therapeutic_area=_normalize_deal_therapeutic_area(deal.therapeutic_area),
            indication=deal.indication,
            modality=inferred_modality,
            stage=_normalize_deal_stage(deal.phase_at_acquisition),
            model_rnpv_millions=deal.headline_value_millions,
            enterprise_value_millions=deal.headline_value_millions,
            acquisition_ready=True,
            priority_tags=[
                value
                for value in [
                    deal.indication,
                    deal.lead_asset,
                ]
                if value
            ],
        )
        return candidate, "deal_universe_fallback", notes

    def _resolve_actual_profile(self, acquirer_name: str) -> AcquirerProfile | None:
        normalized = _norm_text(acquirer_name)
        if normalized is None:
            return None
        for profile in self.dataset.acquirers:
            aliases = {
                _norm_text(profile.acquirer_id),
                _norm_text(profile.company_name),
                _norm_text(profile.ticker),
            }
            if normalized in aliases:
                return profile
        return None

    @staticmethod
    def _load_watchlist(path: str | None) -> dict[str, WatchlistAsset]:
        if path is None:
            return {}
        config = load_watchlist_config(path)
        by_ticker: dict[str, WatchlistAsset] = {}
        for asset in getattr(config, "watchlist", []):
            ticker = _norm_ticker(getattr(asset, "ticker", None))
            if ticker is not None:
                by_ticker[ticker] = asset
        return by_ticker

    @staticmethod
    def _load_deals(path: str | Path) -> list[HistoricalAcquisitionDeal]:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        deals = raw.get("deals", []) if isinstance(raw, dict) else []
        loaded: list[HistoricalAcquisitionDeal] = []
        for item in deals:
            ticker = _norm_ticker(item.get("target_ticker"))
            announcement_date = item.get("announcement_date")
            if not ticker or not announcement_date:
                continue
            loaded.append(
                HistoricalAcquisitionDeal(
                    target_name=str(item.get("target_name") or ticker),
                    target_ticker=ticker,
                    acquirer=str(item.get("acquirer") or "unknown"),
                    announcement_date=date.fromisoformat(str(announcement_date)[:10]),
                    headline_value_millions=(
                        float(item["headline_value_millions"])
                        if item.get("headline_value_millions") is not None
                        else None
                    ),
                    lead_asset=item.get("lead_asset"),
                    indication=item.get("indication"),
                    therapeutic_area=item.get("therapeutic_area"),
                    phase_at_acquisition=item.get("phase_at_acquisition"),
                    notes=item.get("notes"),
                )
            )
        return loaded

    def _summarize_by_acquirer(
        self,
        rows: list[DealProfileValidationRow],
    ) -> list[DealProfileValidationAcquirerStat]:
        grouped: dict[str, list[DealProfileValidationRow]] = {}
        for row in rows:
            grouped.setdefault(row.actual_acquirer_id, []).append(row)

        stats: list[DealProfileValidationAcquirerStat] = []
        for acquirer_id, bucket in grouped.items():
            top1_hits = sum(1 for row in bucket if row.top1_hit)
            top3_hits = sum(1 for row in bucket if row.top3_hit)
            stats.append(
                DealProfileValidationAcquirerStat(
                    acquirer_id=acquirer_id,
                    acquirer_name=self.profile_by_id[acquirer_id].company_name,
                    n_deals=len(bucket),
                    top1_hits=top1_hits,
                    top3_hits=top3_hits,
                    top1_rate=round(top1_hits / len(bucket), 6),
                    top3_rate=round(top3_hits / len(bucket), 6),
                    median_rank=float(median([row.actual_acquirer_rank for row in bucket])),
                )
            )
        stats.sort(key=lambda stat: (-stat.top1_rate, -stat.n_deals, stat.acquirer_id))
        return stats


def _normalize_deal_stage(value: str | None) -> str | None:
    normalized = _norm_text(value)
    if normalized is None:
        return None
    if "approved" in normalized or "commercial" in normalized:
        return "approved"
    if "nda" in normalized or "bla" in normalized or "filing" in normalized:
        return "nda_bla"
    if "phase 3" in normalized or "phase iii" in normalized or "pivotal" in normalized:
        return "phase_3"
    if "phase 2" in normalized or "phase ii" in normalized or "2b" in normalized:
        return "phase_2"
    if "phase 1" in normalized or "phase i" in normalized or "1b" in normalized:
        return "phase_1"
    return normalized.replace(" ", "_")


def _infer_modality_from_deal(deal: HistoricalAcquisitionDeal) -> str | None:
    search_text = " ".join(
        value
        for value in [
            deal.target_name,
            deal.lead_asset,
            deal.indication,
            deal.therapeutic_area,
            deal.notes,
        ]
        if value
    ).lower()
    if not search_text:
        return None
    normalized = search_text.replace("-", " ")
    if "antibody drug conjugate" in normalized or "adc" in normalized:
        return "adc"
    if any(token in normalized for token in ["radiopharmaceutical", "radioligand", "lutetium", "actinium"]):
        return "radiopharmaceutical"
    if "mrna" in normalized:
        return "mRNA"
    if any(token in normalized for token in ["rna", "sirna", "oligo", "aso"]):
        return "rna"
    if any(token in normalized for token in ["gene therapy", "genetic", "editing", "one time", "aav"]):
        return "genetic_medicine"
    if "cell therapy" in normalized or "car t" in normalized:
        return "cell_therapy"
    if "protein" in normalized:
        return "protein"
    if "peptide" in normalized:
        return "peptide"
    if "antibody" in normalized or "biologic" in normalized:
        return "biologic"
    if "oral" in normalized:
        return "oral_small_molecule"
    if any(token in normalized for token in ["small molecule", "cgrp", "inhibitor", "agonist", "antagonist"]):
        return "small_molecule"
    return None


def _refine_watchlist_modality(
    *,
    existing: str | None,
    inferred: str | None,
) -> str | None:
    if inferred is None:
        return None
    if existing is None:
        return inferred
    if existing == "small_molecule" and inferred == "oral_small_molecule":
        return inferred
    if existing == "small_molecule" and inferred in {
        "adc",
        "biologic",
        "genetic_medicine",
        "cell_therapy",
        "radiopharmaceutical",
        "mRNA",
        "rna",
        "protein",
        "peptide",
    }:
        return inferred
    return existing


def _normalize_deal_therapeutic_area(value: str | None) -> str | None:
    normalized = _norm_text(value)
    if normalized is None:
        return None
    if "immunology" in normalized:
        return "immunology"
    if "nephrology" in normalized or "kidney" in normalized or "renal" in normalized:
        return "kidney_disease"
    if "hepatology" in normalized or "liver" in normalized or "hepatic" in normalized:
        return "liver_disease"
    if "neuroscience" in normalized or "neuro" in normalized or "cns" in normalized:
        return "neuroscience"
    if "respiratory" in normalized or "pulmonary" in normalized:
        return "respiratory"
    if "rare disease" in normalized:
        return "rare_disease"
    if "platform" in normalized:
        return "platform"
    if "vaccine" in normalized:
        return "vaccines"
    return normalized.replace(" ", "_")


def _refine_watchlist_therapeutic_area(
    *,
    existing: str | None,
    inferred: str | None,
) -> str | None:
    normalized_inferred = _normalize_deal_therapeutic_area(inferred)
    if normalized_inferred is None:
        return None
    if existing is None:
        return normalized_inferred

    normalized_existing = _norm_text(existing)
    if normalized_existing in {
        "other",
        "platform",
        "genetic medicine",
        "genetic_medicine",
        "rare disease",
    }:
        return normalized_inferred
    return existing
