"""MeaningfulnessBars — per-indication clinical-meaningfulness bars (Idea 8).

Loads ``clinical_meaningfulness_bars.yaml`` and exposes the effect-size bar that
the killer-question engine's ``DIFFERENTIATION`` archetype compares a claimed
effect against. Mirrors the ``AssumptionsLoader`` conventions: a lazily loaded
singleton, frozen (read-only) data, and an ``"other"`` fallback that emits a
``UserWarning`` so the default is visible.

Kept in a small standalone loader (not folded into ``industry_assumptions.yaml``)
so the bars table is decoupled from the core assumptions schema and its required
sections — adding/refining a bar never risks the main assumptions validation.
"""
from __future__ import annotations

import warnings
from pathlib import Path
from types import MappingProxyType
from typing import Optional

import yaml

from bve.config.assumptions_loader import _freeze

_DEFAULT_PATH = Path(__file__).parent / "clinical_meaningfulness_bars.yaml"

_EMPTY_BAR = _freeze({"clinically_meaningful_delta": None, "metric": "unspecified"})


def _normalize(indication: Optional[str]) -> str:
    return (indication or "").strip().lower().replace(" ", "_")


class MeaningfulnessBars:
    """Loads and caches the per-indication clinical-meaningfulness bars."""

    _instance: Optional["MeaningfulnessBars"] = None

    def __init__(self, path: Path = _DEFAULT_PATH) -> None:
        with open(path) as f:
            raw: dict = yaml.safe_load(f) or {}
        self._bars: MappingProxyType = _freeze(raw.get("bars", {}))
        self._meta: MappingProxyType = _freeze(raw.get("meta", {}))
        self._path = path

    @classmethod
    def get(cls) -> "MeaningfulnessBars":
        if cls._instance is None:
            cls._instance = cls(_DEFAULT_PATH)
        return cls._instance

    @classmethod
    def reset(cls, path: Optional[Path] = None) -> "MeaningfulnessBars":
        cls._instance = cls(path or _DEFAULT_PATH)
        return cls._instance

    @property
    def meta(self) -> MappingProxyType:
        return self._meta

    def bar(self, indication: Optional[str]) -> MappingProxyType:
        """Full bar entry for an indication. Falls back to 'other' with a warning."""
        key = _normalize(indication)
        if key in self._bars:
            return self._bars[key]
        warnings.warn(
            f"Indication {indication!r} not found in clinical_meaningfulness_bars.yaml. "
            "Falling back to 'other' (no indication-specific bar).",
            UserWarning,
            stacklevel=2,
        )
        return self._bars.get("other", _EMPTY_BAR)

    def delta(self, indication: Optional[str]) -> Optional[float]:
        """The clinically-meaningful effect-size delta, or None when unknown."""
        d = self.bar(indication).get("clinically_meaningful_delta")
        return None if d is None else float(d)
