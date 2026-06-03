"""
Canonical normalizers for indication, biological target, and MOA.

Two-step pipeline:
  1. Deterministic exact-match against the synonym registry.
  2. RapidFuzz token_sort_ratio fuzzy fallback against all aliases.
     ≥ FUZZY_ACCEPT (85): MEDIUM confidence
     ≥ FUZZY_WARN  (70): LOW confidence — populated but flagged
     < FUZZY_WARN      : FAILED — canonical_id is None

Compound strings (e.g. "UC and Crohn's disease"):
  If the full string fails exact lookup, the normalizer tries splitting on
  " and " / " or " / " / " delimiters and returns the first HIGH/MEDIUM
  match from any part, flagged with "multi_entity_detected".
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from rapidfuzz import fuzz, process

from bve.normalization.registries import (
    INDICATION_ALIAS_MAP,
    INDICATION_REGISTRY,
    MOA_ALIAS_MAP,
    MOA_REGISTRY,
    TARGET_ALIAS_MAP,
    TARGET_REGISTRY,
)
from bve.normalization.types import (
    CanonicalIndication,
    CanonicalMOA,
    CanonicalTarget,
    NormalizationConfidence,
    NormalizationResult,
)

# ── Thresholds ────────────────────────────────────────────────────────────────

FUZZY_ACCEPT: int = 85   # >= MEDIUM
FUZZY_WARN: int = 70     # >= LOW; < WARN = FAILED

# Delimiters used to split compound strings
_COMPOUND_DELIMITERS = [" and ", " or ", " / ", ", "]


def _preprocess(raw: str) -> str:
    return " ".join(raw.strip().lower().split())


def _split_compound(raw: str) -> list[str]:
    """Split on known compound delimiters; return individual parts."""
    parts = [raw]
    for delim in _COMPOUND_DELIMITERS:
        new_parts: list[str] = []
        for part in parts:
            new_parts.extend(part.split(delim))
        parts = new_parts
    return [p.strip() for p in parts if p.strip() and p.strip() != raw]


# ── Abstract base ─────────────────────────────────────────────────────────────

class BaseNormalizer(ABC):

    @property
    @abstractmethod
    def _alias_map(self) -> dict[str, str]:
        """alias_text -> canonical_id"""

    @property
    @abstractmethod
    def _registry(self) -> dict:
        """canonical_id -> Canonical*"""

    def _canonical_name(self, cid: str) -> str:
        entry = self._registry.get(cid)
        return entry.name if entry else cid

    def _all_aliases(self) -> list[str]:
        return list(self._alias_map.keys())

    def _fuzzy_lookup(
        self, normalized: str
    ) -> tuple[Optional[str], float]:
        """Return (canonical_id, score) for the best fuzzy match, or (None, 0)."""
        result = process.extractOne(
            normalized,
            self._all_aliases(),
            scorer=fuzz.token_sort_ratio,
            score_cutoff=FUZZY_WARN,
        )
        if result is None:
            return None, 0.0
        matched_alias, score, _ = result
        return self._alias_map[matched_alias], float(score)

    def _top_alternatives(
        self, normalized: str, exclude_id: Optional[str] = None, limit: int = 3
    ) -> list[tuple[str, float]]:
        """Return top-N (canonical_id, score) alternatives for review."""
        candidates = process.extract(
            normalized,
            self._all_aliases(),
            scorer=fuzz.token_sort_ratio,
            limit=limit + 3,
        )
        seen: set[str] = set()
        alts: list[tuple[str, float]] = []
        for alias, score, _ in candidates:
            cid = self._alias_map[alias]
            if cid == exclude_id or cid in seen:
                continue
            seen.add(cid)
            alts.append((cid, float(score)))
            if len(alts) >= limit:
                break
        return alts

    # ── Public API ────────────────────────────────────────────────────────────

    def normalize(self, raw: str) -> NormalizationResult:
        """
        Normalize *raw* to a canonical entity.

        Returns a NormalizationResult with confidence and match_score.
        Never raises; callers check ``is_trustworthy`` before using
        ``canonical_id``.
        """
        if not raw or not raw.strip():
            return NormalizationResult(
                raw_input=raw or "",
                confidence=NormalizationConfidence.FAILED,
                method="none",
                warnings=["empty_input"],
            )

        normalized = _preprocess(raw)

        # ── Step 1: exact synonym lookup ─────────────────────────────────────
        if normalized in self._alias_map:
            cid = self._alias_map[normalized]
            return NormalizationResult(
                raw_input=raw,
                canonical_id=cid,
                canonical_name=self._canonical_name(cid),
                confidence=NormalizationConfidence.HIGH,
                match_score=100.0,
                method="exact",
                alternatives=self._top_alternatives(normalized, exclude_id=cid),
            )

        # ── Step 2: fuzzy on full string ─────────────────────────────────────
        cid, score = self._fuzzy_lookup(normalized)
        if cid is not None:
            confidence = (
                NormalizationConfidence.MEDIUM if score >= FUZZY_ACCEPT
                else NormalizationConfidence.LOW
            )
            return NormalizationResult(
                raw_input=raw,
                canonical_id=cid,
                canonical_name=self._canonical_name(cid),
                confidence=confidence,
                match_score=score,
                method="fuzzy",
                alternatives=self._top_alternatives(normalized, exclude_id=cid),
            )

        # ── Step 3: compound split fallback ──────────────────────────────────
        parts = _split_compound(normalized)
        for part in parts:
            if part in self._alias_map:
                cid = self._alias_map[part]
                return NormalizationResult(
                    raw_input=raw,
                    canonical_id=cid,
                    canonical_name=self._canonical_name(cid),
                    confidence=NormalizationConfidence.HIGH,
                    match_score=100.0,
                    method="split",
                    alternatives=self._top_alternatives(normalized, exclude_id=cid),
                    warnings=["multi_entity_detected"],
                )
            part_cid, part_score = self._fuzzy_lookup(part)
            if part_cid is not None and part_score >= FUZZY_ACCEPT:
                return NormalizationResult(
                    raw_input=raw,
                    canonical_id=part_cid,
                    canonical_name=self._canonical_name(part_cid),
                    confidence=NormalizationConfidence.MEDIUM,
                    match_score=part_score,
                    method="split",
                    alternatives=self._top_alternatives(normalized, exclude_id=part_cid),
                    warnings=["multi_entity_detected"],
                )

        # ── Step 4: FAILED ───────────────────────────────────────────────────
        return NormalizationResult(
            raw_input=raw,
            confidence=NormalizationConfidence.FAILED,
            match_score=0.0,
            method="none",
            alternatives=self._top_alternatives(normalized),
            warnings=["no_match_found"],
        )


# ── Concrete normalizers ──────────────────────────────────────────────────────

class IndicationNormalizer(BaseNormalizer):
    @property
    def _alias_map(self) -> dict[str, str]:
        return INDICATION_ALIAS_MAP

    @property
    def _registry(self) -> dict[str, CanonicalIndication]:
        return INDICATION_REGISTRY


class TargetNormalizer(BaseNormalizer):
    @property
    def _alias_map(self) -> dict[str, str]:
        return TARGET_ALIAS_MAP

    @property
    def _registry(self) -> dict[str, CanonicalTarget]:
        return TARGET_REGISTRY


class MOANormalizer(BaseNormalizer):
    @property
    def _alias_map(self) -> dict[str, str]:
        return MOA_ALIAS_MAP

    @property
    def _registry(self) -> dict[str, CanonicalMOA]:
        return MOA_REGISTRY
