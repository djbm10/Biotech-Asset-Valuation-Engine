"""
Portfolio synergy graph: identify and score complementary asset pairs.

Synergy arises when two assets together create more value than the sum of parts.
Key synergy types in biotech:
  - combination_therapy: assets work together mechanistically (e.g., PD-1 + CTLA-4)
  - label_expansion: asset A extends the indication scope of asset B
  - platform_leverage: shared biology/delivery reduces costs/risks for both
  - commercial_synergy: shared sales force, patient population, or distribution
  - pipeline_derisking: asset A validates the biology that asset B depends on
  - market_creation: asset A creates a market that asset B captures (e.g., GLP-1 + muscle loss)

Usage:
    from bve.analysis.synergy_graph import SynergyGraph, SynergyEdge, score_portfolio_synergy

    graph = SynergyGraph.from_rules()
    edges = graph.find_synergies(assets)

    # Or use canonical rule definitions
    score = score_portfolio_synergy(asset_a, asset_b)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Synergy types
# ---------------------------------------------------------------------------

class SynergyType(str, Enum):
    COMBINATION_THERAPY = "combination_therapy"
    LABEL_EXPANSION = "label_expansion"
    PLATFORM_LEVERAGE = "platform_leverage"
    COMMERCIAL_SYNERGY = "commercial_synergy"
    PIPELINE_DERISKING = "pipeline_derisking"
    MARKET_CREATION = "market_creation"


_SYNERGY_TYPE_WEIGHTS: dict[SynergyType, float] = {
    SynergyType.COMBINATION_THERAPY: 1.0,      # Highest — direct clinical value
    SynergyType.PIPELINE_DERISKING: 0.85,      # Validates shared biology
    SynergyType.MARKET_CREATION: 0.80,         # Creates new demand (GLP-1 → sarcopenia)
    SynergyType.LABEL_EXPANSION: 0.75,         # Extends indication scope
    SynergyType.PLATFORM_LEVERAGE: 0.65,       # Shared cost/risk reduction
    SynergyType.COMMERCIAL_SYNERGY: 0.55,      # Lower — indirect economic benefit
}


# ---------------------------------------------------------------------------
# Synergy rule
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SynergyRule:
    """A defined synergy pattern between two indication/MOA/target profiles."""
    rule_id: str
    synergy_type: SynergyType
    asset_a_signals: frozenset[str]   # Tokens that asset A must match
    asset_b_signals: frozenset[str]   # Tokens that asset B must match
    base_score: float                  # 0–1 strength of this synergy
    description: str
    evidence: str = ""                 # Supporting clinical/commercial rationale
    bidirectional: bool = True         # If True, A+B == B+A (usually True)


# ---------------------------------------------------------------------------
# Synergy edge (one scored pair)
# ---------------------------------------------------------------------------

@dataclass
class SynergyEdge:
    """A scored synergy relationship between two assets."""
    asset_id_a: str
    asset_id_b: str
    rule_id: str
    synergy_type: SynergyType
    score: float                   # 0–1 final weighted score
    description: str
    evidence: str = ""
    asset_a_matched_signals: list[str] = field(default_factory=list)
    asset_b_matched_signals: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        return (
            f"SynergyEdge({self.asset_id_a} ↔ {self.asset_id_b}): "
            f"{self.synergy_type.value} score={self.score:.2f} — {self.description}"
        )


# ---------------------------------------------------------------------------
# Portfolio synergy result
# ---------------------------------------------------------------------------

@dataclass
class PortfolioSynergyResult:
    """Synergy analysis over a portfolio of assets."""
    asset_ids: list[str]
    edges: list[SynergyEdge]
    total_synergy_score: float
    n_synergy_pairs: int
    top_pairs: list[SynergyEdge]

    def print_summary(self, *, top_n: int = 5) -> None:
        print(f"\nPortfolio Synergy Analysis — {len(self.asset_ids)} assets")
        print(f"  Total synergy score: {self.total_synergy_score:.2f}")
        print(f"  Synergy pairs found: {self.n_synergy_pairs}")
        if self.edges:
            print("\n  Top synergy pairs:")
            for edge in self.top_pairs[:top_n]:
                print(f"    [{edge.score:.2f}] {edge.asset_id_a} × {edge.asset_id_b}: "
                      f"{edge.synergy_type.value} — {edge.description}")


# ---------------------------------------------------------------------------
# Canonical synergy rules
# ---------------------------------------------------------------------------

_CANONICAL_RULES: list[SynergyRule] = [

    # ── Oncology combination therapy ─────────────────────────────────────────
    SynergyRule(
        rule_id="onc_pd1_ctla4_combo",
        synergy_type=SynergyType.COMBINATION_THERAPY,
        asset_a_signals=frozenset({"pd1", "pdl1", "checkpoint", "pd-1"}),
        asset_b_signals=frozenset({"ctla4", "ctla-4", "ipilimumab", "tremelimumab"}),
        base_score=0.95,
        description="PD-1/PD-L1 + CTLA-4 combination — validated in melanoma/NSCLC (Opdivo+Yervoy)",
        evidence="CheckMate-227 (NSCLC), CheckMate-067 (melanoma): combination 2-3x survival benefit vs mono",
        bidirectional=True,
    ),
    SynergyRule(
        rule_id="onc_pd1_bispecific_combo",
        synergy_type=SynergyType.COMBINATION_THERAPY,
        asset_a_signals=frozenset({"pd1", "pdl1", "checkpoint"}),
        asset_b_signals=frozenset({"bispecific", "tcell_engager", "cd3", "psma", "her2"}),
        base_score=0.80,
        description="Checkpoint + bispecific T-cell engager — backbone combo strategy",
        evidence="Multiple Ph2/3 trials show checkpoint enhances bispecific T-cell responses",
        bidirectional=True,
    ),
    SynergyRule(
        rule_id="onc_kras_sos1_combo",
        synergy_type=SynergyType.COMBINATION_THERAPY,
        asset_a_signals=frozenset({"kras", "kras_g12c", "kras_g12d", "kras_beyond_g12c"}),
        asset_b_signals=frozenset({"sos1", "mek", "erk", "egfr", "ras_pathway"}),
        base_score=0.90,
        description="KRAS inhibitor + upstream/downstream RAS pathway agent — vertical combination",
        evidence="AMG-510/sotorasib + MEK inhibitors, KRAS + SOS1 combos in NSCLC show synergy",
        bidirectional=True,
    ),
    SynergyRule(
        rule_id="onc_adv_rdc_combo",
        synergy_type=SynergyType.COMBINATION_THERAPY,
        asset_a_signals=frozenset({"adc", "antibody_drug_conjugate", "her2", "trop2"}),
        asset_b_signals=frozenset({"radiopharmaceutical", "actinium", "lutetium", "psma", "rdc"}),
        base_score=0.70,
        description="ADC + RDC payload diversity — complementary cytotoxic mechanisms",
        evidence="BMS expanding both ADC (ADC from Turning Point) and RDC (RayzeBio) platforms",
        bidirectional=True,
    ),

    # ── GLP-1 / Obesity ecosystem ─────────────────────────────────────────────
    SynergyRule(
        rule_id="glp1_muscle_sarcopenia",
        synergy_type=SynergyType.MARKET_CREATION,
        asset_a_signals=frozenset({"glp1", "glp-1", "semaglutide", "tirzepatide", "obesity", "weight_loss", "gcgr"}),
        asset_b_signals=frozenset({"sarcopenia", "muscle_loss", "muscle_atrophy", "myostatin", "activin", "skeletal_muscle"}),
        base_score=0.95,
        description="GLP-1/obesity drug creates sarcopenia market — weight loss causes 30-40% lean mass reduction",
        evidence="Semaglutide STEP trials: ~30% of weight lost is lean mass. Eli Lilly bimagrumab acquisition thesis",
        bidirectional=False,  # A creates market for B, not symmetric
    ),
    SynergyRule(
        rule_id="glp1_nash_nafld",
        synergy_type=SynergyType.LABEL_EXPANSION,
        asset_a_signals=frozenset({"glp1", "glp-1", "semaglutide", "obesity", "weight_loss"}),
        asset_b_signals=frozenset({"nash", "nafld", "mash", "steatohepatitis", "liver_fibrosis", "liver_disease"}),
        base_score=0.85,
        description="GLP-1 + NASH therapy — shared metabolic disease patient population and biology",
        evidence="Semaglutide NASH trial, tirzepatide-SURPASS-NASH: GLP-1 shows anti-NASH effect; combo with FXR/THR-β",
        bidirectional=True,
    ),
    SynergyRule(
        rule_id="glp1_cardiovascular",
        synergy_type=SynergyType.LABEL_EXPANSION,
        asset_a_signals=frozenset({"glp1", "glp-1", "obesity", "semaglutide"}),
        asset_b_signals=frozenset({"heart_failure", "hfpef", "atrial_fibrillation", "cardiovascular", "cvot"}),
        base_score=0.80,
        description="GLP-1 label expansion into HFpEF and atrial fibrillation (SELECT/STEP-HF data)",
        evidence="SELECT trial: semaglutide -20% CV events. STEP-HF: -improved HFpEF outcomes",
        bidirectional=True,
    ),

    # ── Immunology / complement ─────────────────────────────────────────────
    SynergyRule(
        rule_id="imm_baff_april_igan",
        synergy_type=SynergyType.COMBINATION_THERAPY,
        asset_a_signals=frozenset({"baff", "april", "baff_april", "taci", "blys"}),
        asset_b_signals=frozenset({"igan", "iga_nephropathy", "complement", "c3", "c5", "mesangial"}),
        base_score=0.85,
        description="BAFF/APRIL dual blockade + complement inhibition in IgAN — upstream + downstream",
        evidence="Povetacicept (BAFF/APRIL) and iptacopan (complement) target complementary IgAN mechanisms",
        bidirectional=True,
    ),
    SynergyRule(
        rule_id="imm_il17_il23_psoriasis",
        synergy_type=SynergyType.PLATFORM_LEVERAGE,
        asset_a_signals=frozenset({"il17", "il-17", "secukinumab", "ixekizumab", "bimekizumab"}),
        asset_b_signals=frozenset({"il23", "il-23", "risankizumab", "guselkumab", "psoriasis", "psa", "psorasis"}),
        base_score=0.75,
        description="IL-17 + IL-23 shared dermatology/rheumatology platform and commercial infrastructure",
        evidence="UCB (bimekizumab) and J&J (guselkumab) both pursuing psoriasis/PsA — shared dermatology field force",
        bidirectional=True,
    ),
    SynergyRule(
        rule_id="imm_dupixent_type2_wave2",
        synergy_type=SynergyType.LABEL_EXPANSION,
        asset_a_signals=frozenset({"dupilumab", "dupixent", "il4", "il13", "il-4", "il-13", "type2_inflammation"}),
        asset_b_signals=frozenset({"il33", "tslp", "ox40l", "prurigo", "atopic", "eosinophilic"}),
        base_score=0.80,
        description="Dupixent backbone + IL-33/TSLP/OX40L next-wave type-2 inflammation franchise extension",
        evidence="Regeneron itepekimab (IL-33) + Dupixent combo trials underway; Sanofi-Regeneron next-gen atopy",
        bidirectional=False,
    ),

    # ── Rare disease platform leverage ───────────────────────────────────────
    SynergyRule(
        rule_id="rare_gene_therapy_platform",
        synergy_type=SynergyType.PLATFORM_LEVERAGE,
        asset_a_signals=frozenset({"aav", "gene_therapy", "lentiviral", "ex_vivo_gene_editing", "crispr"}),
        asset_b_signals=frozenset({"sickle_cell", "beta_thalassemia", "hemophilia", "spinal_muscular_atrophy", "pmd"}),
        base_score=0.85,
        description="Gene therapy platform shared across hemoglobinopathies — manufacturing + regulatory synergy",
        evidence="BMS/Bluebird, Vertex/CRISPR Tx: shared ex vivo gene editing infrastructure across SCD/beta-thal",
        bidirectional=True,
    ),
    SynergyRule(
        rule_id="rare_rnai_platform",
        synergy_type=SynergyType.PLATFORM_LEVERAGE,
        asset_a_signals=frozenset({"rnai", "sirna", "antisense", "aso", "mrna", "oligonucleotide"}),
        asset_b_signals=frozenset({"liver", "hepatic", "aatd", "transthyretin", "attr", "hepb", "hepatology"}),
        base_score=0.80,
        description="RNAi/ASO liver delivery platform shared across hepatic disease targets",
        evidence="Alnylam inclisiran, givosiran, lumasiran — same GalNAc-siRNA platform, multiple liver targets",
        bidirectional=True,
    ),
    SynergyRule(
        rule_id="rare_cf_corrector_platform",
        synergy_type=SynergyType.PLATFORM_LEVERAGE,
        asset_a_signals=frozenset({"cftr", "cystic_fibrosis", "trikafta", "elexacaftor"}),
        asset_b_signals=frozenset({"aatd", "alpha_1_antitrypsin", "vx_634", "rare_protein_misfolding"}),
        base_score=0.75,
        description="CF corrector small molecule know-how applies to AATD protein misfolding correction",
        evidence="Vertex explicitly uses CF corrector chemistry insights for AATD (VX-634) program",
        bidirectional=True,
    ),

    # ── Neuroscience ─────────────────────────────────────────────────────────
    SynergyRule(
        rule_id="neuro_d2_serotonin_schizophrenia",
        synergy_type=SynergyType.COMBINATION_THERAPY,
        asset_a_signals=frozenset({"d2", "dopamine_d2", "muscarinergic", "m1_m4", "karxt", "xanomeline"}),
        asset_b_signals=frozenset({"5ht2a", "serotonin", "antipsychotic", "schizophrenia", "negative_symptoms"}),
        base_score=0.80,
        description="Muscarinic agonist + serotonin/D2 pathway combination for next-gen schizophrenia",
        evidence="Cobenfy (KarXT, BMS) validated muscarinic M1/M4 — GPCR biased agonism complement to D2 modulation",
        bidirectional=True,
    ),
    SynergyRule(
        rule_id="neuro_amyloid_tau",
        synergy_type=SynergyType.COMBINATION_THERAPY,
        asset_a_signals=frozenset({"amyloid", "abeta", "beta_amyloid", "lecanemab", "donanemab"}),
        asset_b_signals=frozenset({"tau", "tauopathy", "p_tau", "phospho_tau", "tangles"}),
        base_score=0.85,
        description="Amyloid clearance + tau inhibition — two-hallmark Alzheimer's combination",
        evidence="FDA supports combination development; Eisai/Biogen exploring anti-amyloid + anti-tau combo",
        bidirectional=True,
    ),

    # ── Commercial / renal ──────────────────────────────────────────────────
    SynergyRule(
        rule_id="renal_sglt2_pkd",
        synergy_type=SynergyType.COMMERCIAL_SYNERGY,
        asset_a_signals=frozenset({"sglt2", "dapagliflozin", "empagliflozin", "ckd", "diabetic_nephropathy"}),
        asset_b_signals=frozenset({"pkd", "polycystic_kidney", "igan", "iga_nephropathy", "fsgs", "nephrology"}),
        base_score=0.70,
        description="SGLT2 nephrology platform + rare kidney disease — shared nephrologist field force",
        evidence="AZ Farxiga (dapagliflozin) CKD approval + Chinook (atrasentan) IgAN acquisition: same nephro channel",
        bidirectional=True,
    ),
]


# ---------------------------------------------------------------------------
# Asset profile for synergy matching
# ---------------------------------------------------------------------------

@dataclass
class SynergyAssetProfile:
    """Minimal asset description for synergy graph scoring."""
    asset_id: str
    indication: str = ""
    therapeutic_area: str = ""
    target: str = ""
    mechanism_of_action: str = ""
    modality: str = ""
    signals: list[str] = field(default_factory=list)
    # Free-form text tokens for broad matching
    extra_tokens: list[str] = field(default_factory=list)

    @property
    def all_tokens(self) -> frozenset[str]:
        """All normalized text tokens for this asset."""
        raw = [
            self.indication, self.therapeutic_area, self.target,
            self.mechanism_of_action, self.modality,
        ] + self.signals + self.extra_tokens
        tokens: set[str] = set()
        for text in raw:
            if not text:
                continue
            normalized = text.lower().replace("-", "_").replace(" ", "_")
            tokens.add(normalized)
            # Also add the original lowercase for partial matching
            tokens.add(text.lower().strip())
        return frozenset(tokens)


# ---------------------------------------------------------------------------
# Synergy graph
# ---------------------------------------------------------------------------

class SynergyGraph:
    """Evaluate synergy between asset pairs using canonical synergy rules."""

    def __init__(self, rules: Optional[list[SynergyRule]] = None) -> None:
        self.rules = rules or _CANONICAL_RULES

    @classmethod
    def from_rules(cls, rules: Optional[list[SynergyRule]] = None) -> "SynergyGraph":
        return cls(rules=rules)

    def _tokens_match(self, asset_tokens: frozenset[str], rule_signals: frozenset[str]) -> list[str]:
        """Return the signals that matched (empty = no match)."""
        matched = []
        for signal in rule_signals:
            # Exact match or substring match
            if signal in asset_tokens or any(signal in tok or tok in signal for tok in asset_tokens):
                matched.append(signal)
        return matched

    def _score_pair(
        self,
        asset_a: SynergyAssetProfile,
        asset_b: SynergyAssetProfile,
        rule: SynergyRule,
    ) -> Optional[SynergyEdge]:
        """Try to match a rule against an asset pair. Returns None if no match."""
        a_tokens = asset_a.all_tokens
        b_tokens = asset_b.all_tokens

        # Try A→rule.asset_a + B→rule.asset_b
        a_match = self._tokens_match(a_tokens, rule.asset_a_signals)
        b_match = self._tokens_match(b_tokens, rule.asset_b_signals)

        if a_match and b_match:
            # Scale score by match coverage (fraction of signals matched)
            a_coverage = len(a_match) / len(rule.asset_a_signals)
            b_coverage = len(b_match) / len(rule.asset_b_signals)
            coverage = (a_coverage + b_coverage) / 2.0
            type_weight = _SYNERGY_TYPE_WEIGHTS.get(rule.synergy_type, 0.7)
            final_score = round(rule.base_score * coverage * type_weight, 4)
            return SynergyEdge(
                asset_id_a=asset_a.asset_id,
                asset_id_b=asset_b.asset_id,
                rule_id=rule.rule_id,
                synergy_type=rule.synergy_type,
                score=final_score,
                description=rule.description,
                evidence=rule.evidence,
                asset_a_matched_signals=a_match,
                asset_b_matched_signals=b_match,
            )

        # Try reverse B→rule.asset_a + A→rule.asset_b (if bidirectional)
        if rule.bidirectional:
            b_fwd = self._tokens_match(b_tokens, rule.asset_a_signals)
            a_fwd = self._tokens_match(a_tokens, rule.asset_b_signals)
            if b_fwd and a_fwd:
                a_coverage = len(a_fwd) / len(rule.asset_b_signals)
                b_coverage = len(b_fwd) / len(rule.asset_a_signals)
                coverage = (a_coverage + b_coverage) / 2.0
                type_weight = _SYNERGY_TYPE_WEIGHTS.get(rule.synergy_type, 0.7)
                final_score = round(rule.base_score * coverage * type_weight, 4)
                return SynergyEdge(
                    asset_id_a=asset_a.asset_id,
                    asset_id_b=asset_b.asset_id,
                    rule_id=rule.rule_id,
                    synergy_type=rule.synergy_type,
                    score=final_score,
                    description=rule.description,
                    evidence=rule.evidence,
                    asset_a_matched_signals=a_fwd,
                    asset_b_matched_signals=b_fwd,
                )
        return None

    def find_synergies(
        self,
        assets: list[SynergyAssetProfile],
        *,
        min_score: float = 0.0,
    ) -> list[SynergyEdge]:
        """Find all synergy edges among a list of assets."""
        edges: list[SynergyEdge] = []
        seen_pairs: set[frozenset[str]] = set()

        for i, asset_a in enumerate(assets):
            for asset_b in assets[i + 1:]:
                pair_key = frozenset({asset_a.asset_id, asset_b.asset_id})
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                best: Optional[SynergyEdge] = None
                for rule in self.rules:
                    edge = self._score_pair(asset_a, asset_b, rule)
                    if edge is not None and (best is None or edge.score > best.score):
                        best = edge

                if best is not None and best.score >= min_score:
                    edges.append(best)

        return sorted(edges, key=lambda e: -e.score)

    def score_pair(
        self,
        asset_a: SynergyAssetProfile,
        asset_b: SynergyAssetProfile,
    ) -> float:
        """Return the highest synergy score between two assets (0 if no rule fires)."""
        best_score = 0.0
        for rule in self.rules:
            edge = self._score_pair(asset_a, asset_b, rule)
            if edge is not None:
                best_score = max(best_score, edge.score)
        return best_score


# ---------------------------------------------------------------------------
# Portfolio scorer
# ---------------------------------------------------------------------------

def score_portfolio_synergy(
    assets: list[SynergyAssetProfile],
    *,
    rules: Optional[list[SynergyRule]] = None,
    top_n: int = 5,
) -> PortfolioSynergyResult:
    """
    Score synergy across a portfolio of assets.

    Returns a PortfolioSynergyResult with total synergy score,
    number of synergy pairs, and top-N edges.
    """
    graph = SynergyGraph.from_rules(rules)
    edges = graph.find_synergies(assets)

    total_score = sum(e.score for e in edges)
    top_pairs = edges[:top_n]

    return PortfolioSynergyResult(
        asset_ids=[a.asset_id for a in assets],
        edges=edges,
        total_synergy_score=round(total_score, 4),
        n_synergy_pairs=len(edges),
        top_pairs=top_pairs,
    )


# ---------------------------------------------------------------------------
# Acquirer-fit synergy extension
# ---------------------------------------------------------------------------

def score_acquirer_portfolio_fit(
    candidate: SynergyAssetProfile,
    existing_portfolio: list[SynergyAssetProfile],
    *,
    rules: Optional[list[SynergyRule]] = None,
) -> tuple[float, list[SynergyEdge]]:
    """
    Score how well a candidate asset fits an acquirer's existing portfolio
    based on synergy with current holdings.

    Returns (synergy_score, matching_edges).
    synergy_score is the sum of all edge scores between the candidate and
    each existing asset (capped at 1.0 per pair, summed across pairs).
    """
    graph = SynergyGraph.from_rules(rules)
    matching_edges: list[SynergyEdge] = []

    for existing_asset in existing_portfolio:
        edge = None
        best_score = 0.0
        for rule in graph.rules:
            e = graph._score_pair(candidate, existing_asset, rule)
            if e is not None and e.score > best_score:
                best_score = e.score
                edge = e
        if edge is not None:
            matching_edges.append(edge)

    matching_edges.sort(key=lambda e: -e.score)
    total_score = sum(e.score for e in matching_edges)
    return round(min(total_score, 3.0), 4), matching_edges  # cap at 3.0
