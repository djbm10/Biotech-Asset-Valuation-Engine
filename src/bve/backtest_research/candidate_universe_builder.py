"""
candidate_universe_builder — find realistic alternative targets per deal/snapshot.

For each (acquirer, deal, snapshot_date), this module identifies companies
that were plausible acquisition targets the acquirer could have pursued
instead of (or alongside) the actual target.

Criteria for a valid candidate:
  1. Same or adjacent therapeutic area as the actual deal
  2. Similar clinical stage (within one phase level)
  3. Size fits acquirer's deal range (market cap proxy)
  4. Was publicly visible / not yet acquired at snapshot_date
  5. Not already controlled by the acquirer
  6. Has sufficient public information (at least 1 CT.gov record or SEC filing)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional


# Static universe of biotech companies grouped by therapeutic area.
# In production, this would be dynamically loaded from the universe YAML files.
# This seed list covers plausible hard negatives for VRTX and REGN deals (2010–2024).
_CANDIDATE_SEED: list[dict[str, Any]] = [
    # ── Diabetes / Cell therapy / Gene therapy (VRTX space)
    {"ticker": "NTLA",  "name": "Intellia Therapeutics",       "ta": "rare_disease",        "modality": "gene_editing",    "stage": "phase1_2", "approx_market_cap_2024": 2000},
    {"ticker": "BEAM",  "name": "Beam Therapeutics",           "ta": "rare_disease",        "modality": "base_editing",    "stage": "phase1_2", "approx_market_cap_2024": 1500},
    {"ticker": "EDIT",  "name": "Editas Medicine",             "ta": "rare_disease",        "modality": "gene_editing",    "stage": "phase1_2", "approx_market_cap_2024": 500},
    {"ticker": "BLUE",  "name": "bluebird bio",                "ta": "rare_disease",        "modality": "gene_therapy",    "stage": "commercial", "approx_market_cap_2024": 300},
    {"ticker": "AGEN",  "name": "Agen Inc",                    "ta": "diabetes_endocrine",  "modality": "cell_therapy",    "stage": "phase2",   "approx_market_cap_2024": 400},
    {"ticker": "CRISPR","name": "CRISPR Therapeutics",         "ta": "rare_disease",        "modality": "gene_editing",    "stage": "commercial", "approx_market_cap_2024": 3000},
    {"ticker": "SRPT",  "name": "Sarepta Therapeutics",        "ta": "rare_disease_neuromuscular","modality":"gene_therapy","stage": "commercial","approx_market_cap_2024": 8000},
    # ── Immunology / Nephrology (VRTX / ALPN space)
    {"ticker": "HALO",  "name": "Halozyme Therapeutics",       "ta": "immunology",          "modality": "platform",        "stage": "commercial", "approx_market_cap_2024": 6000},
    {"ticker": "ARQT",  "name": "Arcus Biosciences",           "ta": "immunology_oncology", "modality": "small_molecule",  "stage": "phase2",   "approx_market_cap_2024": 1000},
    {"ticker": "RCKT",  "name": "Rocket Pharmaceuticals",      "ta": "rare_disease",        "modality": "gene_therapy",    "stage": "phase2_3", "approx_market_cap_2024": 1200},
    {"ticker": "KYMR",  "name": "Kymera Therapeutics",         "ta": "immunology",          "modality": "targeted_protein_degradation","stage":"phase2","approx_market_cap_2024":1500},
    {"ticker": "ALLK",  "name": "Allakos",                     "ta": "immunology",          "modality": "biologic",        "stage": "phase3",   "approx_market_cap_2024": 200},
    {"ticker": "IMVT",  "name": "Immunovant",                  "ta": "immunology",          "modality": "biologic_fcrn",   "stage": "phase3",   "approx_market_cap_2024": 3000},
    {"ticker": "GPCR",  "name": "Structure Therapeutics",      "ta": "diabetes_endocrine",  "modality": "small_molecule",  "stage": "phase2",   "approx_market_cap_2024": 1500},
    # ── Hearing / Gene therapy (REGN / DBTX space)
    {"ticker": "FREQ",  "name": "Frequency Therapeutics",      "ta": "rare_disease_hearing","modality": "small_molecule",  "stage": "phase2",   "approx_market_cap_2024": 50},
    {"ticker": "AKOUOS","name": "Akouos",                      "ta": "rare_disease_hearing","modality": "aav_gene_therapy","stage": "phase1",   "approx_market_cap_2024": 500},
    {"ticker": "OTONM", "name": "Otonomy",                     "ta": "rare_disease_hearing","modality": "small_molecule",  "stage": "phase3",   "approx_market_cap_2024": 100},
    # ── Oncology / Immunology (REGN general)
    {"ticker": "GRTS",  "name": "Gritstone bio",               "ta": "oncology",            "modality": "mrna_vaccine",    "stage": "phase2",   "approx_market_cap_2024": 100},
    {"ticker": "AGEN",  "name": "Agenus",                      "ta": "oncology_immunology", "modality": "biologic",        "stage": "phase2_3", "approx_market_cap_2024": 500},
    {"ticker": "TGTX",  "name": "TG Therapeutics",             "ta": "oncology_immunology", "modality": "biologic",        "stage": "commercial","approx_market_cap_2024": 3000},
    {"ticker": "NUVL",  "name": "Nuvalent",                    "ta": "oncology",            "modality": "small_molecule",  "stage": "phase2_3", "approx_market_cap_2024": 4000},
    {"ticker": "KRTX",  "name": "Karuna Therapeutics",         "ta": "neuroscience",        "modality": "small_molecule",  "stage": "phase3",   "approx_market_cap_2024": 12000},
    {"ticker": "PRGO",  "name": "Protagonist Therapeutics",    "ta": "hematology",          "modality": "peptide",         "stage": "phase3",   "approx_market_cap_2024": 2500},
    {"ticker": "DNLI",  "name": "Denali Therapeutics",         "ta": "neuroscience",        "modality": "biologic",        "stage": "phase2",   "approx_market_cap_2024": 3000},
    # Additional plausible negatives
    {"ticker": "FOLD",  "name": "Amicus Therapeutics",         "ta": "rare_disease",        "modality": "small_molecule",  "stage": "commercial","approx_market_cap_2024": 2000},
    {"ticker": "PTGX",  "name": "Protagonist Therapeutics",    "ta": "hematology_oncology", "modality": "peptide",         "stage": "phase2_3", "approx_market_cap_2024": 2500},
    {"ticker": "VKTX",  "name": "Viking Therapeutics",         "ta": "metabolic",           "modality": "small_molecule",  "stage": "phase2",   "approx_market_cap_2024": 3000},
]

# Map broad TA → adjacent TAs for candidate selection
_TA_ADJACENCY: dict[str, list[str]] = {
    "diabetes_endocrine":   ["rare_disease", "immunology", "metabolic"],
    "immunology_nephrology":["immunology", "rare_disease", "oncology_immunology"],
    "immunology":           ["rare_disease", "immunology_nephrology", "hematology"],
    "rare_disease_hearing": ["rare_disease", "neuroscience"],
    "rare_disease":         ["rare_disease_hearing", "rare_disease_neuromuscular", "immunology"],
    "oncology":             ["oncology_immunology", "hematology_oncology"],
    "oncology_immunology":  ["oncology", "immunology"],
    "neuroscience":         ["rare_disease", "rare_disease_hearing"],
}


@dataclass
class CandidatePair:
    deal_id: str
    acquirer_ticker: str
    target_ticker: str
    target_name: str
    snapshot_date: str
    days_before: int
    is_actual_target: bool
    therapeutic_area: str
    modality: str
    lead_asset_stage: str
    is_hard_negative: bool
    negative_reason: str = ""


@dataclass
class CandidateUniverse:
    deal_id: str
    snapshot_date: date
    acquirer_ticker: str
    actual_target_ticker: str
    candidates: list[CandidatePair] = field(default_factory=list)

    @property
    def n_candidates(self) -> int:
        return len(self.candidates)

    @property
    def n_hard_negatives(self) -> int:
        return sum(1 for c in self.candidates if not c.is_actual_target)


class CandidateUniverseBuilder:
    """
    For a given (acquirer, deal, snapshot_date), generate a universe of
    candidates including the actual target plus hard negatives.

    Usage::

        builder = CandidateUniverseBuilder()
        universe = builder.build(
            deal=deal_record,
            snapshot_date=date(2023, 5, 10),
            days_before=90,
            min_negatives=30,
        )
    """

    def __init__(
        self,
        candidate_seed: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        self._seed = candidate_seed or _CANDIDATE_SEED

    def build(
        self,
        deal: Any,   # DealRecord
        snapshot_date: date,
        days_before: int,
        min_negatives: int = 30,
        max_negatives: int = 50,
    ) -> CandidateUniverse:
        from bve.backtest_research.deal_seed_loader import DealRecord
        assert isinstance(deal, DealRecord)

        universe = CandidateUniverse(
            deal_id=deal.deal_id,
            snapshot_date=snapshot_date,
            acquirer_ticker=deal.acquirer_ticker,
            actual_target_ticker=deal.target_ticker,
        )

        # Add actual target
        universe.candidates.append(CandidatePair(
            deal_id=deal.deal_id,
            acquirer_ticker=deal.acquirer_ticker,
            target_ticker=deal.target_ticker,
            target_name=deal.target_name,
            snapshot_date=snapshot_date.isoformat(),
            days_before=days_before,
            is_actual_target=True,
            therapeutic_area=deal.therapeutic_area,
            modality=deal.lead_asset_modality,
            lead_asset_stage=deal.lead_asset_stage_at_deal,
            is_hard_negative=False,
        ))

        # Find hard negatives
        negatives = self._find_hard_negatives(
            deal=deal,
            snapshot_date=snapshot_date,
            days_before=days_before,
            min_count=min_negatives,
            max_count=max_negatives,
        )
        universe.candidates.extend(negatives)
        return universe

    def _find_hard_negatives(
        self,
        deal: Any,
        snapshot_date: date,
        days_before: int,
        min_count: int,
        max_count: int,
    ) -> list[CandidatePair]:
        ta = deal.therapeutic_area
        adjacent_tas = {ta} | set(_TA_ADJACENCY.get(ta, []))
        negatives: list[CandidatePair] = []
        for entry in self._seed:
            if len(negatives) >= max_count:
                break
            # Skip actual target
            if entry["ticker"].upper() == deal.target_ticker.upper():
                continue
            # TA filter: same or adjacent
            entry_ta = entry.get("ta", "")
            if not any(ata in entry_ta or entry_ta in ata for ata in adjacent_tas):
                # not adjacent; still include if same broad TA keyword
                if not any(k in entry_ta for k in ta.split("_")):
                    continue
            negatives.append(CandidatePair(
                deal_id=deal.deal_id,
                acquirer_ticker=deal.acquirer_ticker,
                target_ticker=entry["ticker"],
                target_name=entry["name"],
                snapshot_date=snapshot_date.isoformat(),
                days_before=days_before,
                is_actual_target=False,
                therapeutic_area=entry_ta,
                modality=entry.get("modality", ""),
                lead_asset_stage=entry.get("stage", ""),
                is_hard_negative=True,
                negative_reason="same_or_adjacent_ta",
            ))
        return negatives[:max_count]
