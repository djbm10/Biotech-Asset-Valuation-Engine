"""Entity resolver — maps raw names/tickers to canonical IDs.

Resolution priority:
1. Exact ticker match (fastest, highest confidence)
2. Exact alias match (case-insensitive)
3. Fuzzy name match via rapidfuzz (below threshold → ambiguous)

Ambiguous matches are queued for manual review (confidence < FUZZY_THRESHOLD).
Conflicting matches (two or more candidates with similar scores) are flagged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

try:
    from rapidfuzz import fuzz, process as rfprocess
    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False


FUZZY_THRESHOLD: float = 80.0      # minimum rapidfuzz score to accept a match
CONFLICT_GAP: float = 5.0          # if top two candidates within this score → conflict


class MatchMethod(str, Enum):
    EXACT_TICKER = "exact_ticker"
    EXACT_ALIAS = "exact_alias"
    FUZZY = "fuzzy"
    UNRESOLVED = "unresolved"


@dataclass
class ResolutionResult:
    canonical_id: Optional[str]
    canonical_name: Optional[str]
    method: MatchMethod
    confidence: float                  # 0–1
    needs_review: bool = False
    conflict: bool = False
    candidates: list[tuple[str, float]] = field(default_factory=list)  # (canonical_id, score)
    raw_input: str = ""


class EntityResolver:
    """Resolves company/asset names to canonical IDs.

    Usage::

        resolver = EntityResolver()
        resolver.register("pfizer", "Pfizer", aliases=["Pfizer Inc", "PFE", "pfz"])
        result = resolver.resolve("pfzer")   # fuzzy → pfizer
    """

    def __init__(self, fuzzy_threshold: float = FUZZY_THRESHOLD) -> None:
        self._threshold = fuzzy_threshold
        # canonical_id → {name, ticker, aliases}
        self._registry: dict[str, dict] = {}
        # flat lookup caches rebuilt on register()
        self._ticker_map: dict[str, str] = {}    # upper ticker → canonical_id
        self._alias_map: dict[str, str] = {}     # lower alias → canonical_id
        self._name_list: list[tuple[str, str]] = []  # (display_name, canonical_id)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        canonical_id: str,
        name: str,
        *,
        ticker: Optional[str] = None,
        aliases: Optional[list[str]] = None,
    ) -> None:
        """Register a canonical entity with optional ticker and aliases."""
        self._registry[canonical_id] = {
            "name": name,
            "ticker": ticker,
            "aliases": aliases or [],
        }
        self._rebuild_caches()

    def register_many(self, entries: list[dict]) -> None:
        """Register a batch. Each dict: {id, name, ticker?, aliases?}."""
        for e in entries:
            self._registry[e["id"]] = {
                "name": e["name"],
                "ticker": e.get("ticker"),
                "aliases": e.get("aliases", []),
            }
        self._rebuild_caches()

    def _rebuild_caches(self) -> None:
        self._ticker_map = {}
        self._alias_map = {}
        self._name_list = []

        for cid, meta in self._registry.items():
            if meta["ticker"]:
                self._ticker_map[meta["ticker"].upper()] = cid
            # name + all aliases in alias map
            for raw in [meta["name"]] + meta["aliases"]:
                self._alias_map[raw.lower()] = cid
            self._name_list.append((meta["name"], cid))

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve(self, raw: str) -> ResolutionResult:
        """Resolve a raw string to a canonical entity."""
        raw_stripped = raw.strip()

        # 1. Exact ticker
        upper = raw_stripped.upper()
        if upper in self._ticker_map:
            cid = self._ticker_map[upper]
            return ResolutionResult(
                canonical_id=cid,
                canonical_name=self._registry[cid]["name"],
                method=MatchMethod.EXACT_TICKER,
                confidence=1.0,
                raw_input=raw_stripped,
            )

        # 2. Exact alias (case-insensitive)
        lower = raw_stripped.lower()
        if lower in self._alias_map:
            cid = self._alias_map[lower]
            return ResolutionResult(
                canonical_id=cid,
                canonical_name=self._registry[cid]["name"],
                method=MatchMethod.EXACT_ALIAS,
                confidence=1.0,
                raw_input=raw_stripped,
            )

        # 3. Fuzzy match against canonical names
        if not self._name_list:
            return self._unresolved(raw_stripped)

        if _HAS_RAPIDFUZZ:
            results = rfprocess.extract(
                raw_stripped,
                [name for name, _ in self._name_list],
                scorer=fuzz.token_sort_ratio,
                limit=3,
            )
        else:
            # Simple character-level fallback when rapidfuzz not installed
            results = self._simple_fuzzy(raw_stripped)

        if not results:
            return self._unresolved(raw_stripped)

        top_score = results[0][1]
        top_name = results[0][0]
        top_cid = next(cid for name, cid in self._name_list if name == top_name)

        candidates = [(next(cid for n, cid in self._name_list if n == r[0]), r[1] / 100.0)
                      for r in results]

        if top_score < self._threshold:
            return ResolutionResult(
                canonical_id=None,
                canonical_name=None,
                method=MatchMethod.UNRESOLVED,
                confidence=top_score / 100.0,
                needs_review=True,
                candidates=candidates,
                raw_input=raw_stripped,
            )

        # Check for conflict (two candidates within CONFLICT_GAP)
        conflict = len(results) > 1 and (top_score - results[1][1]) < CONFLICT_GAP

        return ResolutionResult(
            canonical_id=top_cid,
            canonical_name=top_name,
            method=MatchMethod.FUZZY,
            confidence=top_score / 100.0,
            needs_review=conflict,
            conflict=conflict,
            candidates=candidates,
            raw_input=raw_stripped,
        )

    def _simple_fuzzy(self, query: str) -> list[tuple[str, float, int]]:
        """Fallback fuzzy: Jaccard similarity on character bigrams."""
        def bigrams(s: str) -> set[str]:
            s = s.lower()
            return {s[i:i+2] for i in range(len(s) - 1)}

        q_bg = bigrams(query)
        scored = []
        for name, _ in self._name_list:
            n_bg = bigrams(name)
            union = q_bg | n_bg
            sim = len(q_bg & n_bg) / len(union) * 100 if union else 0
            scored.append((name, sim, 0))
        return sorted(scored, key=lambda x: -x[1])[:3]

    def _unresolved(self, raw: str) -> ResolutionResult:
        return ResolutionResult(
            canonical_id=None,
            canonical_name=None,
            method=MatchMethod.UNRESOLVED,
            confidence=0.0,
            needs_review=True,
            raw_input=raw,
        )

    # ------------------------------------------------------------------
    # Bulk operations
    # ------------------------------------------------------------------

    def resolve_many(self, raws: list[str]) -> list[ResolutionResult]:
        return [self.resolve(r) for r in raws]

    def needs_review_count(self, results: list[ResolutionResult]) -> int:
        return sum(1 for r in results if r.needs_review)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def canonical_ids(self) -> list[str]:
        return list(self._registry.keys())

    def get_name(self, canonical_id: str) -> Optional[str]:
        meta = self._registry.get(canonical_id)
        return meta["name"] if meta else None


# ---------------------------------------------------------------------------
# Alias table — seed data for common biotech entity names
# ---------------------------------------------------------------------------

BIOTECH_ALIAS_TABLE: list[dict] = [
    # Big pharma acquirers
    {"id": "pfizer", "name": "Pfizer", "ticker": "PFE",
     "aliases": ["Pfizer Inc", "pfizer inc", "PFZ"]},
    {"id": "eli_lilly", "name": "Eli Lilly", "ticker": "LLY",
     "aliases": ["Lilly", "Eli Lilly and Company", "ELI LILLY"]},
    {"id": "merck", "name": "Merck & Co", "ticker": "MRK",
     "aliases": ["Merck", "Merck Sharp & Dohme", "MSD", "Merck & Co."]},
    {"id": "astrazeneca", "name": "AstraZeneca", "ticker": "AZN",
     "aliases": ["AZ", "Astra Zeneca", "ASTRAZENECA PLC"]},
    {"id": "bristol_myers_squibb", "name": "Bristol-Myers Squibb", "ticker": "BMY",
     "aliases": ["BMS", "Bristol Myers Squibb", "Bristol-Myers"]},
    {"id": "novartis", "name": "Novartis", "ticker": "NVS",
     "aliases": ["Novartis AG", "Novartis International"]},
    {"id": "roche", "name": "Roche", "ticker": "RHHBY",
     "aliases": ["Roche Holding", "Roche AG", "F. Hoffmann-La Roche", "Genentech"]},
    {"id": "abbvie", "name": "AbbVie", "ticker": "ABBV",
     "aliases": ["AbbVie Inc", "ABBVIE"]},
    {"id": "amgen", "name": "Amgen", "ticker": "AMGN",
     "aliases": ["Amgen Inc", "AMGEN INC"]},
    {"id": "gilead", "name": "Gilead Sciences", "ticker": "GILD",
     "aliases": ["Gilead", "Gilead Sciences Inc"]},
    {"id": "johnson_johnson", "name": "Johnson & Johnson", "ticker": "JNJ",
     "aliases": ["J&J", "Janssen", "Janssen Pharmaceuticals"]},
    {"id": "sanofi", "name": "Sanofi", "ticker": "SNY",
     "aliases": ["Sanofi SA", "Sanofi-Aventis"]},
    {"id": "gsk", "name": "GSK", "ticker": "GSK",
     "aliases": ["GlaxoSmithKline", "Glaxo Smith Kline", "GlaxoSmithKline plc"]},
    {"id": "novo_nordisk", "name": "Novo Nordisk", "ticker": "NVO",
     "aliases": ["Novo Nordisk A/S", "NNO"]},
    # Common small biotechs
    {"id": "regeneron", "name": "Regeneron", "ticker": "REGN",
     "aliases": ["Regeneron Pharmaceuticals"]},
    {"id": "biogen", "name": "Biogen", "ticker": "BIIB",
     "aliases": ["Biogen Inc"]},
    {"id": "moderna", "name": "Moderna", "ticker": "MRNA",
     "aliases": ["Moderna Inc", "MODERNA INC"]},
    {"id": "biontech", "name": "BioNTech", "ticker": "BNTX",
     "aliases": ["BioNTech SE"]},
    {"id": "vertex", "name": "Vertex Pharmaceuticals", "ticker": "VRTX",
     "aliases": ["Vertex", "VRTX", "Vertex Pharma"]},
    {"id": "alnylam", "name": "Alnylam Pharmaceuticals", "ticker": "ALNY",
     "aliases": ["Alnylam", "ALNY"]},
]


def build_default_resolver() -> EntityResolver:
    """Build a resolver pre-seeded with the standard alias table."""
    resolver = EntityResolver()
    resolver.register_many(BIOTECH_ALIAS_TABLE)
    return resolver
