"""Build labeled M&A calibration datasets from stored probability snapshots."""
from __future__ import annotations

import csv
import json
import math
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median

import numpy as np
import yaml
from pydantic import BaseModel, Field
from scipy.optimize import minimize
from scipy.special import expit
from scipy.stats import rankdata

from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.intelligence.ma_probability import MAProbabilitySnapshotStore


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _norm_ticker(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized or None


def _norm_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).strip().lower().split())
    return normalized or None


class MATakeoutEvent(BaseModel):
    """One public-company biotech takeout used as a label source."""

    target_name: str
    target_ticker: str
    acquirer: str
    announcement_date: date
    headline_value_millions: float | None = None
    therapeutic_area: str | None = None
    phase_at_acquisition: str | None = None

    @property
    def normalized_ticker(self) -> str:
        return _norm_ticker(self.target_ticker) or self.target_ticker

    @property
    def normalized_therapeutic_area(self) -> str | None:
        return _norm_text(self.therapeutic_area)


class MATakeoutUniverse(BaseModel):
    """Collection of public-company takeout events."""

    as_of_date: date | None = None
    deals: list[MATakeoutEvent] = Field(default_factory=list)


class MACalibrationRow(BaseModel):
    """One labeled pre-takeout or control observation."""

    snapshot_date: date
    asset_id: str
    ticker: str
    label: int = Field(ge=0, le=1)
    probability: float
    rank: int
    best_acquirer_id: str
    best_acquirer_name: str | None = None
    stage: str | None = None
    therapeutic_area: str | None = None
    strategic_fit_score: float | None = None
    valuation_discount_score: float | None = None
    de_risking_stage_score: float | None = None
    capital_vulnerability_score: float | None = None
    scarcity_score: float | None = None
    scarcity_peer_count: int | None = None
    scarcity_bucket: str | None = None
    enterprise_value_millions: float | None = None
    acquisition_discount: float | None = None
    days_to_catalyst: int | None = None
    estimated_deal_value_low_millions: float | None = None
    estimated_deal_value_high_millions: float | None = None

    model_pos: float | None = None
    implied_pos: float | None = None
    spread_pp: float | None = None
    rnpv_millions: float | None = None
    ev_millions: float | None = None
    single_asset: bool | None = None
    config_quality: str | None = None
    market_exceeds_model: bool = False

    announcement_date: date | None = None
    days_to_announcement: int | None = None
    acquired_by: str | None = None
    headline_value_millions: float | None = None
    ta_deal_count_trailing_730d: int = 0
    ta_heat_score: float = 0.0
    prior_partnership_events: int = 0
    has_prior_partnership: bool = False
    match_group_id: str | None = None


class MACalibrationDataset(BaseModel):
    """Labeled takeout-vs-control dataset for M&A model evaluation."""

    built_at: datetime = Field(default_factory=_utcnow)
    start_date: date | None = None
    end_date: date | None = None
    lookahead_days: int
    n_rows: int
    n_positive_rows: int
    n_control_rows: int
    n_unique_targets: int
    dataset_mode: str = "historical_snapshot"
    anchor_days_before_announcement: int | None = None
    controls_per_positive: int | None = None
    rows: list[MACalibrationRow] = Field(default_factory=list)

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


class MACalibrationMetrics(BaseModel):
    """Summary metrics for a stored M&A probability calibration dataset."""

    evaluated_at: datetime = Field(default_factory=_utcnow)
    lookahead_days: int
    top_k: int
    n_rows: int
    n_snapshot_dates: int
    n_positive_rows: int
    n_positive_targets: int
    n_positive_targets_in_top_k: int
    precision_at_k: float | None = None
    unique_target_recall_at_k: float | None = None
    median_lead_days_at_k: float | None = None
    average_probability_positive: float | None = None
    average_probability_control: float | None = None


class MABaselineMetrics(BaseModel):
    """Ranking diagnostics for one transparent M&A baseline."""

    baseline_id: str
    label: str
    top_k: int
    n_rows: int
    n_snapshot_dates: int
    n_positive_rows: int
    n_positive_targets: int
    n_positive_targets_in_top_k: int
    precision_at_k: float | None = None
    unique_target_recall_at_k: float | None = None
    median_lead_days_at_k: float | None = None
    average_score_positive: float | None = None
    average_score_control: float | None = None


class MABaselineComparison(BaseModel):
    """Side-by-side evaluation of transparent M&A ranking baselines."""

    evaluated_at: datetime = Field(default_factory=_utcnow)
    lookahead_days: int
    top_k: int
    n_rows: int
    n_snapshot_dates: int
    n_positive_rows: int
    n_positive_targets: int
    baselines: list[MABaselineMetrics] = Field(default_factory=list)

    def baseline(self, baseline_id: str) -> MABaselineMetrics | None:
        """Return one baseline by id."""

        for item in self.baselines:
            if item.baseline_id == baseline_id:
                return item
        return None


class MALogisticMetrics(BaseModel):
    """Evaluation metrics for one probability vector on the canonical dataset."""

    auc: float | None = None
    brier_score: float | None = None
    precision_at_k: float | None = None
    unique_target_recall_at_k: float | None = None
    median_lead_days_at_k: float | None = None
    average_probability_positive: float | None = None
    average_probability_control: float | None = None


class MALogisticCoefficient(BaseModel):
    """One standardized logistic coefficient."""

    feature_name: str
    coefficient: float
    odds_ratio: float
    mean: float
    std: float


class MALogisticPredictionRow(BaseModel):
    """Per-row fitted and cross-validated probabilities."""

    match_group_id: str
    snapshot_date: date
    ticker: str
    label: int = Field(ge=0, le=1)
    stored_probability: float
    fitted_probability: float
    cross_validated_probability: float
    announcement_date: date | None = None
    days_to_announcement: int | None = None


class MALogisticFitResult(BaseModel):
    """Fitted matched-control logistic model and evaluation summary."""

    fitted_at: datetime = Field(default_factory=_utcnow)
    dataset_mode: str
    feature_names: list[str]
    l2_penalty: float
    top_k: int
    n_rows: int
    n_positive_rows: int
    n_control_rows: int
    n_match_groups: int
    fit_converged: bool
    cross_validated_groups_converged: int
    intercept: float
    coefficients: list[MALogisticCoefficient] = Field(default_factory=list)
    stored_probability_metrics: MALogisticMetrics
    fitted_metrics: MALogisticMetrics
    cross_validated_metrics: MALogisticMetrics
    predictions: list[MALogisticPredictionRow] = Field(default_factory=list)

    def write_json(self, path: str | Path) -> Path:
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(self.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )
        return out_path

    def write_predictions_csv(self, path: str | Path) -> Path:
        out_path = Path(path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = (
            list(self.predictions[0].model_dump(mode="json").keys())
            if self.predictions
            else []
        )
        with out_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            if fieldnames:
                writer.writeheader()
                for row in self.predictions:
                    writer.writerow(row.model_dump(mode="json"))
        return out_path

    @classmethod
    def load_json(cls, path: str | Path) -> "MALogisticFitResult":
        """Load a fitted model previously written by write_json()."""
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.model_validate(raw)

    def predict(self, feature_dict: dict[str, float]) -> float:
        """Apply this fitted model to a dict of feature values.

        Features are standardised using the per-coefficient mean/std recorded
        during training, so unseen features default to 0.0 (the standardised
        mean of missing data).
        """
        total = self.intercept
        for coef in self.coefficients:
            raw = feature_dict.get(coef.feature_name, 0.0)
            denom = coef.std if coef.std > 1e-9 else 1.0
            total += coef.coefficient * ((raw - coef.mean) / denom)
        return float(expit(total))


class MAPolicyComparisonResult(BaseModel):
    """Precision@k results for three ranking policies evaluated on a canonical dataset."""

    top_k: int
    calibration_threshold: float

    # Policy A: v1.2 rank order as-is, calibrated probability displayed only
    policy_a_label: str = "v1.2 rank (display calibrated prob)"
    policy_a_precision_at_k: float | None = None
    policy_a_recall_at_k: float | None = None

    # Policy B: v1.2 rank but only assets with p_takeout_calibrated >= threshold enter top_k
    policy_b_label: str = "v1.2 rank filtered by calibrated threshold"
    policy_b_precision_at_k: float | None = None
    policy_b_recall_at_k: float | None = None

    # Policy C: v1.2 as primary sort key, calibrated probability as tie-breaker
    policy_c_label: str = "v1.2 rank with calibrated tie-breaker"
    policy_c_precision_at_k: float | None = None
    policy_c_recall_at_k: float | None = None

    baseline_auc: float | None = None
    calibrated_auc: float | None = None


class MATakeoutUniverseLoader:
    """Load the curated public-deal universe used for M&A calibration labels."""

    @staticmethod
    def load(path: str | Path) -> MATakeoutUniverse:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        deals_raw = raw.get("deals", []) if isinstance(raw, dict) else []
        deals: list[MATakeoutEvent] = []
        for item in deals_raw:
            ticker = _norm_ticker(item.get("target_ticker"))
            announcement_date = item.get("announcement_date")
            if not ticker or not announcement_date:
                continue
            deals.append(
                MATakeoutEvent(
                    target_name=str(item.get("target_name") or ticker),
                    target_ticker=ticker,
                    acquirer=str(item.get("acquirer") or "unknown"),
                    announcement_date=date.fromisoformat(str(announcement_date)[:10]),
                    headline_value_millions=(
                        float(item["headline_value_millions"])
                        if item.get("headline_value_millions") is not None
                        else None
                    ),
                    therapeutic_area=item.get("therapeutic_area"),
                    phase_at_acquisition=item.get("phase_at_acquisition"),
                )
            )
        as_of_date = raw.get("as_of_date") if isinstance(raw, dict) else None
        return MATakeoutUniverse(
            as_of_date=date.fromisoformat(str(as_of_date)[:10]) if as_of_date else None,
            deals=deals,
        )


class MACalibrationDatasetBuilder:
    """Join stored M&A snapshots to known takeouts and screen context."""

    _DEFAULT_LOGISTIC_FEATURES: tuple[str, ...] = (
        "stored_probability",
        "strategic_fit_score",
        "capital_vulnerability_score",
        "log_enterprise_value",
    )
    _BASELINE_LABELS: tuple[tuple[str, str], ...] = (
        ("stored_probability", "Stored probability"),
        ("strategic_fit_only", "Strategic fit only"),
        ("strategic_fit_plus_scarcity", "Strategic fit + scarcity"),
        ("strategic_fit_plus_capital", "Strategic fit + capital vulnerability"),
        ("strategic_fit_plus_derisking", "Strategic fit + derisking"),
        ("composite_without_valuation_discount", "Composite without valuation discount"),
        (
            "composite_with_inverted_valuation_discount",
            "Composite with inverted valuation discount",
        ),
    )

    def __init__(
        self,
        *,
        knowledge_store: KnowledgeStore,
        deal_universe_path: str | Path = "research/mna/deal_universe_2020_2026.yaml",
        snapshot_store: MAProbabilitySnapshotStore | None = None,
    ) -> None:
        self.knowledge = knowledge_store
        self.snapshot_store = snapshot_store or MAProbabilitySnapshotStore(knowledge_store)
        self.deal_universe_path = str(deal_universe_path)

    def build_dataset(
        self,
        *,
        lookahead_days: int = 365,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> MACalibrationDataset:
        deals = MATakeoutUniverseLoader.load(self.deal_universe_path).deals
        deals_by_ticker: dict[str, list[MATakeoutEvent]] = {}
        for deal in deals:
            deals_by_ticker.setdefault(deal.normalized_ticker, []).append(deal)
        for bucket in deals_by_ticker.values():
            bucket.sort(key=lambda item: item.announcement_date)

        snapshot_rows = self.snapshot_store.list_snapshots(start_date=start_date, end_date=end_date)
        rows: list[MACalibrationRow] = []
        for snapshot in snapshot_rows:
            ticker = _norm_ticker(snapshot.ticker)
            if ticker is None:
                continue
            ticker_deals = deals_by_ticker.get(ticker, [])
            if ticker_deals and snapshot.snapshot_date >= ticker_deals[0].announcement_date:
                continue

            matched_deal = self._match_deal(
                deals=ticker_deals,
                snapshot_date=snapshot.snapshot_date,
                lookahead_days=lookahead_days,
            )
            screen = self._screen_snapshot_on_or_before(
                asset_id=snapshot.asset_id,
                ticker=ticker,
                as_of=snapshot.snapshot_date,
            )
            therapeutic_area = snapshot.therapeutic_area or (
                screen.get("ta") if screen is not None else None
            )
            ta_deal_count = self._ta_deal_count(
                deals=deals,
                therapeutic_area=therapeutic_area,
                as_of=snapshot.snapshot_date,
                trailing_days=730,
            )
            prior_partnership_events = self._count_prior_partnership_events(
                asset_id=snapshot.asset_id,
                as_of=snapshot.snapshot_date,
            )
            rows.append(
                MACalibrationRow(
                    snapshot_date=snapshot.snapshot_date,
                    asset_id=snapshot.asset_id,
                    ticker=ticker,
                    label=1 if matched_deal is not None else 0,
                    probability=float(snapshot.probability),
                    rank=int(snapshot.rank),
                    best_acquirer_id=snapshot.best_acquirer_id,
                    best_acquirer_name=snapshot.best_acquirer_name,
                    stage=snapshot.stage or (screen.get("stage") if screen is not None else None),
                    therapeutic_area=therapeutic_area,
                    strategic_fit_score=snapshot.strategic_fit_score,
                    valuation_discount_score=snapshot.valuation_discount_score,
                    de_risking_stage_score=snapshot.de_risking_stage_score,
                    capital_vulnerability_score=snapshot.capital_vulnerability_score,
                    scarcity_score=snapshot.scarcity_score,
                    scarcity_peer_count=snapshot.scarcity_peer_count,
                    scarcity_bucket=snapshot.scarcity_bucket,
                    enterprise_value_millions=snapshot.enterprise_value_millions,
                    acquisition_discount=snapshot.acquisition_discount,
                    days_to_catalyst=snapshot.days_to_catalyst,
                    estimated_deal_value_low_millions=snapshot.estimated_deal_value_low_millions,
                    estimated_deal_value_high_millions=snapshot.estimated_deal_value_high_millions,
                    model_pos=_coerce_float(screen, "model_pos"),
                    implied_pos=_coerce_float(screen, "implied_pos"),
                    spread_pp=_coerce_float(screen, "spread_pp"),
                    rnpv_millions=_coerce_float(screen, "rnpv_millions"),
                    ev_millions=_coerce_float(screen, "ev_millions"),
                    single_asset=(
                        bool(screen["single_asset"]) if screen is not None else None
                    ),
                    config_quality=screen.get("config_quality") if screen is not None else None,
                    market_exceeds_model=(
                        bool(screen.get("market_exceeds_model", False))
                        if screen is not None
                        else False
                    ),
                    announcement_date=(
                        matched_deal.announcement_date if matched_deal is not None else None
                    ),
                    days_to_announcement=(
                        (matched_deal.announcement_date - snapshot.snapshot_date).days
                        if matched_deal is not None
                        else None
                    ),
                    acquired_by=matched_deal.acquirer if matched_deal is not None else None,
                    headline_value_millions=(
                        matched_deal.headline_value_millions if matched_deal is not None else None
                    ),
                    ta_deal_count_trailing_730d=ta_deal_count,
                    ta_heat_score=min(round(ta_deal_count / 4.0, 6), 1.0),
                    prior_partnership_events=prior_partnership_events,
                    has_prior_partnership=prior_partnership_events > 0,
                )
            )

        rows.sort(
            key=lambda row: (
                row.snapshot_date,
                row.rank,
                -row.probability,
                row.ticker,
            )
        )
        positive_targets = {row.ticker for row in rows if row.label == 1}
        dataset_start = start_date or (rows[0].snapshot_date if rows else None)
        dataset_end = end_date or (rows[-1].snapshot_date if rows else None)
        return MACalibrationDataset(
            start_date=dataset_start,
            end_date=dataset_end,
            lookahead_days=lookahead_days,
            n_rows=len(rows),
            n_positive_rows=sum(1 for row in rows if row.label == 1),
            n_control_rows=sum(1 for row in rows if row.label == 0),
            n_unique_targets=len(positive_targets),
            dataset_mode="historical_snapshot",
            rows=rows,
        )

    def build_canonical_dataset(
        self,
        *,
        lookahead_days: int = 365,
        start_date: date | None = None,
        end_date: date | None = None,
        anchor_days_before_announcement: int = 180,
        controls_per_positive: int = 2,
    ) -> MACalibrationDataset:
        """Deduplicate to one canonical pre-deal row per target plus matched controls."""

        base = self.build_dataset(
            lookahead_days=lookahead_days,
            start_date=start_date,
            end_date=end_date,
        )
        if not base.rows:
            return MACalibrationDataset(
                start_date=start_date,
                end_date=end_date,
                lookahead_days=lookahead_days,
                n_rows=0,
                n_positive_rows=0,
                n_control_rows=0,
                n_unique_targets=0,
                dataset_mode="canonical_predeal",
                anchor_days_before_announcement=anchor_days_before_announcement,
                controls_per_positive=controls_per_positive,
                rows=[],
            )

        deals = MATakeoutUniverseLoader.load(self.deal_universe_path).deals
        deal_tickers = {
            deal.normalized_ticker
            for deal in deals
            if deal.normalized_ticker is not None
        }
        rows_by_date = self._rows_by_date(base)
        positive_groups: dict[tuple[str, date], list[MACalibrationRow]] = {}
        for row in base.rows:
            if row.label != 1 or row.announcement_date is None:
                continue
            positive_groups.setdefault((row.ticker, row.announcement_date), []).append(row)

        selected_rows: list[MACalibrationRow] = []
        used_control_tickers: set[str] = set()
        for (_, _), grouped_rows in sorted(
            positive_groups.items(),
            key=lambda item: (item[0][1], item[0][0]),
        ):
            canonical = self._select_canonical_positive_row(
                grouped_rows,
                anchor_days_before_announcement=anchor_days_before_announcement,
            )
            if canonical is None:
                continue
            match_group_id = self._match_group_id(
                ticker=canonical.ticker,
                announcement_date=canonical.announcement_date,
            )
            canonical = canonical.model_copy(update={"match_group_id": match_group_id})
            selected_rows.append(canonical)
            controls = self._match_control_rows(
                target_row=canonical,
                candidate_rows=rows_by_date.get(canonical.snapshot_date, []),
                all_deal_tickers=deal_tickers,
                controls_per_positive=controls_per_positive,
                used_control_tickers=used_control_tickers,
            )
            controls = [
                control.model_copy(update={"match_group_id": match_group_id})
                for control in controls
            ]
            selected_rows.extend(controls)
            for control in controls:
                ticker = _norm_ticker(control.ticker)
                if ticker is not None:
                    used_control_tickers.add(ticker)

        selected_rows.sort(
            key=lambda row: (
                row.snapshot_date,
                -row.label,
                row.rank,
                -row.probability,
                row.ticker,
            )
        )
        positive_targets = {row.ticker for row in selected_rows if row.label == 1}
        dataset_start = start_date or (selected_rows[0].snapshot_date if selected_rows else None)
        dataset_end = end_date or (selected_rows[-1].snapshot_date if selected_rows else None)
        return MACalibrationDataset(
            start_date=dataset_start,
            end_date=dataset_end,
            lookahead_days=lookahead_days,
            n_rows=len(selected_rows),
            n_positive_rows=sum(1 for row in selected_rows if row.label == 1),
            n_control_rows=sum(1 for row in selected_rows if row.label == 0),
            n_unique_targets=len(positive_targets),
            dataset_mode="canonical_predeal",
            anchor_days_before_announcement=anchor_days_before_announcement,
            controls_per_positive=controls_per_positive,
            rows=selected_rows,
        )

    def evaluate(
        self,
        dataset: MACalibrationDataset,
        *,
        top_k: int = 15,
    ) -> MACalibrationMetrics:
        positive_targets = {row.ticker for row in dataset.rows if row.label == 1}
        positive_probabilities = [row.probability for row in dataset.rows if row.label == 1]
        control_probabilities = [row.probability for row in dataset.rows if row.label == 0]
        n_snapshot_dates = len({row.snapshot_date for row in dataset.rows})
        if dataset.dataset_mode == "canonical_predeal":
            top_rows = sorted(
                dataset.rows,
                key=lambda row: (-row.probability, row.rank, row.snapshot_date, row.ticker),
            )[:top_k]
            top_total = len(top_rows)
            top_hits = sum(1 for row in top_rows if row.label == 1)
            captured_targets = {row.ticker for row in top_rows if row.label == 1}
            best_lead_days = {
                row.ticker: row.days_to_announcement
                for row in top_rows
                if row.label == 1 and row.days_to_announcement is not None
            }
        else:
            rows_by_date = self._rows_by_date(dataset)
            top_hits = 0
            top_total = 0
            captured_targets: set[str] = set()
            best_lead_days: dict[str, int] = {}
            for snapshot_date in sorted(rows_by_date):
                ranked = sorted(
                    rows_by_date[snapshot_date],
                    key=lambda row: (-row.probability, row.rank, row.ticker),
                )
                top_rows = ranked[:top_k]
                top_total += len(top_rows)
                top_hits += sum(1 for row in top_rows if row.label == 1)
                for row in top_rows:
                    if row.label != 1 or row.days_to_announcement is None:
                        continue
                    captured_targets.add(row.ticker)
                    best_lead_days[row.ticker] = max(
                        best_lead_days.get(row.ticker, row.days_to_announcement),
                        row.days_to_announcement,
                    )

        return MACalibrationMetrics(
            lookahead_days=dataset.lookahead_days,
            top_k=top_k,
            n_rows=dataset.n_rows,
            n_snapshot_dates=n_snapshot_dates,
            n_positive_rows=dataset.n_positive_rows,
            n_positive_targets=len(positive_targets),
            n_positive_targets_in_top_k=len(captured_targets),
            precision_at_k=round(top_hits / top_total, 6) if top_total > 0 else None,
            unique_target_recall_at_k=(
                round(len(captured_targets) / len(positive_targets), 6)
                if positive_targets
                else None
            ),
            median_lead_days_at_k=(
                float(median(best_lead_days.values()))
                if best_lead_days
                else None
            ),
            average_probability_positive=(
                round(sum(positive_probabilities) / len(positive_probabilities), 6)
                if positive_probabilities
                else None
            ),
            average_probability_control=(
                round(sum(control_probabilities) / len(control_probabilities), 6)
                if control_probabilities
                else None
            ),
        )

    def fit_logistic_model(
        self,
        dataset: MACalibrationDataset,
        *,
        feature_names: list[str] | tuple[str, ...] | None = None,
        l2_penalty: float = 1.0,
        top_k: int = 15,
    ) -> MALogisticFitResult:
        """Fit the first matched-control logistic model on a canonical dataset."""

        if dataset.dataset_mode != "canonical_predeal":
            raise ValueError("fit_logistic_model() requires a canonical_predeal dataset")
        if dataset.n_rows <= 0:
            raise ValueError("Cannot fit logistic model on an empty dataset")

        feature_names = list(feature_names or self._DEFAULT_LOGISTIC_FEATURES)
        X = self._feature_matrix(dataset.rows, feature_names)
        y = np.array([float(row.label) for row in dataset.rows], dtype=float)
        group_ids = np.array(
            [
                row.match_group_id
                or self._match_group_id(ticker=row.ticker, announcement_date=row.announcement_date)
                for row in dataset.rows
            ],
            dtype=object,
        )

        means, stds, X_scaled = _standardize_matrix(X)
        intercept, coefficients, converged = _fit_penalized_logistic(
            X_scaled,
            y,
            l2_penalty=l2_penalty,
        )
        fitted_probabilities = _predict_penalized_logistic(
            X_scaled,
            intercept=intercept,
            coefficients=coefficients,
        )

        cv_probabilities = np.zeros(len(dataset.rows), dtype=float)
        cv_converged_groups = 0
        for group_id in sorted(set(group_ids.tolist())):
            test_mask = group_ids == group_id
            train_mask = ~test_mask
            if int(np.sum(train_mask)) <= 0:
                continue
            X_train = X[train_mask]
            y_train = y[train_mask]
            train_means, train_stds, X_train_scaled = _standardize_matrix(X_train)
            fold_intercept, fold_coefficients, fold_converged = _fit_penalized_logistic(
                X_train_scaled,
                y_train,
                l2_penalty=l2_penalty,
            )
            if fold_converged:
                cv_converged_groups += 1
            X_test_scaled = (X[test_mask] - train_means) / train_stds
            cv_probabilities[test_mask] = _predict_penalized_logistic(
                X_test_scaled,
                intercept=fold_intercept,
                coefficients=fold_coefficients,
            )

        predictions = [
            MALogisticPredictionRow(
                match_group_id=str(group_ids[idx]),
                snapshot_date=row.snapshot_date,
                ticker=row.ticker,
                label=row.label,
                stored_probability=row.probability,
                fitted_probability=float(fitted_probabilities[idx]),
                cross_validated_probability=float(cv_probabilities[idx]),
                announcement_date=row.announcement_date,
                days_to_announcement=row.days_to_announcement,
            )
            for idx, row in enumerate(dataset.rows)
        ]

        coefficients_payload = [
            MALogisticCoefficient(
                feature_name=feature_names[idx],
                coefficient=round(float(coefficients[idx]), 6),
                odds_ratio=round(float(math.exp(coefficients[idx])), 6),
                mean=round(float(means[idx]), 6),
                std=round(float(stds[idx]), 6),
            )
            for idx in range(len(feature_names))
        ]
        return MALogisticFitResult(
            dataset_mode=dataset.dataset_mode,
            feature_names=feature_names,
            l2_penalty=float(l2_penalty),
            top_k=top_k,
            n_rows=dataset.n_rows,
            n_positive_rows=dataset.n_positive_rows,
            n_control_rows=dataset.n_control_rows,
            n_match_groups=len(set(group_ids.tolist())),
            fit_converged=converged,
            cross_validated_groups_converged=cv_converged_groups,
            intercept=round(float(intercept), 6),
            coefficients=coefficients_payload,
            stored_probability_metrics=self._score_metrics_for_probabilities(
                dataset.rows,
                [row.probability for row in dataset.rows],
                top_k=top_k,
            ),
            fitted_metrics=self._score_metrics_for_probabilities(
                dataset.rows,
                fitted_probabilities.tolist(),
                top_k=top_k,
            ),
            cross_validated_metrics=self._score_metrics_for_probabilities(
                dataset.rows,
                cv_probabilities.tolist(),
                top_k=top_k,
            ),
            predictions=predictions,
        )

    def compare_baselines(
        self,
        dataset: MACalibrationDataset,
        *,
        top_k: int = 15,
    ) -> MABaselineComparison:
        """Evaluate transparent ranking baselines on the same labeled dataset."""

        rows_by_date = self._rows_by_date(dataset)
        n_snapshot_dates = len(rows_by_date)
        n_positive_targets = len({row.ticker for row in dataset.rows if row.label == 1})
        baselines = [
            self._evaluate_ranker(
                dataset=dataset,
                rows_by_date=rows_by_date,
                baseline_id=baseline_id,
                label=label,
                score_fn=self._baseline_score_fn(baseline_id),
                top_k=top_k,
                n_snapshot_dates=n_snapshot_dates,
                n_positive_targets=n_positive_targets,
            )
            for baseline_id, label in self._BASELINE_LABELS
        ]
        return MABaselineComparison(
            lookahead_days=dataset.lookahead_days,
            top_k=top_k,
            n_rows=dataset.n_rows,
            n_snapshot_dates=n_snapshot_dates,
            n_positive_rows=dataset.n_positive_rows,
            n_positive_targets=n_positive_targets,
            baselines=baselines,
        )

    def compare_ranking_policies(
        self,
        dataset: MACalibrationDataset,
        fit_result: MALogisticFitResult,
        *,
        top_k: int = 15,
        calibration_threshold: float = 0.10,
    ) -> MAPolicyComparisonResult:
        """Evaluate three ranking policies that keep v1.2 as the primary ranker.

        Policy A: v1.2 rank order unchanged — calibrated prob displayed only.
        Policy B: v1.2 rank filtered to assets with p_calibrated >= threshold.
        Policy C: v1.2 as primary sort key, calibrated prob as secondary tie-breaker.

        Returns precision@k and recall@k for each policy so the caller can decide
        whether promotion (replacing v1.2 ranking) is warranted.
        """
        rows = dataset.rows

        calibrated = [
            fit_result.predict(self._policy_feature_dict(row, fit_result.feature_names))
            for row in rows
        ]

        # Policy A: rank by v1.2 stored probability only (baseline)
        pairs_a = list(zip(rows, calibrated, strict=False))
        prec_a, rec_a = self._evaluate_policy_pairs(
            dataset=dataset,
            ranked_pairs=pairs_a,
            top_k=top_k,
            sort_key=lambda item: (-item[0].probability, item[0].rank, item[0].snapshot_date, item[0].ticker),
        )

        # Policy B: rank by v1.2, but drop assets below calibrated threshold
        pairs_b_filtered = list(
            zip(rows, calibrated, strict=False)
        )
        prec_b, rec_b = self._evaluate_policy_pairs(
            dataset=dataset,
            ranked_pairs=pairs_b_filtered,
            top_k=top_k,
            predicate=lambda item: item[1] >= calibration_threshold,
            sort_key=lambda item: (-item[0].probability, item[0].rank, item[0].snapshot_date, item[0].ticker),
        )
        if prec_b is None and rec_b is None:
            prec_b, rec_b = prec_a, rec_a

        # Policy C: v1.2 primary, calibrated probability as secondary tie-breaker
        pairs_c = list(zip(rows, calibrated, strict=False))
        prec_c, rec_c = self._evaluate_policy_pairs(
            dataset=dataset,
            ranked_pairs=pairs_c,
            top_k=top_k,
            sort_key=lambda item: (-item[0].probability, -item[1], item[0].rank, item[0].snapshot_date, item[0].ticker),
        )

        baseline_auc = _binary_auc([row.label for row in rows], [float(row.probability) for row in rows])
        calibrated_auc = _binary_auc([row.label for row in rows], calibrated)

        return MAPolicyComparisonResult(
            top_k=top_k,
            calibration_threshold=calibration_threshold,
            policy_a_precision_at_k=prec_a,
            policy_a_recall_at_k=rec_a,
            policy_b_precision_at_k=prec_b,
            policy_b_recall_at_k=rec_b,
            policy_c_precision_at_k=prec_c,
            policy_c_recall_at_k=rec_c,
            baseline_auc=baseline_auc,
            calibrated_auc=calibrated_auc,
        )

    @staticmethod
    def _policy_feature_dict(
        row: MACalibrationRow,
        feature_names: list[str],
    ) -> dict[str, float]:
        return {
            feature_name: MACalibrationDatasetBuilder._feature_value(row, feature_name)
            for feature_name in feature_names
        }

    @staticmethod
    def _evaluate_policy_pairs(
        *,
        dataset: MACalibrationDataset,
        ranked_pairs: list[tuple[MACalibrationRow, float]],
        top_k: int,
        sort_key,
        predicate=None,
    ) -> tuple[float | None, float | None]:
        predicate = predicate or (lambda item: True)
        positive_targets = {row.ticker for row, _ in ranked_pairs if row.label == 1}
        if not ranked_pairs or top_k <= 0:
            return None, None

        if dataset.dataset_mode == "canonical_predeal":
            eligible = [item for item in ranked_pairs if predicate(item)]
            if not eligible:
                return None, None
            top = sorted(eligible, key=sort_key)[:top_k]
            hits = sum(1 for row, _ in top if row.label == 1)
            captured = len({row.ticker for row, _ in top if row.label == 1})
            precision = round(hits / len(top), 6) if top else None
            recall = round(captured / len(positive_targets), 6) if positive_targets else None
            return precision, recall

        grouped: dict[date, list[tuple[MACalibrationRow, float]]] = {}
        for item in ranked_pairs:
            grouped.setdefault(item[0].snapshot_date, []).append(item)

        top_total = 0
        top_hits = 0
        captured_targets: set[str] = set()
        for snapshot_date in sorted(grouped):
            eligible = [item for item in grouped[snapshot_date] if predicate(item)]
            if not eligible:
                continue
            top = sorted(eligible, key=sort_key)[:top_k]
            top_total += len(top)
            top_hits += sum(1 for row, _ in top if row.label == 1)
            for row, _ in top:
                if row.label == 1:
                    captured_targets.add(row.ticker)
        if top_total <= 0:
            return None, None
        precision = round(top_hits / top_total, 6)
        recall = round(len(captured_targets) / len(positive_targets), 6) if positive_targets else None
        return precision, recall

    @staticmethod
    def _match_group_id(*, ticker: str, announcement_date: date | None) -> str:
        normalized_ticker = _norm_ticker(ticker) or ticker
        if announcement_date is None:
            return f"{normalized_ticker}:unknown"
        return f"{normalized_ticker}:{announcement_date.isoformat()}"

    @staticmethod
    def _match_deal(
        *,
        deals: list[MATakeoutEvent],
        snapshot_date: date,
        lookahead_days: int,
    ) -> MATakeoutEvent | None:
        for deal in deals:
            if deal.announcement_date <= snapshot_date:
                continue
            if (deal.announcement_date - snapshot_date).days <= lookahead_days:
                return deal
        return None

    def _screen_snapshot_on_or_before(
        self,
        *,
        asset_id: str | None = None,
        ticker: str,
        as_of: date,
    ) -> dict[str, object] | None:
        try:
            if asset_id:
                asset_row = self.knowledge.get_screen_snapshot_for_asset_on_or_before(
                    asset_id=asset_id,
                    as_of=as_of,
                )
                if asset_row is not None:
                    return asset_row
            return self.knowledge.get_screen_snapshot_for_ticker_on_or_before(
                ticker=ticker,
                as_of=as_of,
            )
        except Exception:
            return None

    def _count_prior_partnership_events(self, *, asset_id: str, as_of: date) -> int:
        row = self.knowledge._conn.execute(
            """
            SELECT COUNT(*) AS n
            FROM events
            WHERE asset_id = ?
              AND event_type = 'partnership'
              AND observed_at IS NOT NULL
              AND substr(observed_at, 1, 10) < ?
            """,
            (asset_id, as_of.isoformat()),
        ).fetchone()
        return int(row["n"]) if row is not None and row["n"] is not None else 0

    @staticmethod
    def _ta_deal_count(
        *,
        deals: list[MATakeoutEvent],
        therapeutic_area: str | None,
        as_of: date,
        trailing_days: int,
    ) -> int:
        normalized_ta = _norm_text(therapeutic_area)
        if normalized_ta is None:
            return 0
        count = 0
        for deal in deals:
            if deal.normalized_therapeutic_area != normalized_ta:
                continue
            delta_days = (as_of - deal.announcement_date).days
            if 0 < delta_days <= trailing_days:
                count += 1
        return count

    @staticmethod
    def _rows_by_date(dataset: MACalibrationDataset) -> dict[date, list[MACalibrationRow]]:
        rows_by_date: dict[date, list[MACalibrationRow]] = {}
        for row in dataset.rows:
            rows_by_date.setdefault(row.snapshot_date, []).append(row)
        return rows_by_date

    @staticmethod
    def _select_canonical_positive_row(
        rows: list[MACalibrationRow],
        *,
        anchor_days_before_announcement: int,
    ) -> MACalibrationRow | None:
        if not rows:
            return None
        announcement_date = rows[0].announcement_date
        if announcement_date is None:
            return None
        anchor_date = announcement_date - timedelta(days=anchor_days_before_announcement)
        on_or_before_anchor = [row for row in rows if row.snapshot_date <= anchor_date]
        if on_or_before_anchor:
            return max(
                on_or_before_anchor,
                key=lambda row: (row.snapshot_date, row.probability, -row.rank),
            )
        before_announcement = [row for row in rows if row.snapshot_date < announcement_date]
        if before_announcement:
            return min(
                before_announcement,
                key=lambda row: (abs((row.snapshot_date - anchor_date).days), row.snapshot_date),
            )
        return None

    def _match_control_rows(
        self,
        *,
        target_row: MACalibrationRow,
        candidate_rows: list[MACalibrationRow],
        all_deal_tickers: set[str],
        controls_per_positive: int,
        used_control_tickers: set[str],
    ) -> list[MACalibrationRow]:
        selected: list[MACalibrationRow] = []
        selected_tickers: set[str] = set()
        for allow_reuse in (False, True):
            ranked_candidates = sorted(
                (
                    candidate
                    for candidate in candidate_rows
                    if self._is_eligible_control(
                        target_row=target_row,
                        candidate=candidate,
                        all_deal_tickers=all_deal_tickers,
                        used_control_tickers=used_control_tickers,
                        selected_tickers=selected_tickers,
                        allow_reuse=allow_reuse,
                    )
                ),
                key=lambda candidate: self._control_match_key(target_row, candidate),
            )
            for candidate in ranked_candidates:
                ticker = _norm_ticker(candidate.ticker)
                if ticker is None:
                    continue
                selected.append(candidate)
                selected_tickers.add(ticker)
                if len(selected) >= controls_per_positive:
                    return selected
        return selected

    @staticmethod
    def _is_eligible_control(
        *,
        target_row: MACalibrationRow,
        candidate: MACalibrationRow,
        all_deal_tickers: set[str],
        used_control_tickers: set[str],
        selected_tickers: set[str],
        allow_reuse: bool,
    ) -> bool:
        ticker = _norm_ticker(candidate.ticker)
        target_ticker = _norm_ticker(target_row.ticker)
        if ticker is None or target_ticker is None:
            return False
        if candidate.label != 0 or ticker == target_ticker:
            return False
        if ticker in all_deal_tickers:
            return False
        if ticker in selected_tickers:
            return False
        if not allow_reuse and ticker in used_control_tickers:
            return False
        return True

    @classmethod
    def _control_match_key(
        cls,
        target_row: MACalibrationRow,
        candidate: MACalibrationRow,
    ) -> tuple[object, ...]:
        target_stage = _norm_text(target_row.stage)
        candidate_stage = _norm_text(candidate.stage)
        target_ta = _norm_text(target_row.therapeutic_area)
        candidate_ta = _norm_text(candidate.therapeutic_area)
        target_ev = cls._row_enterprise_value(target_row)
        candidate_ev = cls._row_enterprise_value(candidate)
        target_bucket = _ev_bucket(target_ev)
        candidate_bucket = _ev_bucket(candidate_ev)
        ev_bucket_distance = (
            abs(target_bucket - candidate_bucket)
            if target_bucket is not None and candidate_bucket is not None
            else 99
        )
        ev_distance = (
            abs(math.log1p(max(target_ev or 0.0, 0.0)) - math.log1p(max(candidate_ev or 0.0, 0.0)))
            if target_ev is not None and candidate_ev is not None
            else 99.0
        )
        catalyst_distance = (
            abs((target_row.days_to_catalyst or 9999) - (candidate.days_to_catalyst or 9999))
            if target_row.days_to_catalyst is not None and candidate.days_to_catalyst is not None
            else 9999
        )
        return (
            0 if target_stage == candidate_stage and target_stage is not None else 1,
            0 if target_ta == candidate_ta and target_ta is not None else 1,
            ev_bucket_distance,
            round(ev_distance, 6),
            catalyst_distance,
            abs(candidate.rank - target_row.rank),
            candidate.rank,
            candidate.ticker,
        )

    @staticmethod
    def _row_enterprise_value(row: MACalibrationRow) -> float | None:
        value = row.enterprise_value_millions
        if value is None:
            value = row.ev_millions
        if value is None:
            return None
        return float(value)

    @classmethod
    def _feature_matrix(
        cls,
        rows: list[MACalibrationRow],
        feature_names: list[str],
    ) -> np.ndarray:
        return np.array(
            [
                [cls._feature_value(row, feature_name) for feature_name in feature_names]
                for row in rows
            ],
            dtype=float,
        )

    @classmethod
    def _feature_value(cls, row: MACalibrationRow, feature_name: str) -> float:
        if feature_name == "stored_probability":
            return _component_value(row.probability)
        if feature_name == "strategic_fit_score":
            return _component_value(row.strategic_fit_score)
        if feature_name == "valuation_discount_score":
            return _component_value(row.valuation_discount_score)
        if feature_name == "capital_vulnerability_score":
            return _component_value(row.capital_vulnerability_score)
        if feature_name == "de_risking_stage_score":
            return _component_value(row.de_risking_stage_score)
        if feature_name == "ta_heat_score":
            return _component_value(row.ta_heat_score)
        if feature_name == "single_asset_flag":
            return 1.0 if row.single_asset else 0.0
        if feature_name == "market_exceeds_model_flag":
            return 1.0 if row.market_exceeds_model else 0.0
        if feature_name == "log_enterprise_value":
            return math.log1p(max(cls._row_enterprise_value(row) or 0.0, 0.0))
        raise ValueError(f"Unsupported logistic feature: {feature_name}")

    @staticmethod
    def _score_metrics_for_probabilities(
        rows: list[MACalibrationRow],
        probabilities: list[float],
        *,
        top_k: int,
    ) -> MALogisticMetrics:
        labels = [row.label for row in rows]
        positive_probabilities = [score for score, label in zip(probabilities, labels, strict=False) if label == 1]
        control_probabilities = [score for score, label in zip(probabilities, labels, strict=False) if label == 0]
        ranked_rows = sorted(
            zip(rows, probabilities, strict=False),
            key=lambda item: (-item[1], item[0].rank, item[0].snapshot_date, item[0].ticker),
        )
        top_rows = ranked_rows[:top_k]
        top_hits = sum(1 for row, _ in top_rows if row.label == 1)
        positive_targets = {row.ticker for row in rows if row.label == 1}
        captured_targets = {row.ticker for row, _ in top_rows if row.label == 1}
        best_lead_days = [
            row.days_to_announcement
            for row, _ in top_rows
            if row.label == 1 and row.days_to_announcement is not None
        ]
        return MALogisticMetrics(
            auc=_binary_auc(labels, probabilities),
            brier_score=round(
                float(np.mean((np.array(probabilities, dtype=float) - np.array(labels, dtype=float)) ** 2)),
                6,
            ),
            precision_at_k=round(top_hits / len(top_rows), 6) if top_rows else None,
            unique_target_recall_at_k=(
                round(len(captured_targets) / len(positive_targets), 6)
                if positive_targets
                else None
            ),
            median_lead_days_at_k=float(median(best_lead_days)) if best_lead_days else None,
            average_probability_positive=(
                round(sum(positive_probabilities) / len(positive_probabilities), 6)
                if positive_probabilities
                else None
            ),
            average_probability_control=(
                round(sum(control_probabilities) / len(control_probabilities), 6)
                if control_probabilities
                else None
            ),
        )

    @classmethod
    def _baseline_score_fn(cls, baseline_id: str) -> Callable[[MACalibrationRow], float]:
        if baseline_id == "stored_probability":
            return lambda row: _component_value(row.probability)
        if baseline_id == "strategic_fit_only":
            return lambda row: _component_value(row.strategic_fit_score)
        if baseline_id == "strategic_fit_plus_scarcity":
            return lambda row: _weighted_average(
                row,
                strategic_fit_score=0.85,
                scarcity_score=0.15,
            )
        if baseline_id == "strategic_fit_plus_capital":
            return lambda row: _weighted_average(
                row,
                strategic_fit_score=0.5,
                capital_vulnerability_score=0.5,
            )
        if baseline_id == "strategic_fit_plus_derisking":
            return lambda row: _weighted_average(
                row,
                strategic_fit_score=0.5,
                de_risking_stage_score=0.5,
            )
        if baseline_id == "composite_without_valuation_discount":
            return lambda row: _weighted_average(
                row,
                strategic_fit_score=0.30,
                de_risking_stage_score=0.25,
                capital_vulnerability_score=0.15,
            )
        if baseline_id == "composite_with_inverted_valuation_discount":
            return lambda row: _weighted_average(
                row,
                strategic_fit_score=0.30,
                valuation_discount_score=0.30,
                de_risking_stage_score=0.25,
                capital_vulnerability_score=0.15,
                invert={"valuation_discount_score"},
            )
        raise ValueError(f"Unknown baseline_id: {baseline_id}")

    @staticmethod
    def _evaluate_ranker(
        *,
        dataset: MACalibrationDataset,
        rows_by_date: dict[date, list[MACalibrationRow]],
        baseline_id: str,
        label: str,
        score_fn: Callable[[MACalibrationRow], float],
        top_k: int,
        n_snapshot_dates: int,
        n_positive_targets: int,
    ) -> MABaselineMetrics:
        scored_rows = [(row, score_fn(row)) for row in dataset.rows]
        positive_scores = [score for row, score in scored_rows if row.label == 1]
        control_scores = [score for row, score in scored_rows if row.label == 0]

        if dataset.dataset_mode == "canonical_predeal":
            top_rows = sorted(
                dataset.rows,
                key=lambda row: (-score_fn(row), row.rank, row.snapshot_date, row.ticker),
            )[:top_k]
            top_total = len(top_rows)
            top_hits = sum(1 for row in top_rows if row.label == 1)
            captured_targets = {row.ticker for row in top_rows if row.label == 1}
            best_lead_days = {
                row.ticker: row.days_to_announcement
                for row in top_rows
                if row.label == 1 and row.days_to_announcement is not None
            }
        else:
            top_hits = 0
            top_total = 0
            captured_targets: set[str] = set()
            best_lead_days: dict[str, int] = {}
            for snapshot_date in sorted(rows_by_date):
                ranked = sorted(
                    rows_by_date[snapshot_date],
                    key=lambda row: (-score_fn(row), row.rank, row.ticker),
                )
                top_rows = ranked[:top_k]
                top_total += len(top_rows)
                top_hits += sum(1 for row in top_rows if row.label == 1)
                for row in top_rows:
                    if row.label != 1 or row.days_to_announcement is None:
                        continue
                    captured_targets.add(row.ticker)
                    best_lead_days[row.ticker] = max(
                        best_lead_days.get(row.ticker, row.days_to_announcement),
                        row.days_to_announcement,
                    )

        return MABaselineMetrics(
            baseline_id=baseline_id,
            label=label,
            top_k=top_k,
            n_rows=dataset.n_rows,
            n_snapshot_dates=n_snapshot_dates,
            n_positive_rows=dataset.n_positive_rows,
            n_positive_targets=n_positive_targets,
            n_positive_targets_in_top_k=len(captured_targets),
            precision_at_k=round(top_hits / top_total, 6) if top_total > 0 else None,
            unique_target_recall_at_k=(
                round(len(captured_targets) / n_positive_targets, 6)
                if n_positive_targets > 0
                else None
            ),
            median_lead_days_at_k=(
                float(median(best_lead_days.values()))
                if best_lead_days
                else None
            ),
            average_score_positive=(
                round(sum(positive_scores) / len(positive_scores), 6)
                if positive_scores
                else None
            ),
            average_score_control=(
                round(sum(control_scores) / len(control_scores), 6)
                if control_scores
                else None
            ),
        )


def _coerce_float(payload: dict[str, object] | None, key: str) -> float | None:
    if payload is None:
        return None
    value = payload.get(key)
    if value is None:
        return None
    return float(value)


def _component_value(value: float | None) -> float:
    if value is None:
        return 0.0
    return min(max(float(value), 0.0), 1.0)


def _weighted_average(
    row: MACalibrationRow,
    *,
    invert: set[str] | None = None,
    **weights: float,
) -> float:
    invert = invert or set()
    total_weight = sum(abs(weight) for weight in weights.values())
    if total_weight <= 0:
        return 0.0
    total = 0.0
    for field_name, weight in weights.items():
        value = _component_value(getattr(row, field_name))
        if field_name in invert:
            value = 1.0 - value
        total += value * weight
    return min(max(total / total_weight, 0.0), 1.0)


def _ev_bucket(value: float | None) -> int | None:
    if value is None:
        return None
    normalized = max(float(value), 0.0)
    if normalized < 300.0:
        return 0
    if normalized < 750.0:
        return 1
    if normalized < 1500.0:
        return 2
    if normalized < 3000.0:
        return 3
    if normalized < 6000.0:
        return 4
    return 5


def _standardize_matrix(X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    means = X.mean(axis=0)
    stds = X.std(axis=0)
    stds = np.where(stds < 1e-9, 1.0, stds)
    return means, stds, (X - means) / stds


def _fit_penalized_logistic(
    X_scaled: np.ndarray,
    y: np.ndarray,
    *,
    l2_penalty: float,
) -> tuple[float, np.ndarray, bool]:
    def neg_log_likelihood(theta: np.ndarray) -> float:
        intercept = theta[0]
        coefficients = theta[1:]
        probabilities = expit(intercept + X_scaled @ coefficients)
        probabilities = np.clip(probabilities, 1e-12, 1.0 - 1e-12)
        loss = -float(np.sum(y * np.log(probabilities) + (1.0 - y) * np.log(1.0 - probabilities)))
        loss += 0.5 * l2_penalty * float(np.sum(coefficients**2))
        return loss

    def gradient(theta: np.ndarray) -> np.ndarray:
        intercept = theta[0]
        coefficients = theta[1:]
        probabilities = expit(intercept + X_scaled @ coefficients)
        residual = probabilities - y
        grad_intercept = float(np.sum(residual))
        grad_coefficients = X_scaled.T @ residual + (l2_penalty * coefficients)
        return np.concatenate(([grad_intercept], grad_coefficients))

    theta0 = np.zeros(X_scaled.shape[1] + 1, dtype=float)
    result = minimize(
        neg_log_likelihood,
        theta0,
        jac=gradient,
        method="BFGS",
        options={"maxiter": 1000},
    )
    return float(result.x[0]), np.array(result.x[1:], dtype=float), bool(result.success)


def _predict_penalized_logistic(
    X_scaled: np.ndarray,
    *,
    intercept: float,
    coefficients: np.ndarray,
) -> np.ndarray:
    return np.array(expit(intercept + X_scaled @ coefficients), dtype=float)


def _binary_auc(labels: list[int], scores: list[float]) -> float | None:
    positive_scores = [score for score, label in zip(scores, labels, strict=False) if label == 1]
    negative_scores = [score for score, label in zip(scores, labels, strict=False) if label == 0]
    if not positive_scores or not negative_scores:
        return None
    ranks = rankdata(np.array(scores, dtype=float))
    n_positive = len(positive_scores)
    n_negative = len(negative_scores)
    positive_rank_sum = float(
        sum(rank for rank, label in zip(ranks.tolist(), labels, strict=False) if label == 1)
    )
    auc = (
        positive_rank_sum - (n_positive * (n_positive + 1) / 2.0)
    ) / float(n_positive * n_negative)
    return round(float(auc), 6)
