"""Master target registry — TARGET_UNIVERSE_V3.

Aggregates all TA-specific target sub-registries into a single structured dict
keyed by therapeutic-area / company-class category.

Sub-registries
--------------
  target_registry_onc.py  — Section A: Oncology, Section I: Platforms/AI
  target_registry_core.py — Section B: Immunology, Section C: Rare Disease,
                            Section D: CNS
  target_registry_other.py— Section E: Cardiometabolic, Section F: Hematology,
                            Section G: Ophthalmology, Section H: Infectious Disease
  target_registry_asia.py — Section J: China, Korea, Japan, India biotech

Usage
-----
    from bve.entities.target_registry import (
        TARGET_UNIVERSE_V3,
        ALL_TARGETS,
        TARGET_BY_TICKER,
        TARGET_BY_ASSET_ID,
        STRATEGIC_BIOTECH_HYBRIDS,
    )

    # Access by category
    oncology = TARGET_UNIVERSE_V3["oncology"]
    rare_disease = TARGET_UNIVERSE_V3["rare_disease"]

    # Flat list (all categories combined)
    for t in ALL_TARGETS:
        print(t.ticker, t.mna_relevance_score)

    # Lookup by ticker or asset_id
    target = TARGET_BY_TICKER.get("RVMD")
    target = TARGET_BY_ASSET_ID.get("a-rvmd")

STRATEGIC_BIOTECH_HYBRIDS
--------------------------
Tickers that should be treated as large-cap acquirers / strategic buyers
rather than normal acquisition targets. These companies appear in the acquirer
registries and should NOT be placed in active target shortlists.
"""
from __future__ import annotations

from bve.entities.target import WatchlistTarget

from bve.entities.target_registry_onc import (
    ONCOLOGY_TARGETS,
    PLATFORM_TARGETS,
)
from bve.entities.target_registry_core import (
    IMMUNOLOGY_TARGETS,
    RARE_DISEASE_TARGETS,
    CNS_TARGETS,
)
from bve.entities.target_registry_other import (
    CARDIOMETABOLIC_TARGETS,
    HEMATOLOGY_TARGETS,
    OPHTHALMOLOGY_TARGETS,
    INFECTIOUS_DISEASE_TARGETS,
)
from bve.entities.target_registry_asia import (
    CHINA_BIOTECH_TARGETS,
    KOREA_BIOTECH_TARGETS,
    JAPAN_BIOTECH_TARGETS,
    INDIA_PHARMA_TARGETS,
)


# ---------------------------------------------------------------------------
# Companies treated as acquirers / strategic buyers — NOT active targets
# ---------------------------------------------------------------------------
# These are large-cap biotechs with the scale, cash, and BD appetite to buy
# rather than be bought. They may appear in licensing / partnership deals but
# should be excluded from buy-side shortlists.
STRATEGIC_BIOTECH_HYBRIDS: list[str] = [
    "VRTX",   # Vertex — $15B cash, CF monopoly; acquires rare disease assets
    "REGN",   # Regeneron — $10B+ cash; platform buyer (Sanofi partnership)
    "ALNY",   # Alnylam — RNAi platform; large-scale; acquires pipeline assets
    "BIIB",   # Biogen — neuroscience franchise; active acquirer
    "MRNA",   # Moderna — mRNA platform at scale; actively in-licensing
    "BNTX",   # BioNTech — oncology mRNA platform acquirer
    "SRPT",   # Sarepta — DMD gene therapy franchise; scale buyer
    "ARWR",   # Arrowhead — RNAi platform; licensing and acquisition activity
    "IONIS",  # Ionis — ASO platform; routinely acquires pipeline co-dev rights
    "BMRN",   # BioMarin — rare disease acquirer
    "UTHR",   # United Therapeutics — rare disease/organ transplant; acquirer
    "JAZZ",   # Jazz Pharma — CNS/oncology acquirer
    "NBIX",   # Neurocrine — CNS franchise; active buyer
    "INCY",   # Incyte — JAK/oncology franchise; active in-licensor / buyer
]


# ---------------------------------------------------------------------------
# TARGET_UNIVERSE_V3 — structured by therapeutic-area / company-class category
# ---------------------------------------------------------------------------
TARGET_UNIVERSE_V3: dict[str, list[WatchlistTarget]] = {
    # Section A — Oncology (precision oncology, immuno-oncology, ADC, RAS, etc.)
    "oncology": ONCOLOGY_TARGETS,

    # Section B — Immunology & Inflammation (autoimmune, TYK2, IL targets, etc.)
    "immunology": IMMUNOLOGY_TARGETS,

    # Section C — Rare Disease & Genetic Medicines (gene therapy, oligonucleotide, base editing)
    "rare_disease": RARE_DISEASE_TARGETS,

    # Section D — CNS & Neuroscience (neurodegeneration, psychiatry, epilepsy)
    "cns": CNS_TARGETS,

    # Section E — Cardiometabolic (NASH/MASH, obesity, lipids, cardiorenal)
    "cardiometabolic": CARDIOMETABOLIC_TARGETS,

    # Section F — Hematology & Complement (hemoglobinopathies, PNH, AML, MDS)
    "hematology": HEMATOLOGY_TARGETS,

    # Section G — Ophthalmology (wet AMD, geographic atrophy, gene therapy)
    "ophthalmology": OPHTHALMOLOGY_TARGETS,

    # Section H — Infectious Disease & Vaccines (RSV, flu, HBV, antifungal)
    "infectious_disease": INFECTIOUS_DISEASE_TARGETS,

    # Section I — Platform / AI Drug Discovery (RNA-seq, protein ML, sequencing)
    "platform": PLATFORM_TARGETS,

    # Section J — China Biotech (primarily licensing targets, some full M&A)
    "china_biotech": CHINA_BIOTECH_TARGETS,

    # Section J — Korea Biotech
    "korea_biotech": KOREA_BIOTECH_TARGETS,

    # Section J — Japan Biotech
    "japan_biotech": JAPAN_BIOTECH_TARGETS,

    # Section J — India Pharma (generics / biosimilar manufacturers)
    "india_pharma": INDIA_PHARMA_TARGETS,
}


# ---------------------------------------------------------------------------
# Flat list and lookup dicts
# ---------------------------------------------------------------------------
ALL_TARGETS: list[WatchlistTarget] = [
    t for targets in TARGET_UNIVERSE_V3.values() for t in targets
]

TARGET_BY_TICKER: dict[str, WatchlistTarget] = {
    t.ticker: t for t in ALL_TARGETS if t.ticker
}

TARGET_BY_ASSET_ID: dict[str, WatchlistTarget] = {
    t.asset_id: t for t in ALL_TARGETS if t.asset_id
}


# ---------------------------------------------------------------------------
# Category summary helper
# ---------------------------------------------------------------------------
def category_summary() -> dict[str, int]:
    """Return count of targets per category."""
    return {cat: len(lst) for cat, lst in TARGET_UNIVERSE_V3.items()}


def targets_by_conviction(conviction: str) -> list[WatchlistTarget]:
    """Filter ALL_TARGETS by conviction tier (high / medium / low / watch)."""
    return [t for t in ALL_TARGETS if t.conviction == conviction]


def top_mna_targets(n: int = 20) -> list[WatchlistTarget]:
    """Return top N targets by mna_relevance_score (descending)."""
    scored = [t for t in ALL_TARGETS if t.mna_relevance_score is not None]
    return sorted(scored, key=lambda t: t.mna_relevance_score or 0, reverse=True)[:n]
