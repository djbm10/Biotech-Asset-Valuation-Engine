"""Auto-generated valuation config builder for watchlist assets."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from bve.config.assumptions_loader import AssumptionsLoader
from bve.pipeline.disk_cache import DiskCache
from bve.pipeline.universe_registry import UniverseRegistryEntry
from bve.services.rate_limiter import ServiceRateLimiter


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AutoConfigGenerator:
    """Build valuation config dictionaries from registry entries and live data."""

    def __init__(self, cache: DiskCache, rate_limiter: ServiceRateLimiter) -> None:
        self.cache = cache
        self.rate_limiter = rate_limiter
        self.assumptions = AssumptionsLoader.get()
        self.generator_version = "0.3"

    @staticmethod
    def _quarter_label(now: datetime) -> str:
        quarter = ((now.month - 1) // 3) + 1
        return f"{now.year}Q{quarter}"

    @staticmethod
    def _normalize_phase(raw_phase: Optional[str], fallback: str) -> str:
        if not raw_phase:
            return fallback
        text = raw_phase.upper().replace(" ", "")
        mapping = {
            "EARLY_PHASE1": "phase_1",
            "PHASE1": "phase_1",
            "PHASE1/PHASE2": "phase_2",
            "PHASE2": "phase_2",
            "PHASE2/PHASE3": "phase_3",
            "PHASE3": "phase_3",
            "PHASE4": "phase_3",
        }
        return mapping.get(text, fallback)

    @staticmethod
    def _normalize_modality(raw_modality: str) -> str:
        text = (raw_modality or "").strip().lower()
        mapping = {
            "small_molecule": "small_molecule",
            "biologic": "biologic",
            "cell_gene": "gene_therapy",
            "cell_therapy": "cell_therapy",
            "gene_therapy": "gene_therapy",
            "rna_therapy": "rna_therapy",
            "adc": "adc",
            "other": "other",
        }
        return mapping.get(text, "other")

    def _fetch_ctgov_by_nct_id(self, nct_id: str) -> dict:
        from bve.ingestion.clinicaltrials_gov import fetch_study

        self.rate_limiter.wait("clinicaltrials_gov")
        protocol = fetch_study(nct_id)
        status_mod = protocol.get("statusModule", {})
        design_mod = protocol.get("designModule", {})
        outcomes_mod = protocol.get("outcomesModule", {})

        phases = design_mod.get("phases") or []
        enrollment_info = design_mod.get("enrollmentInfo") or {}
        primary = outcomes_mod.get("primaryOutcomes") or []

        return {
            "nct_id": nct_id,
            "phase": phases[0] if phases else None,
            "enrollment": enrollment_info.get("count"),
            "primary_endpoint": primary[0].get("measure") if primary else None,
            "estimated_completion_date": (
                status_mod.get("primaryCompletionDateStruct") or {}
            ).get("date"),
        }

    def _fetch_sec_financials(self, ticker: str) -> dict:
        from bve.ingestion.sec_edgar import get_financials_by_ticker

        self.rate_limiter.wait("sec_filing")
        data = get_financials_by_ticker(ticker)
        burn = data.get("rd_expense_millions")
        burn_rate = round(float(burn) / 4.0, 2) if burn is not None else None
        data["burn_rate_millions_per_quarter"] = burn_rate
        return data

    def _fetch_market_snapshot(self, ticker: str) -> dict:
        self.rate_limiter.wait("market")
        try:
            import yfinance as yf

            info = yf.Ticker(ticker).fast_info
            market_cap = getattr(info, "market_cap", None)
            last_price = getattr(info, "last_price", None)
            return {
                "ticker": ticker,
                "market_cap_millions": round(float(market_cap) / 1e6, 2)
                if market_cap is not None
                else None,
                "current_price": round(float(last_price), 4)
                if last_price is not None
                else None,
            }
        except Exception:
            return {
                "ticker": ticker,
                "market_cap_millions": None,
                "current_price": None,
            }

    def _cached_ctgov(self, nct_id: Optional[str]) -> Optional[dict]:
        if not nct_id:
            return None
        cached = self.cache.get("ctgov", nct_id)
        if cached is not None:
            return cached
        try:
            fresh = self._fetch_ctgov_by_nct_id(nct_id)
        except Exception:
            return None
        self.cache.put("ctgov", nct_id, fresh)
        return fresh

    def _cached_sec(self, ticker: str) -> tuple[dict, str]:
        quarter = self._quarter_label(_utcnow())
        key = f"{ticker.upper()}_{quarter}"
        cached = self.cache.get("sec", key)
        if cached is not None:
            return cached, quarter
        try:
            fresh = self._fetch_sec_financials(ticker)
        except Exception:
            return {}, quarter
        self.cache.put("sec", key, fresh)
        return fresh, quarter

    def _cached_market(self, ticker: str) -> dict:
        key = ticker.upper()
        cached = self.cache.get("market", key)
        if cached is not None:
            return cached
        try:
            fresh = self._fetch_market_snapshot(ticker)
        except Exception:
            return {}
        self.cache.put("market", key, fresh)
        return fresh

    @staticmethod
    def _company_id(entry: UniverseRegistryEntry) -> str:
        return f"{entry.ticker.lower()}-auto"

    def generate(self, entry: UniverseRegistryEntry) -> dict:
        """Generate a single valuation YAML payload for one registry entry."""

        defaults_used: list[str] = []

        ctgov = self._cached_ctgov(entry.nct_id)
        sec, sec_quarter = self._cached_sec(entry.ticker)
        market = self._cached_market(entry.ticker)

        stage_value = entry.stage
        if ctgov and ctgov.get("phase"):
            stage_value = self._normalize_phase(str(ctgov.get("phase")), entry.stage)

        trial_phase = stage_value
        pos_rates = self.assumptions.phase_success_rates_for(entry.therapeutic_area)
        success_probability = float(pos_rates.get(trial_phase, pos_rates.get("phase_2", 0.35)))

        if entry.tam_millions is None:
            defaults_used.append("market_model.total_addressable_market_millions")
        if entry.addressable_patients_annual is None:
            defaults_used.append("market_model.addressable_patients_annual")
        if entry.net_price_per_patient_usd is None:
            defaults_used.append("market_model.net_price_per_patient_usd")

        cash = sec.get("cash_millions")
        shares = sec.get("shares_outstanding_millions")
        burn_rate = sec.get("burn_rate_millions_per_quarter")
        current_price = market.get("current_price")

        if cash is None:
            defaults_used.append("company.cash_millions")
            cash = 250.0
        if shares is None:
            defaults_used.append("company.shares_outstanding_millions")
            shares = 100.0
        if burn_rate is None:
            defaults_used.append("company.burn_rate_millions_per_quarter")
            burn_rate = 35.0

        trial = {
            "phase": trial_phase,
            "nct_id": entry.nct_id,
            "success_probability": success_probability,
            "duration_years": 2.5,
            "cost_millions": 120.0,
            "enrollment": ctgov.get("enrollment") if ctgov else None,
            "primary_endpoint": ctgov.get("primary_endpoint") if ctgov else None,
            "endpoint_type": "surrogate_validated",
            "estimated_completion_date": ctgov.get("estimated_completion_date") if ctgov else None,
        }

        if trial["enrollment"] is None:
            defaults_used.append("trials[0].enrollment")
        if trial["primary_endpoint"] is None:
            defaults_used.append("trials[0].primary_endpoint")

        generated_at = _utcnow().date().isoformat()
        return {
            "asset": {
                "id": entry.asset_id,
                "name": entry.drug_name,
                "indication": entry.indication,
                "therapeutic_area": entry.therapeutic_area,
                "stage": stage_value,
                "modality": self._normalize_modality(entry.modality),
                "discount_rate": entry.discount_rate or 0.10,
            },
            "company": {
                "id": self._company_id(entry),
                "name": entry.company_name,
                "ticker": entry.ticker,
                "cash_millions": float(cash),
                "shares_outstanding_millions": float(shares),
                "burn_rate_millions_per_quarter": float(burn_rate),
                "current_price": float(current_price) if current_price is not None else None,
            },
            "trials": [trial],
            "market_model": {
                "total_addressable_market_millions": entry.tam_millions,
                "addressable_patients_annual": entry.addressable_patients_annual,
                "net_price_per_patient_usd": entry.net_price_per_patient_usd,
                "peak_penetration": entry.peak_penetration or 0.1,
                "years_to_peak": 5,
                "patent_life_years": entry.patent_life_years or 10,
                "cogs_rate": 0.15,
                "sgna_rate_launch": 0.4,
                "sgna_rate_mature": 0.2,
            },
            "_meta": {
                "config_version": "auto-v1",
                "generator_version": self.generator_version,
                "generated_at": generated_at,
                "source_nct_id": entry.nct_id,
                "source_sec_filing": f"auto:{sec_quarter}",
                "defaulted_fields": defaults_used,
            },
        }

    def generate_batch(
        self,
        entries: list[UniverseRegistryEntry],
    ) -> list[tuple[UniverseRegistryEntry, dict, Optional[str]]]:
        """Batch-generate configs without aborting on per-entry failures."""

        out: list[tuple[UniverseRegistryEntry, dict, Optional[str]]] = []
        for entry in entries:
            try:
                out.append((entry, self.generate(entry), None))
            except Exception as exc:  # pragma: no cover - defensive
                out.append((entry, {}, str(exc)))
        return out
