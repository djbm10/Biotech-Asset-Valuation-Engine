"""Build a canonical :class:`CompanyProfile` from public sources + heuristic priors.

``ProfileBuilder`` takes injectable fetchers so it is fully testable offline; the
defaults wire to the existing ingestion functions
(``sec_edgar.get_financials_by_ticker``, ``clinicaltrials_gov.fetch_study``,
``refresh.market_data_refresh.fetch_market_snapshot``).

Provenance policy
-----------------
- Curated seed identity (drug, indication, TA, stage, modality) → ``confidence=high``.
- Trial facts pulled from CT.gov → ``confidence=high`` when present.
- Company financials from SEC / market data → ``confidence=high`` when present.
- PoS derived from industry base rates → ``confidence=medium``.
- Commercial economics filled from heuristic priors → ``confidence=low`` (these are
  the fields the analyst is expected to override). Seed-provided economics override
  the prior at ``confidence=medium``.

The auto-built profile is always ``evidence_level="coarse"`` until an analyst
confirms the value drivers (handled downstream by the override merge).
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from bve.pipeline.asset_profile import AssetProfile, CompanyProfile, ProvenancedField, pf
from bve.pipeline.universe_registry import UniverseRegistryEntry

# Normalized fetcher signatures (all return plain dicts, all may be empty):
SecFetcher = Callable[[str], dict[str, Any]]      # (ticker) -> financials
CtgovFetcher = Callable[[str], dict[str, Any]]    # (nct_id) -> trial facts
MarketFetcher = Callable[[str], dict[str, Any]]   # (ticker) -> market snapshot


# ---------------------------------------------------------------------------
# Heuristic economics priors (LOW confidence — the analyst-override targets)
# ---------------------------------------------------------------------------
# Keyed by therapeutic_area; ``other`` is the fallback. Deliberately coarse —
# these exist only to let the engine produce a directional rNPV before review.
# Extending this into industry_assumptions.yaml is deferred (see plan / future_fixes).

_PRIOR_FIELDS = (
    "total_addressable_market_millions",
    "net_price_per_patient_usd",
    "addressable_patients_annual",
    "peak_penetration",
    "patent_life_years",
)

ECONOMICS_PRIORS: dict[str, dict[str, float]] = {
    "oncology": {
        "total_addressable_market_millions": 6000.0,
        "net_price_per_patient_usd": 180000.0,
        "addressable_patients_annual": 20000,
        "peak_penetration": 0.15,
        "patent_life_years": 11,
    },
    "rare_disease": {
        "total_addressable_market_millions": 3000.0,
        "net_price_per_patient_usd": 350000.0,
        "addressable_patients_annual": 6000,
        "peak_penetration": 0.30,
        "patent_life_years": 12,
    },
    "hematology": {
        "total_addressable_market_millions": 4000.0,
        "net_price_per_patient_usd": 400000.0,
        "addressable_patients_annual": 8000,
        "peak_penetration": 0.20,
        "patent_life_years": 12,
    },
    "cardiovascular": {
        "total_addressable_market_millions": 8000.0,
        "net_price_per_patient_usd": 90000.0,
        "addressable_patients_annual": 40000,
        "peak_penetration": 0.20,
        "patent_life_years": 11,
    },
    "cns": {
        "total_addressable_market_millions": 7000.0,
        "net_price_per_patient_usd": 120000.0,
        "addressable_patients_annual": 30000,
        "peak_penetration": 0.18,
        "patent_life_years": 11,
    },
    "immunology": {
        "total_addressable_market_millions": 9000.0,
        "net_price_per_patient_usd": 60000.0,
        "addressable_patients_annual": 50000,
        "peak_penetration": 0.18,
        "patent_life_years": 11,
    },
    "other": {
        "total_addressable_market_millions": 5000.0,
        "net_price_per_patient_usd": 100000.0,
        "addressable_patients_annual": 25000,
        "peak_penetration": 0.15,
        "patent_life_years": 10,
    },
}

# Structural defaults (LOW confidence) for fields no public source provides cheaply.
_DEFAULTS = {
    "duration_years": 2.5,
    "cost_millions": 120.0,
    "endpoint_type": "surrogate_validated",
    "years_to_peak": 5,
    "cogs_rate": 0.15,
    "sgna_rate_launch": 0.40,
    "sgna_rate_mature": 0.20,
    "discount_rate": 0.10,
}

_PHASE_MAP = {
    "EARLY_PHASE1": "phase_1",
    "PHASE1": "phase_1",
    "PHASE1/PHASE2": "phase_2",
    "PHASE2": "phase_2",
    "PHASE2/PHASE3": "phase_3",
    "PHASE3": "phase_3",
    "PHASE4": "phase_3",
}

_MODALITY_MAP = {
    "small_molecule": "small_molecule",
    "biologic": "biologic",
    "cell_gene": "gene_therapy",
    "cell_therapy": "cell_therapy",
    "gene_therapy": "gene_therapy",
    "rna_therapy": "rna_therapy",
    "adc": "adc",
}


def economics_prior(therapeutic_area: str) -> dict[str, float]:
    """Return the heuristic economics prior for a therapeutic area (``other`` fallback)."""
    return ECONOMICS_PRIORS.get((therapeutic_area or "").strip().lower(), ECONOMICS_PRIORS["other"])


def _normalize_phase(raw: Optional[str], fallback: str) -> str:
    if not raw:
        return fallback
    return _PHASE_MAP.get(raw.upper().replace(" ", ""), fallback)


def _normalize_modality(raw: str) -> str:
    return _MODALITY_MAP.get((raw or "").strip().lower(), "other")


# ---------------------------------------------------------------------------
# Default (live) fetchers — lazily imported so tests never touch the network
# ---------------------------------------------------------------------------


def _default_sec_fetcher(ticker: str) -> dict[str, Any]:
    from bve.ingestion.sec_edgar import get_financials_by_ticker

    return dict(get_financials_by_ticker(ticker) or {})


def _default_ctgov_fetcher(nct_id: str) -> dict[str, Any]:
    from bve.ingestion.clinicaltrials_gov import fetch_study

    protocol = fetch_study(nct_id) or {}
    status_mod = protocol.get("statusModule", {})
    design_mod = protocol.get("designModule", {})
    outcomes_mod = protocol.get("outcomesModule", {})
    phases = design_mod.get("phases") or []
    enrollment_info = design_mod.get("enrollmentInfo") or {}
    primary = outcomes_mod.get("primaryOutcomes") or []
    return {
        "phase": phases[0] if phases else None,
        "enrollment": enrollment_info.get("count"),
        "primary_endpoint": primary[0].get("measure") if primary else None,
        "estimated_completion_date": (
            status_mod.get("primaryCompletionDateStruct") or {}
        ).get("date"),
    }


def _default_market_fetcher(ticker: str) -> dict[str, Any]:
    from bve.refresh.market_data_refresh import fetch_market_snapshot

    snap = fetch_market_snapshot(ticker)
    raw = getattr(snap, "raw", {}) or {}
    return {
        "current_price": snap.price,
        "market_cap_millions": snap.market_cap_millions,
        "shares_outstanding_millions": snap.shares_outstanding_millions,
        "cash_millions": raw.get("cash_millions"),
        "total_debt_millions": raw.get("total_debt_millions"),
    }


# ---------------------------------------------------------------------------
# ProfileBuilder
# ---------------------------------------------------------------------------


class ProfileBuilder:
    """Assemble a :class:`CompanyProfile` from a curated identity seed + public data."""

    def __init__(
        self,
        *,
        sec_fetcher: Optional[SecFetcher] = None,
        ctgov_fetcher: Optional[CtgovFetcher] = None,
        market_fetcher: Optional[MarketFetcher] = None,
    ) -> None:
        self._sec_fetcher = sec_fetcher or _default_sec_fetcher
        self._ctgov_fetcher = ctgov_fetcher or _default_ctgov_fetcher
        self._market_fetcher = market_fetcher or _default_market_fetcher

    # -- safe fetch wrappers (a failing source must never abort the build) --

    @staticmethod
    def _safe(fn: Callable[[str], dict], key: Optional[str]) -> dict[str, Any]:
        if not key:
            return {}
        try:
            return dict(fn(key) or {})
        except Exception:
            return {}

    def _pos_for(self, therapeutic_area: str, phase: str) -> Optional[float]:
        """Cumulative probability of approval from the current phase.

        A generated config carries only the single lead trial, so the engine
        treats its ``success_probability`` as the whole P(approval). It must
        therefore be the *cumulative* probability of approval from the current
        phase to launch — NOT the next-phase transition rate. Using the
        per-phase transition rate (``phase_success_rates_for``) would make a
        Phase 1 asset look like it has ~67% approval odds; the cumulative table
        (``prob_approval_from_phase``) already compounds the remaining ladder.
        """
        try:
            from bve.config.assumptions_loader import AssumptionsLoader

            table = AssumptionsLoader.get().prob_approval_from_phase
            ta = (therapeutic_area or "").strip().lower()
            by_phase = table.get(ta) or table.get("all") or {}
            value = by_phase.get(phase, by_phase.get("phase_2"))
            return float(value) if value is not None else None
        except Exception:
            return None

    def build(self, seed: UniverseRegistryEntry) -> CompanyProfile:
        sec = self._safe(self._sec_fetcher, seed.ticker)
        market = self._safe(self._market_fetcher, seed.ticker)
        ctgov = self._safe(self._ctgov_fetcher, seed.nct_id)

        prior = economics_prior(seed.therapeutic_area)

        # Normalize quarterly burn from R&D when the source doesn't provide it.
        burn = sec.get("burn_rate_millions_per_quarter")
        if burn is None and sec.get("rd_expense_millions") is not None:
            burn = round(float(sec["rd_expense_millions"]) / 4.0, 2)

        # ── stage (refine from CT.gov phase when available) ──────────────
        stage_value = _normalize_phase(ctgov.get("phase"), seed.stage)
        stage_source = "clinicaltrials_gov" if ctgov.get("phase") else "seed"

        pos = self._pos_for(seed.therapeutic_area, stage_value)

        asset = AssetProfile(
            asset_id=seed.asset_id,
            nct_id=seed.nct_id,
            drug_name=pf(seed.drug_name, "seed", confidence="high"),
            indication=pf(seed.indication, "seed", confidence="high"),
            therapeutic_area=pf(seed.therapeutic_area, "seed", confidence="high"),
            stage=pf(stage_value, stage_source, confidence="high"),
            modality=pf(_normalize_modality(seed.modality), "seed", confidence="high"),
            discount_rate=self._econ_field(seed.discount_rate, _DEFAULTS["discount_rate"], "seed"),
            # trial facts
            success_probability=(
                pf(pos, "industry_assumptions", confidence="medium")
                if pos is not None
                else pf(None, "unset", confidence="low")
            ),
            duration_years=pf(_DEFAULTS["duration_years"], "default", confidence="low"),
            cost_millions=pf(_DEFAULTS["cost_millions"], "default", confidence="low"),
            enrollment=self._public_field(ctgov.get("enrollment"), "clinicaltrials_gov"),
            primary_endpoint=self._public_field(
                ctgov.get("primary_endpoint"), "clinicaltrials_gov"
            ),
            endpoint_type=pf(_DEFAULTS["endpoint_type"], "default", confidence="low"),
            estimated_completion_date=self._public_field(
                ctgov.get("estimated_completion_date"), "clinicaltrials_gov"
            ),
            # economics (seed > prior; prior is low-confidence)
            total_addressable_market_millions=self._econ_field(
                seed.tam_millions, prior["total_addressable_market_millions"], "seed"
            ),
            net_price_per_patient_usd=self._econ_field(
                seed.net_price_per_patient_usd, prior["net_price_per_patient_usd"], "seed"
            ),
            addressable_patients_annual=self._econ_field(
                seed.addressable_patients_annual, prior["addressable_patients_annual"], "seed"
            ),
            peak_penetration=self._econ_field(
                seed.peak_penetration, prior["peak_penetration"], "seed"
            ),
            patent_life_years=self._econ_field(
                seed.patent_life_years, prior["patent_life_years"], "seed"
            ),
            years_to_peak=pf(_DEFAULTS["years_to_peak"], "default", confidence="low"),
            cogs_rate=pf(_DEFAULTS["cogs_rate"], "default", confidence="low"),
            sgna_rate_launch=pf(_DEFAULTS["sgna_rate_launch"], "default", confidence="low"),
            sgna_rate_mature=pf(_DEFAULTS["sgna_rate_mature"], "default", confidence="low"),
        )

        return CompanyProfile(
            ticker=seed.ticker,
            name=seed.company_name,
            company_id=f"{seed.ticker.lower()}-auto",
            cash_millions=self._public_field(market.get("cash_millions") or sec.get("cash_millions"), "sec_edgar"),
            shares_outstanding_millions=self._public_field(
                sec.get("shares_outstanding_millions") or market.get("shares_outstanding_millions"),
                "sec_edgar",
            ),
            debt_millions=self._public_field(
                market.get("total_debt_millions") or sec.get("long_term_debt_millions"), "sec_edgar"
            ),
            burn_rate_millions_per_quarter=self._public_field(burn, "sec_edgar"),
            current_price=self._public_field(market.get("current_price"), "market_data"),
            market_cap_millions=self._public_field(market.get("market_cap_millions"), "market_data"),
            assets=[asset],
            evidence_level="coarse",
            source="auto_profile",
        )

    # -- field constructors -------------------------------------------------

    @staticmethod
    def _public_field(value: Any, source: str) -> ProvenancedField:
        """A field sourced from a public feed: high confidence if present, else low/unset."""
        if value is None:
            return pf(None, "unset", confidence="low")
        return pf(value, source, confidence="high")

    @staticmethod
    def _econ_field(seed_value: Any, prior_value: Any, seed_source: str) -> ProvenancedField:
        """Economics field: seed value (medium) wins; else heuristic prior (low)."""
        if seed_value is not None:
            return pf(seed_value, seed_source, confidence="medium")
        return pf(prior_value, "heuristic_prior", confidence="low")
