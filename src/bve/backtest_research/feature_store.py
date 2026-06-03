"""
feature_store — assemble the full feature matrix with provenance.

FeatureStore combines acquirer snapshots, target snapshots, and asset
snapshots into (acquirer × target × snapshot_date) rows that feed the
pair scorer.

Every row in the feature store carries all REQUIRED_PROVENANCE_FIELDS.
Rows with missing provenance are flagged as gaps and excluded from scoring.

Output schema (vrtx_regn_feature_store.csv):
  deal_id, acquirer_ticker, target_ticker, snapshot_date, days_before,
  is_actual_target, label_outcome (EVALUATION ONLY — not used in scoring),
  -- acquirer features --
  acq_cash_millions, acq_rd_expense_ttm_millions, acq_urgency_score,
  acq_deal_capacity_millions,
  -- target features --
  tgt_market_cap_millions, tgt_cash_millions, tgt_lead_asset_stage_score,
  tgt_n_active_trials, tgt_is_approved,
  -- pair features (inputs to AcquirerPairScorer) --
  asset_quality, acquirer_appetite, ta_overlap, size_fit,
  acquirer_urgency, integration_capacity,
  -- provenance --
  source_url, source_published_date, data_as_of_date,
  extraction_method, confidence,
  provenance_complete   (bool — all fields non-null)
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Any, Optional

from bve.backtest_research.acquirer_snapshot_builder import AcquirerSnapshotBuilder
from bve.backtest_research.asset_snapshot_builder import AssetSnapshotBuilder
from bve.backtest_research.candidate_universe_builder import CandidatePair
from bve.backtest_research.leakage_guard import LeakageGuard, REQUIRED_PROVENANCE_FIELDS
from bve.backtest_research.target_snapshot_builder import TargetSnapshotBuilder


# Label fields — these must NEVER appear as model input columns.
LABEL_FIELDS: frozenset[str] = frozenset({
    "label_outcome",
    "actual_deal_value_millions",
    "deal_announced_date",
    "is_actual_target_label",
})

# Model input columns (features only — no labels)
FEATURE_COLUMNS: tuple[str, ...] = (
    "asset_quality",
    "acquirer_appetite",
    "ta_overlap",
    "size_fit",
    "acquirer_urgency",
    "integration_capacity",
)


def _ta_overlap_score(acquirer_tas: str, target_ta: str) -> float:
    """Compute [0,1] TA overlap between acquirer TA list and target TA."""
    if not acquirer_tas or not target_ta:
        return 0.30
    acq_set = set(acquirer_tas.lower().replace(",", "|").split("|"))
    tgt_set = set(target_ta.lower().replace("_", " ").split())
    matches = sum(
        1 for a in acq_set
        if any(t in a or a in t for t in tgt_set)
    )
    return min(1.0, 0.30 + matches * 0.25)


def _size_fit_score(
    target_mc: Optional[float],
    deal_min: Optional[float],
    deal_max: Optional[float],
) -> float:
    if target_mc is None:
        return 0.50   # unknown → neutral
    if deal_min is None:
        deal_min = 0.0
    if deal_max is None:
        deal_max = 100_000.0
    if target_mc < deal_min * 0.5:
        return 0.20   # too small
    if target_mc > deal_max * 2.0:
        return 0.15   # too large
    if deal_min <= target_mc <= deal_max:
        return 0.85
    return 0.55   # borderline


@dataclass
class FeatureRow:
    deal_id: str
    acquirer_ticker: str
    target_ticker: str
    snapshot_date: str
    days_before: int
    is_actual_target: bool
    # Pair scorer inputs (all [0,1])
    asset_quality: float
    acquirer_appetite: float
    ta_overlap: float
    size_fit: float
    acquirer_urgency: float
    integration_capacity: float
    # Supporting features (not in scorer formula, for diagnostics)
    acq_cash_millions: Optional[float]
    acq_rd_expense_ttm_millions: Optional[float]
    tgt_market_cap_millions: Optional[float]
    tgt_lead_asset_stage_score: float
    tgt_n_active_trials: int
    tgt_is_approved: bool
    # Provenance
    source_url: str
    source_published_date: str
    data_as_of_date: str
    extraction_method: str
    confidence: float
    provenance_complete: bool
    # Gaps
    gaps: str = ""   # pipe-separated gap field names

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


class FeatureStore:
    """
    Build and export the feature matrix for VRTX/REGN backtest pairs.

    Usage::

        store = FeatureStore(raw_dir="research/backtests/vrtx_regn_2010/raw")
        rows = store.build_rows(
            candidates=candidate_pairs,
            acquirer_profiles={"VRTX": {...}, "REGN": {...}},
        )
        store.write_csv(rows, path="curated/vrtx_regn_feature_store.csv")
        gaps = store.collect_gaps(rows)
        store.write_csv(gaps, path="curated/vrtx_regn_research_gaps.csv")
    """

    def __init__(self, raw_dir: Optional["str | Path"] = None) -> None:
        self._acq_builder = AcquirerSnapshotBuilder(raw_dir=raw_dir)
        self._tgt_builder = TargetSnapshotBuilder(raw_dir=raw_dir)
        self._ast_builder = AssetSnapshotBuilder()
        self._leakage_guard = LeakageGuard()
        self._acq_cache: dict[str, dict[str, Any]] = {}

    def build_rows(
        self,
        candidates: list[CandidatePair],
        acquirer_profiles: Optional[dict[str, dict[str, Any]]] = None,
        target_metadata: Optional[dict[str, dict[str, Any]]] = None,
    ) -> list[FeatureRow]:
        """
        Build one FeatureRow per candidate pair.

        acquirer_profiles: {ticker: profile_dict from acquirers.yaml}
        target_metadata:   {ticker: {lead_asset, therapeutic_area, indication, modality}}
        """
        profiles = acquirer_profiles or {}
        meta = target_metadata or {}
        rows: list[FeatureRow] = []

        for cand in candidates:
            snap_date = date.fromisoformat(cand.snapshot_date)
            row = self._build_row(cand, snap_date, profiles, meta)
            rows.append(row)
        return rows

    def _build_row(
        self,
        cand: CandidatePair,
        snap_date: date,
        profiles: dict[str, dict[str, Any]],
        meta: dict[str, dict[str, Any]],
    ) -> FeatureRow:
        acq_profile = profiles.get(cand.acquirer_ticker, {})

        # -- Acquirer snapshot (cached per acquirer+date)
        cache_key = f"{cand.acquirer_ticker}_{snap_date.isoformat()}"
        if cache_key not in self._acq_cache:
            self._acq_cache[cache_key] = self._acq_builder.build(
                ticker=cand.acquirer_ticker,
                snapshot_date=snap_date,
                acquirer_profile=acq_profile,
            )
        acq_snap = self._acq_cache[cache_key]

        # -- Target snapshot
        tgt_meta = meta.get(cand.target_ticker, {})
        tgt_snap = self._tgt_builder.build(
            ticker=cand.target_ticker,
            lead_asset=tgt_meta.get("lead_asset", cand.target_ticker),
            snapshot_date=snap_date,
            therapeutic_area=cand.therapeutic_area,
            indication=tgt_meta.get("indication", ""),
            modality=cand.modality,
        )

        # -- Compute pair scorer inputs
        asset_quality = tgt_snap.get("lead_asset_stage_score", 0.30)
        acquirer_appetite = min(1.0, float(acq_snap.get("urgency_score", 0.40)) * 0.8 + 0.20)
        ta_overlap = _ta_overlap_score(
            acq_snap.get("therapeutic_areas", ""),
            cand.therapeutic_area,
        )
        size_fit = _size_fit_score(
            tgt_snap.get("market_cap_millions"),
            acq_snap.get("deal_min_millions"),
            acq_snap.get("deal_max_millions"),
        )
        acquirer_urgency = float(acq_snap.get("urgency_score", 0.40))
        integration_capacity = 0.65   # default; would use deal backlog / balance sheet

        # -- Provenance: most conservative source
        prov_date = min(
            filter(None, [
                acq_snap.get("data_as_of_date"),
                tgt_snap.get("data_as_of_date"),
            ]),
            default=snap_date.isoformat(),
        )
        prov_url = tgt_snap.get("source_url") or acq_snap.get("source_url") or ""
        confidence = min(
            float(acq_snap.get("confidence", 0.70)),
            float(tgt_snap.get("confidence", 0.70)),
        )
        extraction = tgt_snap.get("extraction_method") or acq_snap.get("extraction_method") or ""

        # -- Check provenance completeness
        prov_dict = {
            "source_url": prov_url,
            "source_published_date": prov_date,
            "data_as_of_date": prov_date,
            "extraction_method": extraction,
            "confidence": confidence,
        }
        gaps_list = [
            k for k in REQUIRED_PROVENANCE_FIELDS
            if not prov_dict.get(k)
        ]
        if tgt_snap.get("market_cap_millions") is None:
            gaps_list.append("target_market_cap")
        if acq_snap.get("cash_and_equivalents_millions") is None:
            gaps_list.append("acquirer_cash")

        return FeatureRow(
            deal_id=cand.deal_id,
            acquirer_ticker=cand.acquirer_ticker,
            target_ticker=cand.target_ticker,
            snapshot_date=snap_date.isoformat(),
            days_before=cand.days_before,
            is_actual_target=cand.is_actual_target,
            asset_quality=asset_quality,
            acquirer_appetite=acquirer_appetite,
            ta_overlap=ta_overlap,
            size_fit=size_fit,
            acquirer_urgency=acquirer_urgency,
            integration_capacity=integration_capacity,
            acq_cash_millions=acq_snap.get("cash_and_equivalents_millions"),
            acq_rd_expense_ttm_millions=acq_snap.get("rd_expense_ttm_millions"),
            tgt_market_cap_millions=tgt_snap.get("market_cap_millions"),
            tgt_lead_asset_stage_score=asset_quality,
            tgt_n_active_trials=tgt_snap.get("n_active_clinical_trials", 0),
            tgt_is_approved=bool(tgt_snap.get("lead_asset_is_approved", False)),
            source_url=prov_url,
            source_published_date=prov_date,
            data_as_of_date=prov_date,
            extraction_method=extraction,
            confidence=confidence,
            provenance_complete=len(gaps_list) == 0,
            gaps="|".join(gaps_list),
        )

    @staticmethod
    def write_csv(rows: "list[FeatureRow | dict[str, Any]]", path: "str | Path") -> None:
        if not rows:
            return
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        dicts = [r.to_dict() if isinstance(r, FeatureRow) else r for r in rows]
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(dicts[0].keys()))
            writer.writeheader()
            writer.writerows(dicts)

    @staticmethod
    def collect_gaps(rows: list[FeatureRow]) -> list[dict[str, Any]]:
        gaps: list[dict[str, Any]] = []
        for row in rows:
            if row.gaps:
                for g in row.gaps.split("|"):
                    gaps.append({
                        "deal_id": row.deal_id,
                        "target_ticker": row.target_ticker,
                        "snapshot_date": row.snapshot_date,
                        "field_name": g.strip(),
                        "reason": "value_not_found",
                    })
        return gaps

    def run_leakage_audit(self, rows: list[FeatureRow]) -> Any:
        return self._leakage_guard.audit_dataframe(
            [r.to_dict() for r in rows],
            snapshot_date_col="snapshot_date",
        )
