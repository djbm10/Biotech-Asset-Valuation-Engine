"""
Profile enricher — Block 2B.

Builds TargetProfileEnriched and AcquirerProfileEnriched from the three-layer
priority chain:

    manual_overrides.yaml  >  universe YAML  >  SEC EDGAR  >  null

Financial enrichment uses SEC EDGAR XBRL facts (get_financials_by_ticker).
Acquirer dynamic signals (bd_appetite, urgency, integration_capacity) come
from the evidence ledger's compute_score_state().

Usage::

    enricher = ProfileEnricher(targets, acquirers, overrides)
    target_profiles = enricher.enrich_targets()
    acquirer_profiles = enricher.enrich_acquirers()
    write_profiles(target_profiles, acquirer_profiles, Path("outputs/profiles"))
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from bve.ingestion.universe_loader import AcquirerEntry, TargetEntry


# ---------------------------------------------------------------------------
# Enriched profile dataclasses
# ---------------------------------------------------------------------------


@dataclass
class TargetProfileEnriched:
    """Fully-enriched target profile ready for scoring."""

    # Core identity (from YAML / overrides)
    ticker: str
    name: str
    cik: Optional[str]
    exchange: str
    company_type: str
    therapeutic_areas: list[str]
    lead_asset: str
    lead_asset_phase: str
    lead_modality: str
    lead_indication: str
    is_single_asset_company: bool
    include_in_screen: bool
    market_cap_bucket: Optional[str]
    has_partner_encumbrance: Optional[bool]

    # Financial signals (from SEC EDGAR)
    cash_millions: Optional[float]
    rd_expense_ttm_millions: Optional[float]
    sgna_expense_ttm_millions: Optional[float]
    operating_burn_ttm_millions: Optional[float]
    shares_outstanding_millions: Optional[float]
    cash_runway_months: Optional[float]

    # Quality metadata
    quality_score: float                    # 0.0–1.0
    data_quality_flags: list[str]           # "cash_missing", "runway_estimated_from_rd_only", ...
    source_map: dict[str, str]              # field → "manual_override"|"yaml"|"sec"|"null"
    enriched_at: str                        # ISO timestamp


@dataclass
class AcquirerProfileEnriched:
    """Fully-enriched acquirer profile ready for pair scoring."""

    # Core identity (from YAML / overrides)
    ticker: str
    name: str
    cik: Optional[str]
    therapeutic_areas: list[str]
    modalities: list[str]
    deal_size_range_millions: tuple[float, float]
    preferred_stages: list[str]
    include_as_acquirer: bool

    # Dynamic signals from evidence ledger (default = neutral priors)
    bd_appetite: float              # 0.0–1.0; from acquirer_appetite score
    urgency: float                  # 0.0–1.0; from acquirer_urgency score
    integration_capacity: float     # 0.0–1.0; from integration_capacity score

    # Quality metadata
    quality_score: float
    data_quality_flags: list[str]
    source_map: dict[str, str]
    enriched_at: str


# ---------------------------------------------------------------------------
# Quality scoring helpers
# ---------------------------------------------------------------------------

_TARGET_FIELD_WEIGHTS: dict[str, float] = {
    "lead_asset":       0.15,
    "lead_asset_phase": 0.15,
    "lead_modality":    0.10,
    "cash_millions":    0.20,
    "therapeutic_areas": 0.10,
    "lead_indication":  0.10,
}

_FLAG_PENALTIES: dict[str, float] = {
    "cash_missing":                 0.15,
    "rd_expense_missing":           0.05,
    "runway_estimated_from_rd_only": 0.00,   # informational, no penalty
    "lead_asset_missing":           0.15,
    "phase_missing_or_unknown":     0.10,
    "no_evidence_coverage":         0.10,
    "manual_override_used":         0.00,    # informational, no penalty
}


def _compute_target_quality(profile: TargetProfileEnriched) -> float:
    """
    Compute quality score ∈ [0.0, 1.0] based on data completeness.

    Penalises missing or low-quality fields using additive deductions.
    """
    score = 1.0
    for flag in profile.data_quality_flags:
        score -= _FLAG_PENALTIES.get(flag, 0.0)
    return max(0.0, min(1.0, score))


def _compute_acquirer_quality(profile: AcquirerProfileEnriched) -> float:
    score = 1.0
    for flag in profile.data_quality_flags:
        score -= _FLAG_PENALTIES.get(flag, 0.0)
    return max(0.0, min(1.0, score))


# ---------------------------------------------------------------------------
# ProfileEnricher
# ---------------------------------------------------------------------------


class ProfileEnricher:
    """
    Enriches TargetEntry / AcquirerEntry objects with financial and dynamic signals.

    Parameters
    ----------
    targets:
        Loaded targets dict from universe_loader.load_targets().
    acquirers:
        Loaded acquirers dict from universe_loader.load_acquirers().
    manual_overrides:
        Loaded overrides dict from universe_loader.load_manual_overrides().
    sec_fetcher:
        Callable(ticker) → dict with keys: cash_millions, rd_expense_millions,
        sgna_expense_millions, shares_outstanding_millions.
        Defaults to sec_edgar.get_financials_by_ticker.
        Pass a mock for tests.
    ledger_score_fetcher:
        Callable(ticker) → dict[str, float] of evidence-driven scores.
        Defaults to EvidenceLedger().compute_score_state. Pass a mock for tests.
    """

    def __init__(
        self,
        targets: dict[str, TargetEntry],
        acquirers: dict[str, AcquirerEntry],
        manual_overrides: dict[str, dict],
        *,
        sec_fetcher: Optional[Callable[[str], dict[str, Any]]] = None,
        ledger_score_fetcher: Optional[Callable[[str], dict[str, float]]] = None,
    ) -> None:
        self._targets = targets
        self._acquirers = acquirers
        self._overrides = manual_overrides

        if sec_fetcher is None:
            from bve.ingestion.sec_edgar import get_financials_by_ticker
            self._sec_fetcher = get_financials_by_ticker
        else:
            self._sec_fetcher = sec_fetcher

        if ledger_score_fetcher is None:
            from bve.ingestion.evidence_ledger import EvidenceLedger
            _ledger = EvidenceLedger()
            self._ledger_score_fetcher: Callable[[str], dict[str, float]] = (
                _ledger.compute_score_state
            )
        else:
            self._ledger_score_fetcher = ledger_score_fetcher

    # ── Priority-chain field resolver ──────────────────────────────────────

    def _resolve(
        self,
        ticker: str,
        field_name: str,
        yaml_value: Any,
        external_value: Any = None,
    ) -> tuple[Any, str]:
        """
        Return (value, source) using the priority chain:
        manual_override > yaml > external > null.
        """
        override = self._overrides.get(ticker, {})
        if field_name in override and override[field_name] is not None:
            return override[field_name], "manual_override"
        if yaml_value is not None and yaml_value != "" and yaml_value != []:
            return yaml_value, "yaml"
        if external_value is not None:
            return external_value, "sec"
        return None, "null"

    # ── Target enrichment ─────────────────────────────────────────────────

    def enrich_target(self, ticker: str) -> TargetProfileEnriched:
        """Enrich a single target."""
        t = self._targets[ticker]
        now = datetime.now(timezone.utc).isoformat()

        # Fetch SEC financials (may fail — return empty dict on error)
        try:
            sec = self._sec_fetcher(ticker) or {}
        except Exception:
            sec = {}

        cash_raw = sec.get("cash_millions")
        rd_raw = sec.get("rd_expense_millions")
        sgna_raw = sec.get("sgna_expense_millions")
        shares_raw = sec.get("shares_outstanding_millions")

        # Resolve core fields through priority chain
        source_map: dict[str, str] = {}
        flags: list[str] = []

        def resolve(fname: str, yaml_val: Any, ext_val: Any = None) -> Any:
            val, src = self._resolve(ticker, fname, yaml_val, ext_val)
            source_map[fname] = src
            return val

        lead_asset      = resolve("lead_asset",      t.lead_asset)
        lead_phase      = resolve("lead_asset_phase", t.lead_asset_phase)
        lead_modality   = resolve("lead_modality",    t.lead_modality)
        lead_indication = resolve("lead_indication",  t.lead_indication)
        company_type    = resolve("company_type",     t.company_type)
        tas             = resolve("therapeutic_areas", t.therapeutic_areas)
        is_single       = resolve("is_single_asset_company", t.is_single_asset_company)
        has_encumbrance = resolve("has_partner_encumbrance", t.has_partner_encumbrance)

        # Financial fields (SEC only — no override path needed)
        source_map["cash_millions"] = "sec" if cash_raw is not None else "null"
        source_map["rd_expense_ttm_millions"] = "sec" if rd_raw is not None else "null"
        source_map["sgna_expense_ttm_millions"] = "sec" if sgna_raw is not None else "null"
        source_map["shares_outstanding_millions"] = "sec" if shares_raw is not None else "null"

        # Compute runway
        cash_runway: Optional[float] = None
        operating_burn: Optional[float] = None
        if rd_raw is not None and sgna_raw is not None:
            operating_burn = rd_raw + sgna_raw
            source_map["operating_burn_ttm_millions"] = "sec"
        elif rd_raw is not None:
            operating_burn = rd_raw
            source_map["operating_burn_ttm_millions"] = "sec_rd_only"
        else:
            source_map["operating_burn_ttm_millions"] = "null"

        if cash_raw is not None and operating_burn is not None and operating_burn > 0:
            monthly_burn = operating_burn / 12.0
            cash_runway = round(cash_raw / monthly_burn, 1)
            if sgna_raw is None:
                flags.append("runway_estimated_from_rd_only")
            source_map["cash_runway_months"] = "sec"
        else:
            source_map["cash_runway_months"] = "null"

        # Build flags
        if cash_raw is None:
            flags.append("cash_missing")
        if rd_raw is None:
            flags.append("rd_expense_missing")
        if rd_raw is not None and sgna_raw is None:
            flags.append("sgna_expense_missing")
        if not lead_asset:
            flags.append("lead_asset_missing")
        if not lead_phase or lead_phase == "unknown":
            flags.append("phase_missing_or_unknown")
        if self._overrides.get(ticker):
            flags.append("manual_override_used")

        profile = TargetProfileEnriched(
            ticker=ticker,
            name=t.name,
            cik=t.cik,
            exchange=t.exchange,
            company_type=company_type or t.company_type,
            therapeutic_areas=list(tas or t.therapeutic_areas),
            lead_asset=lead_asset or "",
            lead_asset_phase=lead_phase or "",
            lead_modality=lead_modality or "",
            lead_indication=lead_indication or "",
            is_single_asset_company=bool(is_single),
            include_in_screen=t.include_in_screen,
            market_cap_bucket=t.market_cap_bucket,
            has_partner_encumbrance=has_encumbrance,
            cash_millions=cash_raw,
            rd_expense_ttm_millions=rd_raw,
            sgna_expense_ttm_millions=sgna_raw,
            operating_burn_ttm_millions=operating_burn,
            shares_outstanding_millions=shares_raw,
            cash_runway_months=cash_runway,
            quality_score=0.0,   # computed below
            data_quality_flags=flags,
            source_map=source_map,
            enriched_at=now,
        )
        profile.quality_score = _compute_target_quality(profile)
        return profile

    def enrich_targets(self) -> dict[str, TargetProfileEnriched]:
        """Enrich all targets. Returns dict[ticker → TargetProfileEnriched]."""
        return {ticker: self.enrich_target(ticker) for ticker in self._targets}

    # ── Acquirer enrichment ───────────────────────────────────────────────

    def enrich_acquirer(self, ticker: str) -> AcquirerProfileEnriched:
        """Enrich a single acquirer."""
        a = self._acquirers[ticker]
        now = datetime.now(timezone.utc).isoformat()

        # Evidence ledger dynamic signals
        try:
            ledger_scores = self._ledger_score_fetcher(ticker) or {}
        except Exception:
            ledger_scores = {}

        bd_appetite = ledger_scores.get("acquirer_appetite", 0.50)
        urgency = ledger_scores.get("acquirer_urgency", 0.30)
        integration_capacity = ledger_scores.get("integration_capacity", 0.70)

        source_map: dict[str, str] = {}
        flags: list[str] = []

        # Resolve override fields
        def resolve(fname: str, yaml_val: Any) -> Any:
            val, src = self._resolve(ticker, fname, yaml_val)
            source_map[fname] = src
            return val

        tas = resolve("therapeutic_areas", a.therapeutic_areas)

        # Dynamic signals source
        has_ledger_data = bool(ledger_scores)
        source_map["bd_appetite"] = "ledger" if has_ledger_data else "prior"
        source_map["urgency"] = "ledger" if has_ledger_data else "prior"
        source_map["integration_capacity"] = "ledger" if has_ledger_data else "prior"

        if not has_ledger_data:
            flags.append("no_evidence_coverage")
        if self._overrides.get(ticker):
            flags.append("manual_override_used")

        profile = AcquirerProfileEnriched(
            ticker=ticker,
            name=a.name,
            cik=a.cik,
            therapeutic_areas=list(tas or a.therapeutic_areas),
            modalities=list(a.modalities),
            deal_size_range_millions=a.deal_size_range_millions,
            preferred_stages=list(a.preferred_stages),
            include_as_acquirer=a.include_as_acquirer,
            bd_appetite=float(bd_appetite),
            urgency=float(urgency),
            integration_capacity=float(integration_capacity),
            quality_score=0.0,
            data_quality_flags=flags,
            source_map=source_map,
            enriched_at=now,
        )
        profile.quality_score = _compute_acquirer_quality(profile)
        return profile

    def enrich_acquirers(self) -> dict[str, AcquirerProfileEnriched]:
        """Enrich all acquirers. Returns dict[ticker → AcquirerProfileEnriched]."""
        return {ticker: self.enrich_acquirer(ticker) for ticker in self._acquirers}


# ---------------------------------------------------------------------------
# Output writer
# ---------------------------------------------------------------------------


def _profile_to_dict(p: Any) -> dict[str, Any]:
    """Convert a profile dataclass to a JSON-serialisable dict."""
    d = asdict(p) if hasattr(p, "__dataclass_fields__") else dict(vars(p))
    # Convert tuple fields to list for JSON
    if "deal_size_range_millions" in d and isinstance(d["deal_size_range_millions"], (tuple, list)):
        d["deal_size_range_millions"] = list(d["deal_size_range_millions"])
    return d


def write_profiles(
    target_profiles: dict[str, TargetProfileEnriched],
    acquirer_profiles: dict[str, AcquirerProfileEnriched],
    output_dir: Path,
) -> None:
    """
    Write profiles and quality report to output_dir.

    Produces three files:
      - target_profiles.json
      - acquirer_profiles.json
      - profile_quality_report.json
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # target_profiles.json
    t_data = {ticker: _profile_to_dict(p) for ticker, p in target_profiles.items()}
    (output_dir / "target_profiles.json").write_text(
        json.dumps(t_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # acquirer_profiles.json
    a_data = {ticker: _profile_to_dict(p) for ticker, p in acquirer_profiles.items()}
    (output_dir / "acquirer_profiles.json").write_text(
        json.dumps(a_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # profile_quality_report.json
    t_scores = {
        ticker: {
            "quality_score": p.quality_score,
            "flags": p.data_quality_flags,
            "include_in_screen": p.include_in_screen,
        }
        for ticker, p in target_profiles.items()
    }
    a_scores = {
        ticker: {
            "quality_score": p.quality_score,
            "flags": p.data_quality_flags,
            "include_as_acquirer": p.include_as_acquirer,
        }
        for ticker, p in acquirer_profiles.items()
    }

    included_targets = [p for p in target_profiles.values() if p.include_in_screen]
    high_quality = sum(1 for p in included_targets if p.quality_score >= 0.70)

    report = {
        "summary": {
            "target_count": len(target_profiles),
            "targets_included": len(included_targets),
            "targets_high_quality": high_quality,
            "targets_high_quality_pct": (
                round(high_quality / len(included_targets), 3) if included_targets else 0.0
            ),
            "acquirer_count": len(acquirer_profiles),
        },
        "targets": t_scores,
        "acquirers": a_scores,
    }
    (output_dir / "profile_quality_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
