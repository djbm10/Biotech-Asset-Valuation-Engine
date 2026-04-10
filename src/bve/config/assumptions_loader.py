"""
AssumptionsLoader — single source of truth for all calibrated industry priors.

All calibrated values (phase success rates, trial design log-odds, LOE erosion
profiles, competition haircuts, etc.) live in industry_assumptions.yaml.
This module loads, validates, and caches those values.

Design
------
Singleton with lazy initialization. Constants that previously lived in
constants.py now delegate here. All existing import paths continue to work
because constants.py re-exports the same names sourced from this loader.

Immutability
------------
All data returned by properties is frozen: dicts are wrapped in
MappingProxyType, lists converted to tuples. Mutations raise TypeError.
This prevents models from accidentally modifying shared assumption state.

Fallback warnings
-----------------
Accessors that fall back to a default (e.g. unknown therapeutic area → "other")
emit a UserWarning so the caller is aware the default was applied. This makes
assumption application visible rather than silent.

Usage
-----
Typical code should import familiar names from constants.py unchanged:

    from bve.config.constants import PHASE_SUCCESS_RATES, TRIAL_DESIGN_LOGODDS

For programmatic access to the full assumptions object:

    from bve.config.assumptions_loader import AssumptionsLoader
    a = AssumptionsLoader.get()
    rates = a.phase_success_rates_for("oncology")
    print(a.provenance())

For overriding in tests (alternate YAML file):

    AssumptionsLoader.reset(path=Path("tests/fixtures/test_assumptions.yaml"))
"""
from __future__ import annotations

import warnings
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Optional

import yaml

_DEFAULT_PATH = Path(__file__).parent / "industry_assumptions.yaml"

_REQUIRED_SECTIONS = {
    "meta",
    "phase_success_rates",
    "phase_durations_years",
    "phase_costs_millions",
    "commercial",
    "wacc",
    "monte_carlo",
    "loe_erosion_profiles",
    "competition",
    "trial_design",
}

_REQUIRED_PHASES = ("phase_1", "phase_2", "phase_3", "nda_bla")


class AssumptionsValidationError(ValueError):
    """Raised when industry_assumptions.yaml fails schema validation."""


# ---------------------------------------------------------------------------
# Freeze utility — deep immutability
# ---------------------------------------------------------------------------

def _freeze(obj: Any) -> Any:
    """
    Recursively convert dicts to MappingProxyType and lists to tuples.

    This makes all data returned by AssumptionsLoader properties effectively
    read-only at runtime. Attempts to mutate them raise TypeError.
    """
    if isinstance(obj, dict):
        return MappingProxyType({k: _freeze(v) for k, v in obj.items()})
    if isinstance(obj, list):
        return tuple(_freeze(v) for v in obj)
    return obj


class AssumptionsLoader:
    """
    Loads, validates, and caches industry_assumptions.yaml.

    All properties return frozen data (MappingProxyType / tuple). Mutations
    raise TypeError, preventing accidental modification of shared state.
    """

    _instance: Optional["AssumptionsLoader"] = None

    def __init__(self, path: Path = _DEFAULT_PATH) -> None:
        with open(path) as f:
            raw: dict = yaml.safe_load(f)
        self._data: MappingProxyType = _freeze(raw)
        self._path = path
        self._loaded_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00",
            "Z",
        )
        self._validate()

    # ------------------------------------------------------------------
    # Singleton access
    # ------------------------------------------------------------------

    @classmethod
    def get(cls) -> "AssumptionsLoader":
        """Return the cached singleton, loading from the default path if needed."""
        if cls._instance is None:
            cls._instance = cls(_DEFAULT_PATH)
        return cls._instance

    @classmethod
    def reset(cls, path: Optional[Path] = None) -> "AssumptionsLoader":
        """
        Replace the singleton with a freshly loaded instance.

        Use in tests to load an alternate YAML file. Pass None to reload the
        default file (e.g., after a test that mutated the singleton).
        """
        cls._instance = cls(path or _DEFAULT_PATH)
        return cls._instance

    # ------------------------------------------------------------------
    # Provenance
    # ------------------------------------------------------------------

    def provenance(self) -> dict[str, Any]:
        """
        Return a plain dict describing this assumptions set.

        Intended for inclusion in ValuationOutput and model result objects
        so that every output is traceable to an explicit assumption version.

        Example output::

            {
                "version": "2026-Q1",
                "path": "/path/to/industry_assumptions.yaml",
                "loaded_at": "2026-03-06T12:00:00Z",
                "sources": ["Biomedtracker/IQVIA ...", ...]
            }
        """
        return {
            "version": self.version,
            "path": str(self._path),
            "loaded_at": self._loaded_at,
            "sources": list(self.sources),
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(self) -> None:
        errors: list[str] = []

        # Required top-level sections
        for section in _REQUIRED_SECTIONS:
            if section not in self._data:
                errors.append(f"Missing required section: '{section}'")

        if errors:
            self._raise(errors)

        # phase_success_rates: each TA has all 4 phases, values in (0, 1)
        for ta, phases in self._data["phase_success_rates"].items():
            for ph in _REQUIRED_PHASES:
                if ph not in phases:
                    errors.append(f"phase_success_rates.{ta} missing phase '{ph}'")
                else:
                    v = phases[ph]
                    if not (0 < v < 1):
                        errors.append(
                            f"phase_success_rates.{ta}.{ph} = {v} must be in (0, 1)"
                        )

        # loe_erosion_profiles: loss fractions in [0, 1)
        for profile, vals in self._data["loe_erosion_profiles"].items():
            for key in ("year_1_loss", "year_2_loss", "year_3_loss", "terminal_loss"):
                if key not in vals:
                    errors.append(f"loe_erosion_profiles.{profile} missing '{key}'")
                else:
                    v = vals[key]
                    if not (0.0 <= v < 1.0):
                        errors.append(
                            f"loe_erosion_profiles.{profile}.{key} = {v} must be in [0, 1)"
                        )
            # post_loe_sgna_fraction is optional (defaults to 0.30 in RevenueModel)
            # but if present it must be in [0, 1]
            if "post_loe_sgna_fraction" in vals:
                v = vals["post_loe_sgna_fraction"]
                if not (0.0 <= v <= 1.0):
                    errors.append(
                        f"loe_erosion_profiles.{profile}.post_loe_sgna_fraction = {v} "
                        f"must be in [0, 1]"
                    )

        # trial_design caps
        td = self._data["trial_design"]
        cap_pos = td.get("cap_logodds_positive")
        cap_neg = td.get("cap_logodds_negative")
        if cap_pos is not None and cap_pos <= 0:
            errors.append(f"trial_design.cap_logodds_positive = {cap_pos} must be > 0")
        if cap_neg is not None and cap_neg >= 0:
            errors.append(f"trial_design.cap_logodds_negative = {cap_neg} must be < 0")

        # phase_scaling: values in (0, 1]
        for phase, dims in td.get("phase_scaling", {}).items():
            for dim, v in dims.items():
                if not (0 < v <= 1.0):
                    errors.append(
                        f"trial_design.phase_scaling.{phase}.{dim} = {v} must be in (0, 1]"
                    )

        if errors:
            self._raise(errors)

    def _raise(self, errors: list[str]) -> None:
        msg = (
            f"industry_assumptions.yaml validation failed ({self._path}):\n"
            + "\n".join(f"  - {e}" for e in errors)
        )
        raise AssumptionsValidationError(msg)

    # ------------------------------------------------------------------
    # Accessors — phase success rates
    # ------------------------------------------------------------------

    @property
    def phase_success_rates(self) -> MappingProxyType:
        """Full table: {therapeutic_area: {phase: probability}}. Read-only."""
        return self._data["phase_success_rates"]

    def phase_success_rates_for(self, therapeutic_area: str) -> MappingProxyType:
        """
        Phase success rates for a specific therapeutic area.

        Falls back to "other" with a UserWarning if the TA is not in the table.
        """
        psr = self._data["phase_success_rates"]
        if therapeutic_area in psr:
            return psr[therapeutic_area]
        warnings.warn(
            f"Therapeutic area {therapeutic_area!r} not found in industry_assumptions.yaml "
            f"phase_success_rates. Falling back to 'other'. "
            f"(assumptions version: {self.version})",
            UserWarning,
            stacklevel=2,
        )
        return psr["other"]

    @property
    def prob_approval_from_phase(self) -> dict[str, dict[str, float]]:
        """
        Cumulative P(approval) from the start of each phase.
        Derived from phase_success_rates; not stored separately in YAML.
        Returns a plain dict (not frozen) since it is computed on demand.
        """
        result: dict[str, dict[str, float]] = {}
        for ta, rates in self.phase_success_rates.items():
            p1 = rates["phase_1"]
            p2 = rates["phase_2"]
            p3 = rates["phase_3"]
            pn = rates["nda_bla"]
            result[ta] = {
                "phase_1": p1 * p2 * p3 * pn,
                "phase_2": p2 * p3 * pn,
                "phase_3": p3 * pn,
                "nda_bla": pn,
            }
        return result

    # ------------------------------------------------------------------
    # Accessors — phase durations and costs
    # ------------------------------------------------------------------

    @property
    def phase_durations_years(self) -> MappingProxyType:
        return self._data["phase_durations_years"]

    @property
    def phase_costs_millions(self) -> MappingProxyType:
        return self._data["phase_costs_millions"]

    # ------------------------------------------------------------------
    # Accessors — commercial defaults
    # ------------------------------------------------------------------

    @property
    def gross_to_net_by_modality(self) -> MappingProxyType:
        return self._data["commercial"]["gross_to_net_by_modality"]

    def gross_to_net(self, modality: str) -> float:
        """G2N rate for a modality. Warns and falls back to 'other' if not found."""
        table = self.gross_to_net_by_modality
        if modality in table:
            return float(table[modality])
        warnings.warn(
            f"Modality {modality!r} not found in gross_to_net_by_modality. "
            f"Falling back to 'other'. (assumptions version: {self.version})",
            UserWarning,
            stacklevel=2,
        )
        return float(table["other"])

    @property
    def cogs_rate_by_modality(self) -> MappingProxyType:
        return self._data["commercial"]["cogs_rate_by_modality"]

    def cogs_rate(self, modality: str) -> float:
        """COGS rate for a modality. Warns and falls back to 'other' if not found."""
        table = self.cogs_rate_by_modality
        if modality in table:
            return float(table[modality])
        warnings.warn(
            f"Modality {modality!r} not found in cogs_rate_by_modality. "
            f"Falling back to 'other'. (assumptions version: {self.version})",
            UserWarning,
            stacklevel=2,
        )
        return float(table["other"])

    @property
    def sgna(self) -> MappingProxyType:
        """Keys: rate_launch, rate_mature, ramp_years. Legacy accessor; see sgna_profile()."""
        return self._data["commercial"]["sgna"]

    @property
    def sgna_profiles(self) -> MappingProxyType:
        """Full table of SG&A profiles keyed by profile name."""
        return self._data["commercial"]["sgna_profiles"]

    def sgna_profile(self, name: str) -> MappingProxyType:
        """
        SG&A ramp profile for a named commercial profile.

        Available profiles: specialty_pharma, rare_disease, gene_cell_therapy,
        primary_care, default.  Falls back to 'default' (= specialty_pharma)
        with a UserWarning if the name is not found.
        """
        profiles = self._data["commercial"]["sgna_profiles"]
        if name in profiles:
            return profiles[name]
        warnings.warn(
            f"SG&A profile {name!r} not found in sgna_profiles. "
            f"Falling back to 'default'. (assumptions version: {self.version})",
            UserWarning,
            stacklevel=2,
        )
        return profiles["default"]

    @property
    def compliance_by_modality(self) -> MappingProxyType:
        """Compliance rate table keyed by modality string."""
        return self._data["commercial"]["compliance_by_modality"]

    def compliance_rate(self, modality: str) -> float:
        """
        Compliance rate for a modality.

        Falls back to 'other' (0.80) with a UserWarning if not found.
        For 'biologic' (generic), returns the biologic_iv rate (conservative default).
        """
        table = self._data["commercial"]["compliance_by_modality"]
        # biologic (generic) → biologic_iv as conservative default
        lookup = "biologic_iv" if modality == "biologic" else modality
        if lookup in table:
            return float(table[lookup])
        warnings.warn(
            f"Modality {modality!r} not found in compliance_by_modality. "
            f"Falling back to 'other'. (assumptions version: {self.version})",
            UserWarning,
            stacklevel=2,
        )
        return float(table["other"])

    @property
    def commercial_defaults(self) -> MappingProxyType:
        """
        Fallback defaults for CLI / config fields not explicitly set.
        Keys: discount_rate, peak_penetration, cogs_rate.
        """
        return self._data["commercial"]["defaults"]

    # ------------------------------------------------------------------
    # Accessors — WACC
    # ------------------------------------------------------------------

    @property
    def wacc(self) -> MappingProxyType:
        """Keys: default, small_cap, large_cap, risk_free."""
        return self._data["wacc"]

    # ------------------------------------------------------------------
    # Accessors — Monte Carlo defaults
    # ------------------------------------------------------------------

    @property
    def mc_phase_ess(self) -> dict[str, int]:
        """Returns a plain dict (int values) for compatibility with Pydantic models."""
        return {k: int(v) for k, v in self._data["monte_carlo"]["phase_ess"].items()}

    @property
    def mc_peak_sales_cv(self) -> float:
        return float(self._data["monte_carlo"]["peak_sales_cv"])

    @property
    def mc_peak_sales_cv_by_stage(self) -> dict[str, float]:
        """Stage-conditional peak_sales_cv table. Falls back to flat cv if absent."""
        table = self._data["monte_carlo"].get("peak_sales_cv_by_stage", {})
        return {k: float(v) for k, v in table.items()}

    @property
    def mc_discount_rate_std(self) -> float:
        return float(self._data["monte_carlo"]["discount_rate_std"])

    @property
    def mc_years_to_peak_std(self) -> float:
        return float(self._data["monte_carlo"]["years_to_peak_std"])

    @property
    def mc_patent_life_std(self) -> float:
        return float(self._data["monte_carlo"]["patent_life_std"])

    # ------------------------------------------------------------------
    # Accessors — LOE erosion profiles
    # ------------------------------------------------------------------

    @property
    def loe_erosion_profiles(self) -> MappingProxyType:
        """Full table: {modality: {year_1_loss, year_2_loss, ...}}. Read-only."""
        return self._data["loe_erosion_profiles"]

    def loe_erosion_profile(self, modality: str) -> MappingProxyType:
        """
        LOE erosion profile for a modality.

        Falls back to 'other' (small_molecule-like behavior) with a UserWarning
        if the modality is not in the table.
        """
        profiles = self.loe_erosion_profiles
        if modality in profiles:
            return profiles[modality]
        fallback = "other" if "other" in profiles else "small_molecule"
        warnings.warn(
            f"Modality {modality!r} not found in loe_erosion_profiles. "
            f"Falling back to {fallback!r}. (assumptions version: {self.version})",
            UserWarning,
            stacklevel=2,
        )
        return profiles[fallback]

    # ------------------------------------------------------------------
    # Accessors — Competition
    # ------------------------------------------------------------------

    @property
    def competition(self) -> MappingProxyType:
        return self._data["competition"]

    # ------------------------------------------------------------------
    # Accessors — Trial design
    # ------------------------------------------------------------------

    @property
    def trial_design_logodds(self) -> MappingProxyType:
        return self._data["trial_design"]["logodds"]

    @property
    def trial_design_cap_positive(self) -> float:
        return float(self._data["trial_design"]["cap_logodds_positive"])

    @property
    def trial_design_cap_negative(self) -> float:
        return float(self._data["trial_design"]["cap_logodds_negative"])

    @property
    def trial_design_phase_scaling(self) -> MappingProxyType:
        return self._data["trial_design"]["phase_scaling"]

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    @property
    def version(self) -> str:
        return str(self._data["meta"]["version"])

    @property
    def sources(self) -> tuple:
        return self._data["meta"].get("sources", ())
