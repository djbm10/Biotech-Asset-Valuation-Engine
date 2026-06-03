"""
Build an expanded Phase 2+ replay watchlist with screening-grade configs.

The builder reuses the existing config-backed stage-1 watchlist entries where
possible, then generates screening-grade YAML configs for the remaining Phase 2+
names in the expanded replay universe.

Usage
-----
    python -m bve.ops.replay_watchlist_builder
"""
from __future__ import annotations

import argparse
import sqlite3
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml

from bve.config.assumptions_loader import AssumptionsLoader


_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BASE_WATCHLIST_PATH = (
    _REPO_ROOT / "examples" / "configs" / "watchlists" / "watchlist_stage1.yaml"
)
DEFAULT_EXPANDED_UNIVERSE_PATH = _REPO_ROOT / "examples" / "research" / "universe_expanded_mna.yaml"
DEFAULT_UNIVERSE_PARAMS_PATH = _REPO_ROOT / "research" / "universe_params.yaml"
DEFAULT_REPLAY_DB_PATH = _REPO_ROOT / "outputs" / "intelligence" / "replay_store.sqlite"
DEFAULT_KNOWLEDGE_DB_PATH = _REPO_ROOT / "outputs" / "intelligence_phase2" / "knowledge.db"
DEFAULT_GENERATED_CONFIG_DIR = _REPO_ROOT / "examples" / "configs" / "replay_generated"
DEFAULT_OUTPUT_WATCHLIST_PATH = (
    _REPO_ROOT / "examples" / "configs" / "watchlists" / "watchlist_replay_expanded_phase2.yaml"
)

_DEFAULT_STAGE_MARKET_CAPS = {
    "phase_2": 1_500.0,
    "phase_3": 2_500.0,
    "nda_bla": 4_000.0,
}
_TA_MARKET_CAP_MULTIPLIERS = {
    "oncology": 1.15,
    "rare_disease": 0.90,
    "cns": 0.95,
    "cardiovascular": 1.05,
    "immunology": 1.00,
    "infectious_disease": 0.90,
    "ophthalmology": 0.85,
    "other": 1.00,
}
_STAGE_CASH_RATIOS = {
    "phase_2": 0.20,
    "phase_3": 0.15,
    "nda_bla": 0.10,
}
_STAGE_BURN_RATES = {
    "phase_2": 35.0,
    "phase_3": 45.0,
    "nda_bla": 30.0,
}
_STAGE_DISCOUNT_RATES = {
    "phase_2": 0.12,
    "phase_3": 0.11,
    "nda_bla": 0.105,
}
_TA_PEAK_PENETRATION = {
    "oncology": 0.18,
    "rare_disease": 0.30,
    "cns": 0.12,
    "cardiovascular": 0.15,
    "immunology": 0.15,
    "infectious_disease": 0.18,
    "ophthalmology": 0.18,
    "other": 0.12,
}
_STAGE_PEAK_SALES_BASE = {
    "phase_2": 1_200.0,
    "phase_3": 1_900.0,
    "nda_bla": 2_600.0,
}
_TA_PEAK_SALES_MULTIPLIERS = {
    "oncology": 1.20,
    "rare_disease": 0.85,
    "cns": 0.95,
    "cardiovascular": 1.05,
    "immunology": 1.00,
    "infectious_disease": 0.90,
    "ophthalmology": 0.85,
    "other": 1.00,
}
_TA_ALIASES = {
    "genetic medicine": "rare_disease",
}
_MODALITY_ALIASES = {
    "cell_gene": "gene_therapy",
    "cell_therapy": "cell_therapy",
    "gene_therapy": "gene_therapy",
    "rna_therapy": "rna_therapy",
}
_PHASE_CHAIN = {
    "phase_2": ["phase_2", "phase_3", "nda_bla"],
    "phase_3": ["phase_3", "nda_bla"],
    "nda_bla": ["nda_bla"],
}


@dataclass(frozen=True)
class ReplayWatchlistBuildResult:
    watchlist: list[dict[str, Any]]
    generated_configs: dict[str, dict[str, Any]]
    reused_count: int
    generated_count: int
    total_count: int


class ReplayWatchlistBuilder:
    def __init__(
        self,
        *,
        base_watchlist_path: Path | str = DEFAULT_BASE_WATCHLIST_PATH,
        expanded_universe_path: Path | str = DEFAULT_EXPANDED_UNIVERSE_PATH,
        universe_params_path: Path | str = DEFAULT_UNIVERSE_PARAMS_PATH,
        replay_db_path: Path | str = DEFAULT_REPLAY_DB_PATH,
        knowledge_db_path: Path | str = DEFAULT_KNOWLEDGE_DB_PATH,
        generated_config_dir: Path | str = DEFAULT_GENERATED_CONFIG_DIR,
        output_watchlist_path: Path | str = DEFAULT_OUTPUT_WATCHLIST_PATH,
    ) -> None:
        self.base_watchlist_path = Path(base_watchlist_path)
        self.expanded_universe_path = Path(expanded_universe_path)
        self.universe_params_path = Path(universe_params_path)
        self.replay_db_path = Path(replay_db_path)
        self.knowledge_db_path = Path(knowledge_db_path)
        self.generated_config_dir = Path(generated_config_dir)
        self.output_watchlist_path = Path(output_watchlist_path)
        self.assumptions = AssumptionsLoader.get()

    def build(self) -> ReplayWatchlistBuildResult:
        base_watchlist = _load_watchlist(self.base_watchlist_path)
        expanded_universe = _load_expanded_universe(self.expanded_universe_path)
        params = _load_universe_params(self.universe_params_path)
        replay_prices = _load_latest_replay_prices(self.replay_db_path)
        stage_market_caps = _calibrate_stage_market_caps(
            base_watchlist=base_watchlist,
            base_watchlist_path=self.base_watchlist_path,
            knowledge_db_path=self.knowledge_db_path,
        )

        reused_by_ticker: dict[str, dict[str, Any]] = {}
        for item in base_watchlist:
            raw_config = item.get("valuation_config")
            if not raw_config:
                continue
            config_path = _resolve_config_path(str(raw_config), self.base_watchlist_path)
            stage = _config_stage(config_path)
            if not _is_phase2_plus(stage):
                continue
            ticker = str(item.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            reused_by_ticker[ticker] = {
                "company_id": item.get("company_id") or f"co-{ticker.lower()}",
                "asset_id": item.get("asset_id") or _asset_id_from_ticker(ticker),
                "drug_name": item.get("drug_name") or ticker,
                "indication": item.get("indication") or str(item.get("drug_name") or ticker),
                "ticker": ticker,
                "valuation_config": str(raw_config),
            }

        generated_configs: dict[str, dict[str, Any]] = {}
        generated_watchlist_entries: dict[str, dict[str, Any]] = {}
        for entry in expanded_universe:
            ticker = str(entry.get("ticker") or "").strip().upper()
            if not ticker or ticker in reused_by_ticker:
                continue
            stage = _entry_stage(entry, params.get(ticker))
            if not _is_phase2_plus(stage):
                continue

            payload = _build_generated_config(
                ticker=ticker,
                expanded_entry=entry,
                params_entry=params.get(ticker),
                replay_prices=replay_prices,
                stage_market_caps=stage_market_caps,
                assumptions=self.assumptions,
            )
            generated_configs[ticker] = payload
            generated_watchlist_entries[ticker] = {
                "company_id": payload["company"]["id"],
                "asset_id": payload["asset"]["id"],
                "drug_name": payload["asset"]["name"],
                "indication": payload["asset"]["indication"],
                "ticker": ticker,
                "valuation_config": str(
                    _watchlist_config_reference(
                        self.generated_config_dir / f"{ticker.lower()}.yaml"
                    )
                ),
            }

        combined = {**reused_by_ticker, **generated_watchlist_entries}
        ordered_watchlist = [combined[ticker] for ticker in sorted(combined)]
        return ReplayWatchlistBuildResult(
            watchlist=ordered_watchlist,
            generated_configs=dict(sorted(generated_configs.items())),
            reused_count=len(reused_by_ticker),
            generated_count=len(generated_configs),
            total_count=len(ordered_watchlist),
        )

    def write(self, result: ReplayWatchlistBuildResult) -> tuple[Path, list[Path]]:
        self.generated_config_dir.mkdir(parents=True, exist_ok=True)
        written_configs: list[Path] = []
        for ticker, payload in result.generated_configs.items():
            path = self.generated_config_dir / f"{ticker.lower()}.yaml"
            path.write_text(
                yaml.safe_dump(payload, sort_keys=False, allow_unicode=False),
                encoding="utf-8",
            )
            written_configs.append(path)

        self.output_watchlist_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_watchlist_path.write_text(
            yaml.safe_dump({"watchlist": result.watchlist}, sort_keys=False, allow_unicode=False),
            encoding="utf-8",
        )
        return self.output_watchlist_path, written_configs


def _load_watchlist(path: Path) -> list[dict[str, Any]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    records = raw.get("watchlist", []) if isinstance(raw, dict) else raw
    if not isinstance(records, list):
        raise ValueError("Watchlist must be a list or contain a 'watchlist' list")
    return [record for record in records if isinstance(record, dict)]


def _load_expanded_universe(path: Path) -> list[dict[str, Any]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    records = raw.get("universe", []) if isinstance(raw, dict) else raw
    if not isinstance(records, list):
        raise ValueError("Expanded universe YAML must be a list or contain a 'universe' list")
    return [record for record in records if isinstance(record, dict)]


def _load_universe_params(path: Path) -> dict[str, dict[str, Any]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    params = raw.get("universe", {})
    if not isinstance(params, dict):
        raise ValueError("Universe params YAML must contain a top-level 'universe' mapping")
    return {str(ticker).upper(): dict(entry) for ticker, entry in params.items() if isinstance(entry, dict)}


def _resolve_config_path(raw_path: str, watchlist_path: Path) -> Path:
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    candidate = (watchlist_path.parent / path).resolve()
    if candidate.exists():
        return candidate
    return (_REPO_ROOT / path).resolve()


def _watchlist_config_reference(config_path: Path) -> Path:
    try:
        return config_path.resolve().relative_to(_REPO_ROOT)
    except ValueError:
        return config_path.resolve()


def _config_stage(config_path: Path) -> str:
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    asset = raw.get("asset", {}) if isinstance(raw, dict) else {}
    return _normalize_stage(str(asset.get("stage") or "phase_2"))


def _entry_stage(expanded_entry: dict[str, Any], params_entry: Optional[dict[str, Any]]) -> str:
    if params_entry:
        return _normalize_stage(str(params_entry.get("phase") or "phase_2"))
    return _normalize_stage(str(expanded_entry.get("stage") or "phase_2"))


def _normalize_stage(raw_stage: str) -> str:
    text = " ".join(str(raw_stage or "").strip().lower().replace("_", " ").split())
    if "approved" in text or "nda" in text or "bla" in text:
        return "nda_bla"
    if "phase 3" in text or "late stage" in text or "registrational" in text:
        return "phase_3"
    if "phase 2" in text:
        return "phase_2"
    return "phase_1"


def _is_phase2_plus(stage: str) -> bool:
    return stage in {"phase_2", "phase_3", "nda_bla"}


def _normalize_ta(raw_ta: Optional[str]) -> str:
    text = str(raw_ta or "other").strip().lower().replace("_", " ")
    normalized = _TA_ALIASES.get(text, text)
    valid = {
        "oncology",
        "rare disease",
        "cns",
        "cardiovascular",
        "immunology",
        "infectious disease",
        "ophthalmology",
        "other",
    }
    if normalized not in valid:
        return "other"
    return normalized.replace(" ", "_")


def _normalize_modality(raw_modality: Optional[str], expanded_entry: dict[str, Any]) -> str:
    text = str(raw_modality or "").strip().lower()
    if text in _MODALITY_ALIASES:
        return _MODALITY_ALIASES[text]
    valid = {"small_molecule", "biologic", "gene_therapy", "cell_therapy", "adc", "rna_therapy", "other"}
    if text in valid:
        return text

    haystack = " ".join(
        str(expanded_entry.get(field) or "")
        for field in ("drug_name", "indication", "claim_assertion")
    ).lower()
    if "adc" in haystack:
        return "adc"
    if "rna" in haystack or "sirna" in haystack:
        return "rna_therapy"
    if "gene" in haystack or "editing" in haystack or "crispr" in haystack:
        return "gene_therapy"
    if "antibody" in haystack or "mab" in haystack:
        return "biologic"
    return "small_molecule"


def _asset_id_from_ticker(ticker: str) -> str:
    return f"asset-{ticker.lower()}"


def _slugify(value: str) -> str:
    parts = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    return "-".join(part for part in parts.split("-") if part)


def _derive_drug_name(ticker: str, expanded_entry: dict[str, Any], params_entry: Optional[dict[str, Any]]) -> str:
    raw_name = str(expanded_entry.get("drug_name") or "").strip()
    if raw_name:
        return raw_name
    if params_entry:
        label = str(params_entry.get("program_label") or ticker)
        for separator in (" - ", " -", " - ", " — ", " —"):
            if separator in label:
                return label.split(separator, 1)[0].strip()
        return label.split("—", 1)[0].strip()
    return ticker


def _derive_indication(ticker: str, expanded_entry: dict[str, Any], params_entry: Optional[dict[str, Any]]) -> str:
    indication = str(expanded_entry.get("indication") or "").strip()
    if indication:
        return indication
    if params_entry:
        label = str(params_entry.get("program_label") or ticker)
        if "—" in label:
            return label.split("—", 1)[1].strip()
        if "-" in label:
            return label.split("-", 1)[1].strip()
    return ticker


def _derive_asset_id(ticker: str, drug_name: str, expanded_entry: dict[str, Any]) -> str:
    raw_asset_id = str(expanded_entry.get("asset_id") or "").strip()
    if raw_asset_id:
        return raw_asset_id
    return f"asset-{ticker.lower()}-{_slugify(drug_name)}"


def _load_latest_replay_prices(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    conn = sqlite3.connect(path)
    try:
        rows = conn.execute(
            "SELECT hp.ticker, hp.close_usd "
            "FROM historical_prices hp "
            "JOIN ("
            "  SELECT ticker, MAX(price_date) AS max_date "
            "  FROM historical_prices "
            "  GROUP BY ticker"
            ") latest "
            "ON hp.ticker = latest.ticker AND hp.price_date = latest.max_date"
        ).fetchall()
    finally:
        conn.close()
    return {str(ticker).upper(): float(close) for ticker, close in rows}


def _query_latest_market_cap(knowledge_db_path: Path, ticker: str) -> Optional[float]:
    if not knowledge_db_path.exists():
        return None
    conn = sqlite3.connect(knowledge_db_path)
    try:
        row = conn.execute(
            "SELECT market_cap_millions "
            "FROM market_prices "
            "WHERE ticker = ? AND market_cap_millions IS NOT NULL "
            "ORDER BY price_date DESC LIMIT 1",
            (ticker,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return float(row[0])


def _calibrate_stage_market_caps(
    *,
    base_watchlist: list[dict[str, Any]],
    base_watchlist_path: Path,
    knowledge_db_path: Path,
) -> dict[str, float]:
    buckets: dict[str, list[float]] = {stage: [] for stage in _DEFAULT_STAGE_MARKET_CAPS}
    for item in base_watchlist:
        ticker = str(item.get("ticker") or "").strip().upper()
        raw_config = item.get("valuation_config")
        if not ticker or not raw_config:
            continue
        stage = _config_stage(_resolve_config_path(str(raw_config), base_watchlist_path))
        if stage not in buckets:
            continue
        market_cap = _query_latest_market_cap(knowledge_db_path, ticker)
        if market_cap and market_cap > 0:
            buckets[stage].append(market_cap)

    calibrated = dict(_DEFAULT_STAGE_MARKET_CAPS)
    for stage, values in buckets.items():
        if values:
            calibrated[stage] = round(float(statistics.median(values)), 2)
    return calibrated


def _build_generated_config(
    *,
    ticker: str,
    expanded_entry: dict[str, Any],
    params_entry: Optional[dict[str, Any]],
    replay_prices: dict[str, float],
    stage_market_caps: dict[str, float],
    assumptions: AssumptionsLoader,
) -> dict[str, Any]:
    stage = _entry_stage(expanded_entry, params_entry)
    ta = _normalize_ta(
        params_entry.get("ta") if params_entry else expanded_entry.get("therapeutic_area")
    )
    modality = _normalize_modality(
        params_entry.get("modality") if params_entry else None,
        expanded_entry,
    )
    drug_name = _derive_drug_name(ticker, expanded_entry, params_entry)
    indication = _derive_indication(ticker, expanded_entry, params_entry)
    asset_id = _derive_asset_id(ticker, drug_name, expanded_entry)
    company_name = str(expanded_entry.get("company_name") or ticker).strip() or ticker
    current_price = float(replay_prices.get(ticker) or 10.0)

    baseline_market_cap = round(
        stage_market_caps.get(stage, _DEFAULT_STAGE_MARKET_CAPS["phase_2"])
        * _TA_MARKET_CAP_MULTIPLIERS.get(ta, 1.0),
        2,
    )
    shares = max(round(baseline_market_cap / current_price, 2), 1.0)
    cash = round(baseline_market_cap * _STAGE_CASH_RATIOS.get(stage, 0.15), 2)
    burn = _STAGE_BURN_RATES.get(stage, 35.0)
    discount_rate = round(
        float(params_entry.get("discount_rate")) if params_entry and params_entry.get("discount_rate") is not None
        else _STAGE_DISCOUNT_RATES.get(stage, 0.11),
        3,
    )

    peak_penetration = round(
        float(params_entry.get("peak_penetration")) if params_entry and params_entry.get("peak_penetration") is not None
        else _TA_PEAK_PENETRATION.get(ta, 0.12),
        3,
    )
    peak_sales = _peak_sales_millions(
        stage=stage,
        ta=ta,
        params_entry=params_entry,
        expanded_entry=expanded_entry,
    )
    total_addressable_market = round(peak_sales / peak_penetration, 2)
    patent_life = int(
        params_entry.get("patent_life_years")
        if params_entry and params_entry.get("patent_life_years") is not None
        else {"phase_2": 12, "phase_3": 10, "nda_bla": 9}.get(stage, 10)
    )

    return {
        "asset": {
            "id": asset_id,
            "name": drug_name,
            "indication": indication,
            "therapeutic_area": ta,
            "stage": stage,
            "modality": modality,
            "discount_rate": discount_rate,
        },
        "company": {
            "id": f"{ticker.lower()}-replay",
            "name": company_name,
            "ticker": ticker,
            "cash_millions": cash,
            "debt_millions": 0.0,
            "shares_outstanding_millions": shares,
            "burn_rate_millions_per_quarter": burn,
            "current_price": round(current_price, 4),
            "notes": "screening-grade replay config",
        },
        "trials": _build_trials(
            asset_id=asset_id,
            stage=stage,
            therapeutic_area=ta,
            assumptions=assumptions,
        ),
        "market_model": {
            "total_addressable_market_millions": total_addressable_market,
            "peak_penetration": peak_penetration,
            "years_to_peak": 5,
            "patent_life_years": patent_life,
            "cogs_rate": 0.15,
            "sgna_rate_launch": 0.40,
            "sgna_rate_mature": 0.20,
        },
        "_meta": {
            "config_version": "replay-screening-v1",
            "source": "replay_watchlist_builder",
            "screening_grade": True,
            "source_ticker": ticker,
            "source_universe_stage": str(expanded_entry.get("stage") or ""),
            "source_tags": expanded_entry.get("source_tags") or [expanded_entry.get("source")],
            "single_asset": bool(params_entry.get("single_asset", True)) if params_entry else True,
            "heuristic_market_cap_millions": baseline_market_cap,
            "heuristic_peak_sales_millions": peak_sales,
        },
    }


def _peak_sales_millions(
    *,
    stage: str,
    ta: str,
    params_entry: Optional[dict[str, Any]],
    expanded_entry: dict[str, Any],
) -> float:
    if params_entry and params_entry.get("peak_sales_millions") is not None:
        return round(float(params_entry["peak_sales_millions"]), 2)

    base = _STAGE_PEAK_SALES_BASE.get(stage, _STAGE_PEAK_SALES_BASE["phase_2"])
    multiplier = _TA_PEAK_SALES_MULTIPLIERS.get(ta, 1.0)
    peak_sales = base * multiplier
    headline_value = expanded_entry.get("headline_value_millions")
    if headline_value is not None:
        try:
            peak_sales = max(peak_sales, min(float(headline_value) * 0.45, 6_000.0))
        except (TypeError, ValueError):
            pass
    return round(peak_sales, 2)


def _build_trials(
    *,
    asset_id: str,
    stage: str,
    therapeutic_area: str,
    assumptions: AssumptionsLoader,
) -> list[dict[str, Any]]:
    rates = assumptions.phase_success_rates_for(therapeutic_area)
    durations = assumptions.phase_durations_years
    costs = assumptions.phase_costs_millions
    trials: list[dict[str, Any]] = []
    for phase in _PHASE_CHAIN.get(stage, ["phase_2", "phase_3", "nda_bla"]):
        trials.append(
            {
                "phase": phase,
                "success_probability": float(rates.get(phase, rates.get("phase_2", 0.35))),
                "duration_years": float(durations.get(phase, 2.5)),
                "cost_millions": float(costs.get(phase, 120.0)),
                "endpoint_type": "surrogate_validated",
                "notes": "screening-grade default trial chain",
            }
        )
    return trials


def render_build_summary(result: ReplayWatchlistBuildResult) -> str:
    return "\n".join(
        [
            "=" * 60,
            "REPLAY WATCHLIST BUILD",
            "=" * 60,
            f"Reused configs:        {result.reused_count}",
            f"Generated configs:     {result.generated_count}",
            f"Total watchlist assets:{result.total_count}",
            "=" * 60,
        ]
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the expanded Phase 2+ replay watchlist")
    parser.add_argument("--base-watchlist", default=str(DEFAULT_BASE_WATCHLIST_PATH))
    parser.add_argument("--expanded-universe", default=str(DEFAULT_EXPANDED_UNIVERSE_PATH))
    parser.add_argument("--universe-params", default=str(DEFAULT_UNIVERSE_PARAMS_PATH))
    parser.add_argument("--replay-db", default=str(DEFAULT_REPLAY_DB_PATH))
    parser.add_argument("--knowledge-db", default=str(DEFAULT_KNOWLEDGE_DB_PATH))
    parser.add_argument("--generated-config-dir", default=str(DEFAULT_GENERATED_CONFIG_DIR))
    parser.add_argument("--output-watchlist", default=str(DEFAULT_OUTPUT_WATCHLIST_PATH))
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    builder = ReplayWatchlistBuilder(
        base_watchlist_path=args.base_watchlist,
        expanded_universe_path=args.expanded_universe,
        universe_params_path=args.universe_params,
        replay_db_path=args.replay_db,
        knowledge_db_path=args.knowledge_db,
        generated_config_dir=args.generated_config_dir,
        output_watchlist_path=args.output_watchlist,
    )
    result = builder.build()
    watchlist_path, written_configs = builder.write(result)
    print(render_build_summary(result))
    print(f"Watchlist: {watchlist_path}")
    print(f"Config dir: {builder.generated_config_dir}")
    print(f"Configs written: {len(written_configs)}")


if __name__ == "__main__":
    main()
