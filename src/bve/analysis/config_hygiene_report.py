"""Non-destructive audit of replay YAML configs for input hygiene issues.

Two checks are performed:

1. LOT uptake curve audit
   Flags LineOfTherapySegment entries that explicitly set use_s_curve=False (or omit
   it entirely, which falls through to the MarketModel default) for assets whose
   therapeutic_area suggests specialty-pharma S-curve adoption should apply.
   Linear uptake front-loads revenue and overstates early discounted cash flows.

2. Price basis audit
   Flags net_price_per_patient_usd values that are suspiciously round (multiples of
   $10k or $25k) without an explicit price_basis=WAC / gross_to_net_rate config.
   Round numbers in replay configs often originated from WAC list prices; without a
   G2N haircut they overstate revenue.

This module is read-only.  It does not modify any YAML files.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


# ---------------------------------------------------------------------------
# Specialty-pharma TAs where S-curve adoption is the right default
# ---------------------------------------------------------------------------

_SPECIALTY_PHARMA_TAS: frozenset[str] = frozenset(
    {
        "oncology",
        "rare_disease",
        "rare disease",
        "cns",
        "central nervous system",
        "gene_therapy",
        "gene therapy",
        "cell_therapy",
        "cell therapy",
        "immunology",
    }
)

# Prices that are exact multiples of this threshold are flagged as suspicious.
_ROUND_PRICE_GRANULARITY_USD = 10_000.0

# If a price is above this and is a round multiple of granularity, flag it.
_ROUND_PRICE_THRESHOLD_USD = 50_000.0


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class LotUptakeFinding:
    """One LOT segment that may need its uptake curve reviewed."""

    config_file: str
    asset_id: str
    therapeutic_area: str | None
    lot_line: str
    explicit_use_s_curve: bool | None  # None = not set, False = explicitly linear
    years_to_peak: int | None
    recommendation: str


@dataclass
class PriceBasisFinding:
    """One price field that may be WAC rather than net."""

    config_file: str
    asset_id: str
    therapeutic_area: str | None
    price_field: str  # "net_price_per_patient_usd" or LOT segment location
    price_value_usd: float
    price_basis_set: str | None  # current price_basis value or None
    gross_to_net_rate_set: float | None
    recommendation: str


@dataclass
class ConfigHygieneReport:
    """Aggregate of all hygiene findings across a config directory."""

    scanned_files: int = 0
    lot_uptake_findings: list[LotUptakeFinding] = field(default_factory=list)
    price_basis_findings: list[PriceBasisFinding] = field(default_factory=list)

    @property
    def total_findings(self) -> int:
        return len(self.lot_uptake_findings) + len(self.price_basis_findings)

    def render(self) -> str:
        lines = [
            "Config Hygiene Report",
            f"  Scanned files: {self.scanned_files}",
            f"  LOT uptake findings: {len(self.lot_uptake_findings)}",
            f"  Price basis findings: {len(self.price_basis_findings)}",
        ]
        if self.lot_uptake_findings:
            lines.append("")
            lines.append("LOT uptake curve issues (linear uptake where S-curve expected):")
            for f in self.lot_uptake_findings:
                lines.append(
                    f"  [{f.config_file}] asset={f.asset_id!r} ta={f.therapeutic_area!r}"
                    f" lot={f.lot_line!r} use_s_curve={f.explicit_use_s_curve}"
                    f" → {f.recommendation}"
                )
        if self.price_basis_findings:
            lines.append("")
            lines.append("Price basis issues (suspicious round prices without explicit G2N):")
            for f in self.price_basis_findings:
                lines.append(
                    f"  [{f.config_file}] asset={f.asset_id!r} field={f.price_field!r}"
                    f" price=${f.price_value_usd:,.0f}"
                    f" price_basis={f.price_basis_set!r} g2n={f.gross_to_net_rate_set}"
                    f" → {f.recommendation}"
                )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Audit helpers
# ---------------------------------------------------------------------------


def _is_specialty_pharma(ta: str | None) -> bool:
    if ta is None:
        return False
    return ta.strip().lower() in _SPECIALTY_PHARMA_TAS


def _is_suspicious_price(price_usd: float) -> bool:
    """Return True if the price looks like a WAC list price (very round number)."""
    if price_usd < _ROUND_PRICE_THRESHOLD_USD:
        return False
    remainder = price_usd % _ROUND_PRICE_GRANULARITY_USD
    return math.isclose(remainder, 0.0, abs_tol=1.0)


def _audit_lot_segments(
    config_file: str,
    asset_id: str,
    therapeutic_area: str | None,
    lot_segments: list[dict[str, Any]],
) -> list[LotUptakeFinding]:
    findings: list[LotUptakeFinding] = []
    for seg in lot_segments:
        line = str(seg.get("line") or "unknown")
        explicit_use_s_curve = seg.get("use_s_curve")  # None, True, or False
        years_to_peak = seg.get("years_to_peak")

        if explicit_use_s_curve is False:
            # Explicitly set to linear — flag if specialty pharma TA
            if _is_specialty_pharma(therapeutic_area):
                findings.append(
                    LotUptakeFinding(
                        config_file=config_file,
                        asset_id=asset_id,
                        therapeutic_area=therapeutic_area,
                        lot_line=line,
                        explicit_use_s_curve=False,
                        years_to_peak=years_to_peak,
                        recommendation=(
                            "use_s_curve=False is set explicitly. For specialty pharma, "
                            "remove this or set use_s_curve=true to use S-curve adoption."
                        ),
                    )
                )
        elif explicit_use_s_curve is None:
            # Not set — will inherit MarketModel default (False unless TA triggers auto).
            # If the MarketModel has therapeutic_area set, MarketModel._is_specialty_pharma_ta()
            # would activate auto S-curve, so only flag when TA is present but not in the
            # model's specialty set (or TA is absent).
            if _is_specialty_pharma(therapeutic_area):
                # MarketModel._is_specialty_pharma_ta() only checks oncology/rare_disease/CNS.
                # Other specialty TAs (gene_therapy, immunology) would not get auto S-curve.
                standard_auto_set = {"oncology", "rare_disease", "cns"}
                ta_normalized = (therapeutic_area or "").strip().lower().replace(" ", "_")
                if ta_normalized not in standard_auto_set:
                    findings.append(
                        LotUptakeFinding(
                            config_file=config_file,
                            asset_id=asset_id,
                            therapeutic_area=therapeutic_area,
                            lot_line=line,
                            explicit_use_s_curve=None,
                            years_to_peak=years_to_peak,
                            recommendation=(
                                f"TA={therapeutic_area!r} is specialty pharma but not in the "
                                "auto-S-curve set (oncology/rare_disease/CNS). "
                                "Set use_s_curve=true on the LOT segment explicitly."
                            ),
                        )
                    )
    return findings


def _audit_price_basis(
    config_file: str,
    asset_id: str,
    therapeutic_area: str | None,
    raw_config: dict[str, Any],
) -> list[PriceBasisFinding]:
    findings: list[PriceBasisFinding] = []
    price_basis = raw_config.get("market_model", {}).get("price_basis")
    g2n_rate = raw_config.get("market_model", {}).get("gross_to_net_rate")

    # Check top-level net_price_per_patient_usd
    raw_price = raw_config.get("market_model", {}).get("net_price_per_patient_usd")
    if raw_price is not None:
        try:
            price_usd = float(raw_price)
        except (TypeError, ValueError):
            price_usd = 0.0
        if _is_suspicious_price(price_usd) and price_basis is None and g2n_rate is None:
            findings.append(
                PriceBasisFinding(
                    config_file=config_file,
                    asset_id=asset_id,
                    therapeutic_area=therapeutic_area,
                    price_field="net_price_per_patient_usd",
                    price_value_usd=price_usd,
                    price_basis_set=price_basis,
                    gross_to_net_rate_set=g2n_rate,
                    recommendation=(
                        f"${price_usd:,.0f} is a round number and may be a WAC list price. "
                        "If so, set price_basis=wac and gross_to_net_rate (e.g. 0.30 for "
                        "small molecule) to avoid overstating revenue."
                    ),
                )
            )

    # Check LOT segment net prices
    for seg in raw_config.get("market_model", {}).get("lines_of_therapy", []):
        seg_price = seg.get("net_price_per_patient_usd")
        if seg_price is None:
            continue
        try:
            price_usd = float(seg_price)
        except (TypeError, ValueError):
            continue
        lot_line = str(seg.get("line") or "unknown")
        # LOT segments currently have no price_basis field; any round price is suspicious.
        if _is_suspicious_price(price_usd):
            findings.append(
                PriceBasisFinding(
                    config_file=config_file,
                    asset_id=asset_id,
                    therapeutic_area=therapeutic_area,
                    price_field=f"lines_of_therapy[line={lot_line!r}].net_price_per_patient_usd",
                    price_value_usd=price_usd,
                    price_basis_set=None,
                    gross_to_net_rate_set=None,
                    recommendation=(
                        f"LOT segment {lot_line!r}: ${price_usd:,.0f} is round and may be "
                        "WAC. Verify whether G2N discounts are already embedded or add a "
                        "note confirming it is already net."
                    ),
                )
            )
    return findings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def audit_configs(config_dir: str | Path) -> ConfigHygieneReport:
    """Recursively scan *config_dir* for YAML configs and report hygiene issues.

    Only reads files — never writes or modifies anything.
    """
    report = ConfigHygieneReport()
    for yaml_path in sorted(Path(config_dir).rglob("*.yaml")):
        try:
            raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue

        report.scanned_files += 1
        config_file = str(yaml_path.relative_to(config_dir))
        asset_id = str(
            raw.get("asset_id")
            or raw.get("id")
            or yaml_path.stem
        )
        therapeutic_area = (
            raw.get("therapeutic_area")
            or raw.get("market_model", {}).get("therapeutic_area")
        )

        # LOT uptake audit
        lot_segments = raw.get("market_model", {}).get("lines_of_therapy", [])
        if isinstance(lot_segments, list):
            report.lot_uptake_findings.extend(
                _audit_lot_segments(config_file, asset_id, therapeutic_area, lot_segments)
            )

        # Price basis audit
        if "market_model" in raw:
            report.price_basis_findings.extend(
                _audit_price_basis(config_file, asset_id, therapeutic_area, raw)
            )

    return report


def main() -> None:
    import argparse
    import json as _json

    parser = argparse.ArgumentParser(description="Non-destructive YAML config hygiene audit")
    parser.add_argument("config_dir", help="Directory to scan recursively for YAML configs")
    parser.add_argument(
        "--format", choices=["report", "json"], default="report", dest="output_format"
    )
    args = parser.parse_args()

    result = audit_configs(args.config_dir)
    if args.output_format == "json":
        import dataclasses
        print(_json.dumps(dataclasses.asdict(result), indent=2))
    else:
        print(result.render())


if __name__ == "__main__":
    main()
