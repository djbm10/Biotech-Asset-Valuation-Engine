"""
Build an expanded replay universe for the acquisition/M&A backtest.

The builder merges four existing local sources:

1. `examples/research/universe_27_baseline.json`
2. `examples/configs/universe_registry.yaml`
3. `research/mna/deal_universe_2020_2026.yaml` (public targets only)
4. `research/mna/target_monitor.yaml`

Usage
-----
    PYTHONPATH=src python -m bve.ops.replay_universe_builder
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BASELINE_UNIVERSE_PATH = REPO_ROOT / "examples" / "research" / "universe_27_baseline.json"
DEFAULT_REGISTRY_PATH = REPO_ROOT / "examples" / "configs" / "universe_registry.yaml"
DEFAULT_DEAL_UNIVERSE_PATH = REPO_ROOT / "research" / "mna" / "deal_universe_2020_2026.yaml"
DEFAULT_TARGET_MONITOR_PATH = REPO_ROOT / "research" / "mna" / "target_monitor.yaml"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "examples" / "research" / "universe_expanded_mna.yaml"
DEFAULT_REPLAY_START = date(2021, 1, 1)
DEFAULT_BENCHMARK_TICKER = "XBI"
DEFAULT_MINIMUM_NAMES = 60


@dataclass(frozen=True)
class ReplayUniverseBuildResult:
    as_of_date: date
    recommended_replay_start: date
    recommended_backfill_start: date
    recommended_backfill_end: date
    benchmark_ticker: str
    source_counts: dict[str, int]
    universe: list[dict[str, Any]]

    def to_payload(self) -> dict[str, Any]:
        return {
            "as_of_date": self.as_of_date.isoformat(),
            "benchmark_ticker": self.benchmark_ticker,
            "recommended_replay_start": self.recommended_replay_start.isoformat(),
            "recommended_backfill_start": self.recommended_backfill_start.isoformat(),
            "recommended_backfill_end": self.recommended_backfill_end.isoformat(),
            "source_counts": dict(sorted(self.source_counts.items())),
            "universe": self.universe,
        }


@dataclass(frozen=True)
class _RegistryEntry:
    ticker: str
    company_name: str
    asset_id: str
    drug_name: str
    indication: str
    therapeutic_area: str
    stage: str


@dataclass(frozen=True)
class _TargetMonitorEntry:
    company_name: str
    ticker: str
    status: str
    therapeutic_area: str
    lead_assets: str
    stage: str


def _slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value.strip())
    return "-".join(part for part in cleaned.split("-") if part)


def _stage_defaults(stage: str | None) -> tuple[float, float, str]:
    normalized = " ".join((stage or "").strip().lower().replace("_", " ").split())
    if any(
        token in normalized
        for token in ("approved", "commercial", "nda", "bla", "phase 3", "late stage", "pivotal")
    ):
        return 0.58, 0.56, "medium"
    if "phase 2" in normalized or "registrational ready" in normalized:
        return 0.54, 0.52, "medium"
    if "phase 1" in normalized:
        return 0.50, 0.48, "low-medium"
    if "preclinical" in normalized or "platform" in normalized:
        return 0.45, 0.44, "low"
    return 0.50, 0.50, "medium"


def _merge_entry(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    merged["source_tags"] = sorted(
        set(existing.get("source_tags", [])) | set(incoming.get("source_tags", []))
    )
    for key, value in incoming.items():
        if key in {"source", "source_tags"}:
            continue
        if key not in merged or merged[key] in (None, "", [], {}):
            merged[key] = value
    return merged


def _load_registry_entries(path: Path | str) -> list[_RegistryEntry]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    records = payload.get("assets", []) if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError("Universe registry must be a list or contain an 'assets' list")
    return [
        _RegistryEntry(
            ticker=str(record["ticker"]),
            company_name=str(record["company_name"]),
            asset_id=str(record["asset_id"]),
            drug_name=str(record["drug_name"]),
            indication=str(record["indication"]),
            therapeutic_area=str(record["therapeutic_area"]),
            stage=str(record["stage"]),
        )
        for record in records
    ]


def _load_target_monitor_entries(path: Path | str) -> tuple[date, list[_TargetMonitorEntry]]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("Target monitor YAML must be a mapping with 'as_of_date' and 'targets'")
    as_of_date = date.fromisoformat(str(payload["as_of_date"]))
    targets = payload.get("targets", [])
    if not isinstance(targets, list):
        raise ValueError("Target monitor YAML must contain a 'targets' list")
    return as_of_date, [
        _TargetMonitorEntry(
            company_name=str(target["company_name"]),
            ticker=str(target["ticker"]),
            status=str(target["status"]),
            therapeutic_area=str(target["therapeutic_area"]),
            lead_assets=str(target["lead_assets"]),
            stage=str(target["stage"]),
        )
        for target in targets
    ]


class ReplayUniverseBuilder:
    """Merge local replay, watchlist, and M&A research into one replay universe."""

    def __init__(
        self,
        *,
        baseline_universe_path: Path | str = DEFAULT_BASELINE_UNIVERSE_PATH,
        registry_path: Path | str = DEFAULT_REGISTRY_PATH,
        deal_universe_path: Path | str = DEFAULT_DEAL_UNIVERSE_PATH,
        target_monitor_path: Path | str = DEFAULT_TARGET_MONITOR_PATH,
        replay_start: date = DEFAULT_REPLAY_START,
        benchmark_ticker: str = DEFAULT_BENCHMARK_TICKER,
    ) -> None:
        self.baseline_universe_path = Path(baseline_universe_path)
        self.registry_path = Path(registry_path)
        self.deal_universe_path = Path(deal_universe_path)
        self.target_monitor_path = Path(target_monitor_path)
        self.replay_start = replay_start
        self.benchmark_ticker = benchmark_ticker.upper()

    def build(self) -> ReplayUniverseBuildResult:
        baseline = json.loads(self.baseline_universe_path.read_text(encoding="utf-8"))
        registry = _load_registry_entries(self.registry_path)
        deal_dataset = yaml.safe_load(self.deal_universe_path.read_text(encoding="utf-8")) or {}
        target_monitor_as_of, target_monitor_entries = _load_target_monitor_entries(
            self.target_monitor_path
        )

        as_of_dates = [target_monitor_as_of]
        raw_deal_as_of = deal_dataset.get("as_of_date")
        if raw_deal_as_of:
            as_of_dates.append(date.fromisoformat(str(raw_deal_as_of)))
        as_of_date = max(as_of_dates)

        merged_by_ticker: dict[str, dict[str, Any]] = {}
        source_counts = {
            "baseline_replay_universe": 0,
            "universe_registry": 0,
            "mna_public_deal_universe": 0,
            "mna_target_monitor": 0,
        }

        for entry in baseline:
            normalized = self._baseline_entry(dict(entry))
            merged_by_ticker[normalized["ticker"]] = normalized
            source_counts["baseline_replay_universe"] += 1

        for entry in registry:
            normalized = self._registry_entry(entry)
            self._upsert_by_ticker(merged_by_ticker, normalized)
            source_counts["universe_registry"] += 1

        for deal in deal_dataset.get("deals", []):
            if not isinstance(deal, dict) or not deal.get("target_ticker"):
                continue
            normalized = self._deal_entry(dict(deal))
            self._upsert_by_ticker(merged_by_ticker, normalized)
            source_counts["mna_public_deal_universe"] += 1

        for target in target_monitor_entries:
            normalized = self._target_monitor_entry(target)
            self._upsert_by_ticker(merged_by_ticker, normalized)
            source_counts["mna_target_monitor"] += 1

        universe = [
            self._finalize_entry(entry)
            for _, entry in sorted(merged_by_ticker.items(), key=lambda item: item[0])
        ]
        return ReplayUniverseBuildResult(
            as_of_date=as_of_date,
            recommended_replay_start=self.replay_start,
            recommended_backfill_start=self.replay_start,
            recommended_backfill_end=as_of_date,
            benchmark_ticker=self.benchmark_ticker,
            source_counts=source_counts,
            universe=universe,
        )

    @staticmethod
    def write(output_path: Path | str, result: ReplayUniverseBuildResult) -> Path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(
                result.to_payload(),
                sort_keys=False,
                allow_unicode=False,
            ),
            encoding="utf-8",
        )
        return path

    def _upsert_by_ticker(
        self,
        merged_by_ticker: dict[str, dict[str, Any]],
        incoming: dict[str, Any],
    ) -> None:
        ticker = incoming["ticker"]
        existing = merged_by_ticker.get(ticker)
        if existing is None:
            merged_by_ticker[ticker] = incoming
            return
        merged_by_ticker[ticker] = _merge_entry(existing, incoming)

    @staticmethod
    def _baseline_entry(entry: dict[str, Any]) -> dict[str, Any]:
        ticker = str(entry["ticker"]).upper()
        entry["ticker"] = ticker
        entry.setdefault("company_id", f"co-{ticker.lower()}")
        entry.setdefault("source", "baseline_replay_universe")
        entry.setdefault("source_tags", ["baseline_replay_universe"])
        return entry

    @staticmethod
    def _registry_entry(entry: Any) -> dict[str, Any]:
        ranking_score, opportunity_score, conviction = _stage_defaults(entry.stage)
        ticker = entry.ticker.upper()
        return {
            "ticker": ticker,
            "company_id": f"co-{ticker.lower()}",
            "asset_id": entry.asset_id,
            "company_name": entry.company_name,
            "drug_name": entry.drug_name,
            "indication": entry.indication,
            "therapeutic_area": entry.therapeutic_area,
            "stage": entry.stage,
            "ranking_score": ranking_score,
            "opportunity_score": opportunity_score,
            "conviction": conviction,
            "claim_type": "custom",
            "claim_assertion": f"{entry.drug_name} retains strategic optionality in {entry.indication}.",
            "catalyst": f"{entry.drug_name} development progress in {entry.indication}",
            "source": "universe_registry",
            "source_tags": ["universe_registry"],
        }

    @staticmethod
    def _deal_entry(deal: dict[str, Any]) -> dict[str, Any]:
        ticker = str(deal["target_ticker"]).upper()
        ranking_score, opportunity_score, conviction = _stage_defaults(
            str(deal.get("phase_at_acquisition") or "")
        )
        target_name = str(deal.get("target_name") or ticker)
        lead_asset = str(deal.get("lead_asset") or target_name)
        announcement_date = str(deal.get("announcement_date") or "")
        catalyst = lead_asset
        if announcement_date:
            catalyst = (
                f"{deal.get('acquirer', 'strategic buyer')} announced {target_name} acquisition "
                f"on {announcement_date}"
            )
        return {
            "ticker": ticker,
            "company_id": f"co-{ticker.lower()}",
            "asset_id": f"a-{ticker.lower()}",
            "company_name": target_name,
            "drug_name": lead_asset,
            "indication": str(deal.get("indication") or ""),
            "therapeutic_area": str(deal.get("therapeutic_area") or ""),
            "stage": str(deal.get("phase_at_acquisition") or ""),
            "ranking_score": ranking_score,
            "opportunity_score": opportunity_score,
            "conviction": conviction,
            "claim_type": "custom",
            "claim_assertion": (
                f"{lead_asset} could attract strategic interest in "
                f"{str(deal.get('indication') or 'its lead indication')}."
            ),
            "catalyst": catalyst,
            "announcement_date": announcement_date,
            "acquirer": str(deal.get("acquirer") or ""),
            "headline_value_millions": deal.get("headline_value_millions"),
            "comp_bucket": str(deal.get("comp_bucket") or ""),
            "source": "mna_public_deal_universe",
            "source_tags": ["mna_public_deal_universe"],
        }

    @staticmethod
    def _target_monitor_entry(target: Any) -> dict[str, Any]:
        ranking_score, opportunity_score, conviction = _stage_defaults(target.stage)
        ticker = target.ticker.upper()
        return {
            "ticker": ticker,
            "company_id": f"co-{ticker.lower()}",
            "asset_id": f"a-{ticker.lower()}",
            "company_name": target.company_name,
            "drug_name": target.lead_assets,
            "indication": target.therapeutic_area,
            "therapeutic_area": target.therapeutic_area,
            "stage": target.stage,
            "ranking_score": ranking_score,
            "opportunity_score": opportunity_score,
            "conviction": conviction,
            "claim_type": "custom",
            "claim_assertion": (
                f"{target.company_name} remains a live strategic optionality name in "
                f"{target.therapeutic_area}."
            ),
            "catalyst": f"M&A monitor: {target.lead_assets}",
            "status": target.status,
            "source": "mna_target_monitor",
            "source_tags": ["mna_target_monitor"],
        }

    @staticmethod
    def _finalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
        finalized = dict(entry)
        ticker = str(finalized["ticker"]).upper()
        finalized["ticker"] = ticker
        finalized["asset_id"] = str(finalized.get("asset_id") or f"a-{ticker.lower()}").strip()
        finalized["company_id"] = str(finalized.get("company_id") or f"co-{ticker.lower()}").strip()
        finalized["ranking_score"] = round(float(finalized.get("ranking_score", 0.50)), 4)
        finalized["opportunity_score"] = round(float(finalized.get("opportunity_score", 0.50)), 4)
        finalized["source_tags"] = sorted(str(tag) for tag in finalized.get("source_tags", []))
        if not finalized["source_tags"]:
            finalized["source_tags"] = [str(finalized.get("source") or "unknown")]
        finalized["claim_assertion"] = str(finalized.get("claim_assertion") or "")
        finalized["catalyst"] = str(finalized.get("catalyst") or "")
        finalized["company_name"] = str(finalized.get("company_name") or ticker).strip()
        return finalized


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the expanded replay universe")
    parser.add_argument("--baseline-file", default=str(DEFAULT_BASELINE_UNIVERSE_PATH))
    parser.add_argument("--registry-file", default=str(DEFAULT_REGISTRY_PATH))
    parser.add_argument("--deal-universe-file", default=str(DEFAULT_DEAL_UNIVERSE_PATH))
    parser.add_argument("--target-monitor-file", default=str(DEFAULT_TARGET_MONITOR_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument(
        "--replay-start",
        default=DEFAULT_REPLAY_START.isoformat(),
        help="Recommended replay/backfill start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--minimum-names",
        type=int,
        default=DEFAULT_MINIMUM_NAMES,
        help="Fail if the merged universe has fewer than this many distinct tickers",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    replay_start = date.fromisoformat(args.replay_start)
    builder = ReplayUniverseBuilder(
        baseline_universe_path=args.baseline_file,
        registry_path=args.registry_file,
        deal_universe_path=args.deal_universe_file,
        target_monitor_path=args.target_monitor_file,
        replay_start=replay_start,
    )
    result = builder.build()
    if len(result.universe) < args.minimum_names:
        raise SystemExit(
            f"Expanded universe too small: expected >= {args.minimum_names}, got {len(result.universe)}"
        )

    output_path = ReplayUniverseBuilder.write(args.output, result)
    print(
        "Expanded replay universe written: "
        f"{output_path} ({len(result.universe)} tickers, "
        f"replay/backfill start {result.recommended_replay_start.isoformat()}, "
        f"through {result.recommended_backfill_end.isoformat()})"
    )


if __name__ == "__main__":
    main()
