"""
Watchlist-level market-implied PoS mispricing screen.

Usage
-----
    python -m bve.analysis.mispricing_screener \
        --watchlist examples/configs/watchlists/watchlist_stage1.yaml
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable, Optional

from pydantic import BaseModel

from bve.analysis.implied_pos import ImpliedPoSSolver
from bve.analysis.implied_pos_batch import ScreenRow
from bve.ingestion.market_data import get_fundamentals
from bve.intelligence.capital_structure import compute_capital_risk_as_of
from bve.intelligence.knowledge_layer import KnowledgeStore
from bve.ops.historical_replay import REPLAY_STORE_PATH, ReplayStore
from bve.pipeline.watchlist_runner import WatchlistAsset, load_watchlist_config

PriceFundamentalsFetcher = Callable[[str], dict]

_REPORT_SEPARATOR = "=" * 60
_REPO_ROOT = Path(__file__).resolve().parents[3]


class ScreenResult(BaseModel, frozen=True):
    rank: int
    ticker: str
    asset_id: str
    model_pos: float
    implied_pos: float
    pos_spread: float
    model_rnpv_millions: float
    current_ev_millions: float
    acquisition_discount: float
    clinical_stage: str
    next_catalyst: Optional[str]
    days_to_catalyst: Optional[int]
    capital_risk: Optional[str]
    market_exceeds_model: bool = False
    config_quality: Optional[str] = None
    company_action_policy: Optional[str] = None
    company_action_reason: Optional[str] = None
    company_snapshot_date: Optional[date] = None
    company_recency_gate_failed: bool = False


@dataclass(frozen=True)
class _CatalystSnapshot:
    label: str
    catalyst_date: Optional[date]
    days_to_catalyst: Optional[int]


class MispricingScreener:
    def __init__(
        self,
        *,
        solver: Optional[ImpliedPoSSolver] = None,
        as_of_date: Optional[date] = None,
        output_dir: str | Path = "outputs/analysis",
        replay_store_path: str | Path | None = None,
        knowledge_db_path: str | Path | None = None,
        persist_screen_snapshots: bool = False,
        prefer_stored_snapshots: bool = False,
        fundamentals_fetcher: Optional[PriceFundamentalsFetcher] = None,
    ) -> None:
        self.solver = solver or ImpliedPoSSolver()
        self.as_of_date = as_of_date or date.today()
        self.output_dir = Path(output_dir)
        self.replay_store_path = Path(replay_store_path) if replay_store_path else REPLAY_STORE_PATH
        self.knowledge_db_path = Path(knowledge_db_path) if knowledge_db_path else None
        self.persist_screen_snapshots = bool(persist_screen_snapshots)
        self.prefer_stored_snapshots = bool(prefer_stored_snapshots)
        self.fundamentals_fetcher = fundamentals_fetcher or get_fundamentals
        self.last_csv_path: Optional[Path] = None
        self.last_watchlist_count: int = 0
        self.last_resolved_snapshot_date: Optional[date] = None
        self.last_company_gate_exclusions: list[dict[str, str]] = []

    def screen(
        self,
        watchlist_path: str,
        price_source: str = "yfinance",
    ) -> list[ScreenResult]:
        if price_source not in {"yfinance", "replay_store"}:
            raise ValueError("price_source must be 'yfinance' or 'replay_store'")

        resolved_watchlist = _resolve_watchlist_path(watchlist_path)
        config = load_watchlist_config(resolved_watchlist)
        self.last_watchlist_count = len(config.watchlist)
        self.last_resolved_snapshot_date = None
        self.last_company_gate_exclusions = []

        knowledge_db_path = self._resolve_knowledge_db_path(config.knowledge_db_path)
        knowledge = self._open_knowledge_store(
            knowledge_db_path,
            create=self.persist_screen_snapshots,
        )
        replay = self._open_replay_store(required=(price_source == "replay_store"))

        try:
            if self.prefer_stored_snapshots and knowledge is not None:
                stored = self._load_from_snapshots(config.watchlist, knowledge)
                if stored:
                    self.last_csv_path = self._write_csv(stored)
                    return stored

            rows: list[ScreenResult] = []
            for watchlist_asset in config.watchlist:
                row = self._screen_asset(
                    watchlist_asset=watchlist_asset,
                    watchlist_path=resolved_watchlist,
                    price_source=price_source,
                    knowledge=knowledge,
                    replay=replay,
                )
                if row is not None:
                    rows.append(row)

            rows.sort(key=lambda row: (-row.pos_spread, row.ticker, row.asset_id))
            ranked = [
                row.model_copy(update={"rank": idx + 1})
                for idx, row in enumerate(rows)
            ]
            if self.persist_screen_snapshots and knowledge is not None:
                self._persist_screen_snapshots(ranked, knowledge)
            self.last_csv_path = self._write_csv(ranked)
            return ranked
        finally:
            if knowledge is not None:
                knowledge.close()
            if replay is not None:
                replay.close()

    def _screen_asset(
        self,
        *,
        watchlist_asset: WatchlistAsset,
        watchlist_path: Path,
        price_source: str,
        knowledge: Optional[KnowledgeStore],
        replay: Optional[ReplayStore],
    ) -> Optional[ScreenResult]:
        if not watchlist_asset.valuation_config:
            return None

        config_path = _resolve_config_path(watchlist_asset.valuation_config, watchlist_path)
        try:
            from bve.cli.run_asset import _load_config

            raw_cfg = _load_config(config_path)
        except Exception:  # noqa: BLE001
            return None

        asset_cfg = raw_cfg.get("asset", {})
        company_cfg = raw_cfg.get("company", {})
        solver_asset_id = str(asset_cfg.get("id") or watchlist_asset.asset_id)
        ticker = str(
            watchlist_asset.ticker
            or company_cfg.get("ticker")
            or solver_asset_id
        ).upper()
        company_snapshot = self._company_snapshot_on_or_before(
            knowledge=knowledge,
            ticker=ticker,
        )
        if (
            company_snapshot is not None
            and not bool(company_snapshot.get("balance_sheet_passes_recency_gate", False))
        ):
            self.last_company_gate_exclusions.append(
                {
                    "ticker": ticker,
                    "reason": "company_recency_gate_failed",
                }
            )
            return None

        market_cap_millions = self._resolve_market_cap(
            price_source=price_source,
            ticker=ticker,
            company_cfg=company_cfg,
            replay=replay,
        )
        if market_cap_millions is None or market_cap_millions <= 0:
            return None

        current_ev_millions = self._compute_enterprise_value(
            market_cap_millions=market_cap_millions,
            company_cfg=company_cfg,
        )
        if current_ev_millions <= 0:
            return None

        solved = self.solver.solve(str(config_path), current_ev_millions)
        if solved is None:
            return None

        candidate_ids = [watchlist_asset.asset_id, solver_asset_id]
        catalyst = self._lookup_next_catalyst(
            candidate_ids=candidate_ids,
            raw_cfg=raw_cfg,
            knowledge=knowledge,
        )
        capital_risk = self._lookup_capital_risk(
            candidate_ids=candidate_ids,
            company_cfg=company_cfg,
            replay=replay,
            catalyst_date=catalyst.catalyst_date if catalyst else None,
        )

        return ScreenResult(
            rank=0,
            ticker=ticker,
            asset_id=solved.asset_id,
            model_pos=solved.model_pos,
            implied_pos=solved.implied_pos,
            pos_spread=solved.pos_spread,
            model_rnpv_millions=solved.model_rnpv_millions,
            current_ev_millions=solved.current_ev_millions,
            acquisition_discount=solved.acquisition_discount,
            clinical_stage=_stage_label(str(asset_cfg.get("stage") or "unknown")),
            next_catalyst=catalyst.label if catalyst else None,
            days_to_catalyst=catalyst.days_to_catalyst if catalyst else None,
            capital_risk=capital_risk,
            market_exceeds_model=solved.market_exceeds_model,
            config_quality=_infer_config_quality(raw_cfg, config_path),
            company_action_policy=(
                str(company_snapshot.get("action_policy"))
                if company_snapshot and company_snapshot.get("action_policy")
                else None
            ),
            company_action_reason=(
                str(company_snapshot.get("action_reason"))
                if company_snapshot and company_snapshot.get("action_reason")
                else None
            ),
            company_snapshot_date=(
                company_snapshot.get("snapshot_date")
                if company_snapshot is not None
                else None
            ),
            company_recency_gate_failed=False,
        )

    def _resolve_market_cap(
        self,
        *,
        price_source: str,
        ticker: str,
        company_cfg: dict,
        replay: Optional[ReplayStore],
    ) -> Optional[float]:
        if price_source == "yfinance":
            return self._market_cap_from_yfinance(ticker=ticker, company_cfg=company_cfg)
        return self._market_cap_from_replay(
            ticker=ticker,
            company_cfg=company_cfg,
            replay=replay,
        )

    def _market_cap_from_yfinance(
        self,
        *,
        ticker: str,
        company_cfg: dict,
    ) -> Optional[float]:
        try:
            fundamentals = self.fundamentals_fetcher(ticker)
        except Exception:  # noqa: BLE001
            return None

        market_cap = fundamentals.get("market_cap_millions")
        if market_cap is not None and float(market_cap) > 0:
            return float(market_cap)

        price = fundamentals.get("current_price")
        shares = (
            fundamentals.get("shares_outstanding_millions")
            or company_cfg.get("shares_outstanding_millions")
        )
        if price and shares:
            return float(price) * float(shares)
        return None

    def _market_cap_from_replay(
        self,
        *,
        ticker: str,
        company_cfg: dict,
        replay: Optional[ReplayStore],
    ) -> Optional[float]:
        if replay is None:
            return None

        price = replay.get_price(ticker, self.as_of_date)
        shares = company_cfg.get("shares_outstanding_millions")
        if price is None or shares is None or float(shares) <= 0:
            return None
        return float(price) * float(shares)

    @staticmethod
    def _compute_enterprise_value(
        *,
        market_cap_millions: float,
        company_cfg: dict,
    ) -> float:
        cash = company_cfg.get("cash_millions")
        debt = company_cfg.get("debt_millions")
        if cash is None and debt is None:
            return round(float(market_cap_millions), 6)
        cash_value = float(cash or 0.0)
        debt_value = float(debt or 0.0)
        return round(float(market_cap_millions) - cash_value + debt_value, 6)

    def _lookup_next_catalyst(
        self,
        *,
        candidate_ids: list[str],
        raw_cfg: dict,
        knowledge: Optional[KnowledgeStore],
    ) -> Optional[_CatalystSnapshot]:
        if knowledge is not None:
            for asset_id in candidate_ids:
                events = knowledge.get_catalyst_events(asset_id=asset_id, active_only=True)
                upcoming = [
                    event
                    for event in events
                    if event.expected_date >= self.as_of_date
                ]
                if upcoming:
                    event = min(upcoming, key=lambda item: item.expected_date)
                    return _CatalystSnapshot(
                        label=event.description or event.catalyst_type.value,
                        catalyst_date=event.expected_date,
                        days_to_catalyst=(event.expected_date - self.as_of_date).days,
                    )

        upcoming_cfg = raw_cfg.get("asset", {}).get("upcoming_catalysts", []) or []
        if not upcoming_cfg:
            return None

        best_label: Optional[str] = None
        best_date: Optional[date] = None
        for entry in upcoming_cfg:
            label = str(entry.get("description") or entry.get("catalyst_type") or "Catalyst")
            parsed_date = _parse_iso_date(entry.get("expected_date"))
            if parsed_date is not None and parsed_date < self.as_of_date:
                continue
            if parsed_date is not None and (best_date is None or parsed_date < best_date):
                best_label = label
                best_date = parsed_date
            elif best_label is None:
                best_label = label

        if best_label is None:
            return None

        return _CatalystSnapshot(
            label=best_label,
            catalyst_date=best_date,
            days_to_catalyst=(
                (best_date - self.as_of_date).days if best_date is not None else None
            ),
        )

    def _lookup_capital_risk(
        self,
        *,
        candidate_ids: list[str],
        company_cfg: dict,
        replay: Optional[ReplayStore],
        catalyst_date: Optional[date],
    ) -> Optional[str]:
        if replay is not None:
            for asset_id in candidate_ids:
                risk = replay.get_capital_risk_level(asset_id, self.as_of_date)
                if risk:
                    return risk

        if catalyst_date is None:
            return None

        cash = company_cfg.get("cash_millions")
        burn_per_quarter = company_cfg.get("burn_rate_millions_per_quarter")
        if cash is None or burn_per_quarter is None or float(burn_per_quarter) <= 0:
            return None

        cash_runway_quarters = float(cash) / float(burn_per_quarter)
        risk, _ = compute_capital_risk_as_of(
            catalyst_date,
            cash_runway_quarters,
            float(burn_per_quarter) / 3.0,
            as_of=self.as_of_date,
        )
        return risk.value

    def _resolve_knowledge_db_path(self, configured_path: Optional[str]) -> Optional[Path]:
        if self.knowledge_db_path is not None:
            return self.knowledge_db_path
        if configured_path:
            return Path(configured_path)
        return None

    def _open_knowledge_store(
        self,
        db_path: Optional[Path],
        *,
        create: bool = False,
    ) -> Optional[KnowledgeStore]:
        if db_path is None:
            return None
        path = Path(db_path)
        if not path.exists() and not create:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        return KnowledgeStore(str(path))

    def _open_replay_store(self, *, required: bool) -> Optional[ReplayStore]:
        if not self.replay_store_path.exists():
            return None
        return ReplayStore(str(self.replay_store_path))

    def _company_snapshot_on_or_before(
        self,
        *,
        knowledge: Optional[KnowledgeStore],
        ticker: str,
    ) -> Optional[dict]:
        if knowledge is None:
            return None
        try:
            return knowledge.get_company_sotp_snapshot_for_ticker_on_or_before(
                ticker=ticker,
                as_of=self.as_of_date,
            )
        except Exception:
            return None

    def _write_csv(self, rows: list[ScreenResult]) -> Path:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = self.output_dir / f"mispricing_screen_{self.as_of_date.isoformat()}.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "rank",
                    "ticker",
                    "asset_id",
                    "model_pos",
                    "implied_pos",
                    "pos_spread",
                    "model_rnpv_millions",
                    "current_ev_millions",
                    "acquisition_discount",
                    "clinical_stage",
                    "next_catalyst",
                    "days_to_catalyst",
                    "capital_risk",
                    "market_exceeds_model",
                    "config_quality",
                    "company_action_policy",
                    "company_action_reason",
                    "company_snapshot_date",
                    "company_recency_gate_failed",
                ],
            )
            writer.writeheader()
            for row in rows:
                writer.writerow(
                    {
                        **row.model_dump(),
                        "company_snapshot_date": (
                            row.company_snapshot_date.isoformat()
                            if row.company_snapshot_date is not None
                            else ""
                        ),
                    }
                )
        return csv_path

    def _load_from_snapshots(
        self,
        watchlist_assets: list[WatchlistAsset],
        knowledge: KnowledgeStore,
    ) -> list[ScreenResult]:
        program_to_asset_id = {
            asset.asset_id: asset.asset_id
            for asset in watchlist_assets
            if asset.asset_id
        }
        ticker_to_asset_id = {
            str(asset.ticker).upper(): asset.asset_id
            for asset in watchlist_assets
            if asset.ticker
        }
        resolved_date, raw_rows = knowledge.get_screen_snapshots_on_or_before(
            self.as_of_date,
            limit=max(1000, len(watchlist_assets) * 10),
        )
        if resolved_date is None:
            return []

        rows: list[ScreenResult] = []
        for raw in raw_rows:
            ticker = str(raw.get("ticker") or "").upper()
            stored_asset_id = str(raw.get("asset_id") or "")
            program_label = str(raw.get("program_label") or "")
            asset_id = (
                (stored_asset_id if stored_asset_id else None)
                or program_to_asset_id.get(program_label)
                or ticker_to_asset_id.get(ticker)
            )
            if not ticker or asset_id is None:
                continue
            company_snapshot = self._company_snapshot_on_or_before(
                knowledge=knowledge,
                ticker=ticker,
            )
            if (
                company_snapshot is not None
                and not bool(company_snapshot.get("balance_sheet_passes_recency_gate", False))
            ):
                self.last_company_gate_exclusions.append(
                    {
                        "ticker": ticker,
                        "reason": "company_recency_gate_failed",
                    }
                )
                continue
            spread_pp = raw.get("spread_pp")
            acquisition_discount_pct = raw.get("acquisition_discount_pct")
            rows.append(
                ScreenResult(
                    rank=0,
                    ticker=ticker,
                    asset_id=asset_id,
                    model_pos=float(raw.get("model_pos") or 0.0),
                    implied_pos=float(raw.get("implied_pos") or 0.0),
                    pos_spread=(float(spread_pp) / 100.0) if spread_pp is not None else 0.0,
                    model_rnpv_millions=float(raw.get("rnpv_millions") or 0.0),
                    current_ev_millions=float(raw.get("ev_millions") or 0.0),
                    acquisition_discount=(
                        1.0 + (float(acquisition_discount_pct) / 100.0)
                        if acquisition_discount_pct is not None
                        else 0.0
                    ),
                    clinical_stage=_stage_label(str(raw.get("stage") or "unknown")),
                    next_catalyst=raw.get("next_catalyst"),
                    days_to_catalyst=raw.get("days_to_catalyst"),
                    capital_risk=None,
                    market_exceeds_model=bool(raw.get("market_exceeds_model", False)),
                    config_quality=raw.get("config_quality"),
                    company_action_policy=(
                        str(company_snapshot.get("action_policy"))
                        if company_snapshot and company_snapshot.get("action_policy")
                        else None
                    ),
                    company_action_reason=(
                        str(company_snapshot.get("action_reason"))
                        if company_snapshot and company_snapshot.get("action_reason")
                        else None
                    ),
                    company_snapshot_date=(
                        company_snapshot.get("snapshot_date")
                        if company_snapshot is not None
                        else None
                    ),
                    company_recency_gate_failed=False,
                )
            )

        rows.sort(key=lambda row: (-row.pos_spread, row.ticker, row.asset_id))
        ranked = [
            row.model_copy(update={"rank": idx + 1})
            for idx, row in enumerate(rows)
        ]
        self.last_resolved_snapshot_date = resolved_date
        return ranked

    def _persist_screen_snapshots(
        self,
        rows: list[ScreenResult],
        knowledge: KnowledgeStore,
    ) -> int:
        screen_rows = [
            ScreenRow(
                ticker=row.ticker,
                program_label=row.asset_id,
                stage=row.clinical_stage,
                ta="other",
                model_pos=row.model_pos,
                implied_pos=row.implied_pos,
                spread_pp=round(row.pos_spread * 100.0, 4),
                rnpv_millions=row.model_rnpv_millions,
                ev_millions=row.current_ev_millions,
                acquisition_discount_pct=_discount_multiple_to_pct(row.acquisition_discount),
                next_catalyst=row.next_catalyst or "",
                catalyst_date=None,
                days_to_catalyst=row.days_to_catalyst,
                single_asset=True,
                approximation_warning=None,
                data_date=self.as_of_date,
                asset_id=row.asset_id,
                thesis_strength=None,
                market_exceeds_model=row.market_exceeds_model,
                config_quality=row.config_quality,
            )
            for row in rows
        ]
        return knowledge.write_screen_snapshots(screen_rows, snapshot_date=self.as_of_date)


def render_screen_report(
    rows: list[ScreenResult],
    *,
    watchlist_path: str,
    as_of_date: date,
    watchlist_count: int,
    resolved_snapshot_date: Optional[date] = None,
) -> str:
    lines = [
        _REPORT_SEPARATOR,
        f"MISPRICING SCREEN — {as_of_date.isoformat()}",
        f"Watchlist: {watchlist_path} ({watchlist_count} assets)",
        _REPORT_SEPARATOR,
    ]
    if resolved_snapshot_date is not None and resolved_snapshot_date != as_of_date:
        lines.append(
            f"Using stored snapshot on or before as-of date: {resolved_snapshot_date.isoformat()}"
        )
    if not rows:
        lines.extend(
            [
                "No screenable assets.",
                _REPORT_SEPARATOR,
            ]
        )
        return "\n".join(lines)

    header = (
        f"{'Rank':<5} {'Ticker':<6} {'Stage':<7} "
        f"{'Model%':>7} {'Mkt%':>7} {'Spread':>9} "
        f"{'rNPV($M)':>9} {'EV($M)':>8} {'Disc':>6} "
        f"{'Next Catalyst':<22} {'Days':>4}"
    )
    lines.append(header)
    for row in rows:
        lines.append(
            f"{row.rank:<5} "
            f"{row.ticker:<6} "
            f"{_stage_short_label(row.clinical_stage):<7} "
            f"{row.model_pos * 100:>6.1f}% "
            f"{row.implied_pos * 100:>6.1f}% "
            f"{row.pos_spread * 100:>+8.1f}pp "
            f"{_format_money(row.model_rnpv_millions):>9} "
            f"{_format_money(row.current_ev_millions):>8} "
            f"{row.acquisition_discount:>5.2f}x "
            f"{(row.next_catalyst or '—')[:22]:<22} "
            f"{_format_days(row.days_to_catalyst):>4}"
        )
    lines.extend(
        [
            _REPORT_SEPARATOR,
            "  Positive spread = model thinks higher PoS than market (potential buy)",
            "  Negative spread = market thinks higher PoS than model (potential avoid)",
        ]
    )
    return "\n".join(lines)


def _resolve_watchlist_path(raw_path: str) -> Path:
    path = Path(raw_path).expanduser()
    if path.exists():
        return path

    candidates = [
        _REPO_ROOT / "examples" / "configs" / "watchlists" / raw_path,
        _REPO_ROOT / "examples" / "configs" / "watchlists" / Path(raw_path).name,
        _REPO_ROOT / raw_path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return path


def _resolve_config_path(raw_path: str, watchlist_path: Path) -> Path:
    path = Path(raw_path).expanduser()
    if path.exists():
        return path
    if not path.is_absolute():
        candidate = (watchlist_path.parent / path).resolve()
        if candidate.exists():
            return candidate
        repo_candidate = (_REPO_ROOT / path).resolve()
        if repo_candidate.exists():
            return repo_candidate
    return path


def _parse_iso_date(value: object) -> Optional[date]:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _stage_label(raw_stage: str) -> str:
    mapping = {
        "preclinical": "Preclinical",
        "phase_1": "Phase 1",
        "phase_2": "Phase 2",
        "phase_3": "Phase 3",
        "nda_bla": "NDA/BLA",
        "approved": "Approved",
    }
    return mapping.get(raw_stage, raw_stage)


def _stage_short_label(stage: str) -> str:
    mapping = {
        "Preclinical": "Pre",
        "Phase 1": "Ph1",
        "Phase 2": "Ph2",
        "Phase 3": "Ph3",
        "NDA/BLA": "NDA",
        "Approved": "Appr",
    }
    return mapping.get(stage, stage[:7])


def _format_money(value_millions: float) -> str:
    if abs(value_millions) >= 1000:
        return f"${value_millions / 1000:.1f}B"
    return f"${value_millions:,.0f}M"


def _format_days(value: Optional[int]) -> str:
    if value is None:
        return "—"
    return str(value)


def _discount_multiple_to_pct(value: float) -> float:
    return round((float(value) - 1.0) * 100.0, 4)


def _infer_config_quality(raw_cfg: dict, config_path: Path) -> Optional[str]:
    meta = raw_cfg.get("_meta", {}) if isinstance(raw_cfg, dict) else {}
    if isinstance(meta, dict):
        explicit = meta.get("config_quality") or meta.get("quality_tier")
        if explicit is not None:
            return str(explicit)

        source = meta.get("config_version")
        if source is not None and "auto" in str(source).lower():
            return "auto_generated"

    path_text = str(config_path).lower()
    if "replay_generated" in path_text or "auto_generated" in path_text:
        return "screening_grade"
    if "examples/configs" in path_text:
        return "curated"
    return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the watchlist implied-PoS mispricing screen")
    parser.add_argument("--watchlist", required=True, help="Path to watchlist YAML")
    parser.add_argument(
        "--as-of",
        default=None,
        help="Screen date (YYYY-MM-DD). Used for replay_store prices and stored snapshots.",
    )
    parser.add_argument(
        "--price-source",
        choices=["yfinance", "replay_store"],
        default="yfinance",
        help="Market-cap source",
    )
    parser.add_argument(
        "--replay-store",
        default=None,
        help="Override replay-store SQLite path when --price-source replay_store",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/analysis",
        help="Directory for CSV output",
    )
    parser.add_argument(
        "--knowledge-db",
        default=None,
        help="Override KnowledgeStore path used for catalyst lookup / snapshot storage",
    )
    parser.add_argument(
        "--persist-screen-snapshots",
        action="store_true",
        help="Persist watchlist screen rows into screen_snapshots",
    )
    parser.add_argument(
        "--use-stored-snapshots",
        action="store_true",
        help="Load latest stored screen snapshot on or before --as-of instead of recomputing",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    as_of_date = date.fromisoformat(args.as_of) if args.as_of else None
    screener = MispricingScreener(
        as_of_date=as_of_date,
        output_dir=args.output_dir,
        replay_store_path=args.replay_store,
        knowledge_db_path=args.knowledge_db,
        persist_screen_snapshots=args.persist_screen_snapshots,
        prefer_stored_snapshots=args.use_stored_snapshots,
    )
    rows = screener.screen(args.watchlist, price_source=args.price_source)
    print(
        render_screen_report(
            rows,
            watchlist_path=args.watchlist,
            as_of_date=screener.as_of_date,
            watchlist_count=screener.last_watchlist_count,
            resolved_snapshot_date=screener.last_resolved_snapshot_date,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
