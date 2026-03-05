"""
Reference pricing data for biotech assets.

Since real-time pricing databases (EvaluatePharma, IQVIA, Redbook) are
behind paywalls, this module provides:
1. A curated reference table of approved drug prices
2. Heuristic pricing benchmarks by therapeutic area and modality
3. Helper to estimate WAP from comps

All prices are US Wholesale Acquisition Cost (WAC) in USD per year unless noted.
Net price = WAC × (1 - gross_to_net_discount).
"""
from __future__ import annotations

from bve.config.constants import GROSS_TO_NET_DISCOUNT

# ---------------------------------------------------------------------------
# Reference price benchmarks (USD/year WAC) by therapeutic area + modality
# Sources: SSR Health, Truven/IBM, company earnings disclosures
# ---------------------------------------------------------------------------

PRICE_BENCHMARKS: dict[str, dict[str, dict[str, float]]] = {
    "oncology": {
        "small_molecule": {"low": 80_000, "mid": 150_000, "high": 250_000},
        "biologic": {"low": 120_000, "mid": 200_000, "high": 350_000},
        "adc": {"low": 150_000, "mid": 250_000, "high": 400_000},
        "cell_therapy": {"low": 300_000, "mid": 450_000, "high": 700_000},
        "gene_therapy": {"low": 500_000, "mid": 1_000_000, "high": 3_000_000},
    },
    "rare_disease": {
        "small_molecule": {"low": 100_000, "mid": 250_000, "high": 600_000},
        "biologic": {"low": 200_000, "mid": 400_000, "high": 800_000},
        "gene_therapy": {"low": 500_000, "mid": 1_500_000, "high": 3_500_000},
        "rna_therapy": {"low": 300_000, "mid": 500_000, "high": 1_000_000},
    },
    "cns": {
        "small_molecule": {"low": 20_000, "mid": 60_000, "high": 120_000},
        "biologic": {"low": 60_000, "mid": 150_000, "high": 300_000},
        "gene_therapy": {"low": 300_000, "mid": 800_000, "high": 2_000_000},
    },
    "cardiovascular": {
        "small_molecule": {"low": 10_000, "mid": 35_000, "high": 80_000},
        "biologic": {"low": 15_000, "mid": 60_000, "high": 150_000},
    },
    "immunology": {
        "small_molecule": {"low": 25_000, "mid": 60_000, "high": 120_000},
        "biologic": {"low": 30_000, "mid": 80_000, "high": 200_000},
    },
    "infectious_disease": {
        "small_molecule": {"low": 5_000, "mid": 25_000, "high": 100_000},
        "biologic": {"low": 20_000, "mid": 60_000, "high": 150_000},
    },
}

_DEFAULT_BENCHMARK = {"low": 50_000, "mid": 120_000, "high": 300_000}


def get_wac_benchmark(
    therapeutic_area: str,
    modality: str,
    percentile: str = "mid",
) -> float:
    """
    Return WAC reference price (USD/year) for a given TA + modality.

    percentile: "low" | "mid" | "high"
    """
    ta_data = PRICE_BENCHMARKS.get(therapeutic_area, {})
    mod_data = ta_data.get(modality, _DEFAULT_BENCHMARK)
    return mod_data.get(percentile, mod_data["mid"])


def get_net_price(
    wac: float,
    modality: str = "biologic",
    custom_gtn: float | None = None,
) -> float:
    """
    Convert WAC → estimated net price after gross-to-net discount.

    custom_gtn overrides the modality default if provided.
    """
    gtn = custom_gtn if custom_gtn is not None else GROSS_TO_NET_DISCOUNT.get(modality, 0.30)
    return wac * (1.0 - gtn)


def estimate_price_from_comps(
    comp_prices: list[float],
    differentiation: str = "similar",
) -> float:
    """
    Estimate target drug price from a list of comparable drug prices.

    differentiation: "superior" (+20%), "similar" (median), "inferior" (-20%)
    """
    if not comp_prices:
        raise ValueError("comp_prices must not be empty")
    median = sorted(comp_prices)[len(comp_prices) // 2]
    premiums = {"superior": 1.20, "similar": 1.00, "inferior": 0.80}
    return median * premiums.get(differentiation, 1.0)
