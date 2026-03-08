"""
CLI entry point: run a full valuation for a single asset defined in a YAML config file.

Usage
-----
    bve-asset --config examples/configs/relay_rly2608.yaml --memo bd --charts
    bve-asset --config examples/configs/xyz101.yaml --memo hf --charts --all-memos
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from bve.config.assumptions_loader import AssumptionsLoader as _AssumptionsLoader

# Resolved once at import — avoids re-loading YAML on every CLI invocation
_COMMERCIAL_DEFAULTS = _AssumptionsLoader.get().commercial_defaults
_MC_DEFAULTS = _AssumptionsLoader.get()


_VALID_THERAPEUTIC_AREAS = {"oncology", "rare_disease", "cns", "cardiovascular", "immunology", "infectious_disease", "ophthalmology", "other"}
_VALID_STAGES = {"phase_1", "phase_2", "phase_3", "nda_bla"}
_VALID_MODALITIES = {"small_molecule", "biologic", "cell_gene", "adc", "other"}
_VALID_ENDPOINT_TYPES = {"hard_clinical", "surrogate_validated", "surrogate_novel", "biomarker_only"}
_VALID_MOA_PRECEDENT = {"validated", "partial", "novel"}
_VALID_SAMPLE_ADEQUACY = {"well_powered", "adequate", "borderline", "underpowered"}
_VALID_SAFETY = {"clean", "minor", "concerning", "serious"}
_VALID_COMPETITION = {"low", "moderate", "high"}
_VALID_ENDPOINT_BASIS = {"hard_clinical", "surrogate_validated", "surrogate_novel", "biomarker_only"}
_VALID_EVIDENCE_DESIGN = {"rct_comparative", "rct_non_comparative", "single_arm", "registry_based"}
_VALID_APPROVAL_PATHWAY = {"standard", "accelerated_approval", "breakthrough_designation", "orphan_drug"}


def _validate_config(cfg: dict, path: Path) -> None:
    """
    Validate required fields and enum values in a YAML config.
    Raises SystemExit with a clear message on the first error found.
    """
    errors = []

    def _check(condition: bool, msg: str) -> None:
        if not condition:
            errors.append(msg)

    a = cfg.get("asset", {})
    _check(bool(a.get("id")), "asset.id is required")
    _check(bool(a.get("name")), "asset.name is required")
    _check(bool(a.get("indication")), "asset.indication is required")
    _check(
        a.get("therapeutic_area") in _VALID_THERAPEUTIC_AREAS,
        f"asset.therapeutic_area must be one of {sorted(_VALID_THERAPEUTIC_AREAS)}, got: {a.get('therapeutic_area')!r}"
    )
    _check(
        a.get("stage") in _VALID_STAGES,
        f"asset.stage must be one of {sorted(_VALID_STAGES)}, got: {a.get('stage')!r}"
    )
    if a.get("modality"):
        _check(
            a["modality"] in _VALID_MODALITIES,
            f"asset.modality must be one of {sorted(_VALID_MODALITIES)}, got: {a['modality']!r}"
        )

    c = cfg.get("company", {})
    _check(bool(c.get("id")), "company.id is required")
    _check(bool(c.get("name")), "company.name is required")
    _check(c.get("cash_millions") is not None, "company.cash_millions is required")
    _check(c.get("shares_outstanding_millions") is not None, "company.shares_outstanding_millions is required")
    if c.get("shares_outstanding_millions") is not None:
        _check(float(c["shares_outstanding_millions"]) > 0, "company.shares_outstanding_millions must be > 0")

    trials = cfg.get("trials", [])
    _check(len(trials) > 0, "at least one trial is required under 'trials:'")
    for i, t in enumerate(trials):
        prefix = f"trials[{i}]"
        _check(t.get("phase") in _VALID_STAGES, f"{prefix}.phase must be one of {sorted(_VALID_STAGES)}, got: {t.get('phase')!r}")
        _check(t.get("duration_years") is not None, f"{prefix}.duration_years is required")
        _check(t.get("cost_millions") is not None, f"{prefix}.cost_millions is required")
        _check(t.get("success_probability") is not None, f"{prefix}.success_probability is required")
        sp = t.get("success_probability")
        if sp is not None:
            _check(0 < float(sp) < 1, f"{prefix}.success_probability must be between 0 and 1, got: {sp}")
        if t.get("endpoint_type"):
            _check(
                t["endpoint_type"] in _VALID_ENDPOINT_TYPES,
                f"{prefix}.endpoint_type must be one of {sorted(_VALID_ENDPOINT_TYPES)}, got: {t['endpoint_type']!r}"
            )

    m = cfg.get("market_model", {})
    has_lots = bool(m.get("lines_of_therapy"))
    if not has_lots:
        _check(
            m.get("total_addressable_market_millions") is not None or m.get("addressable_patients_annual") is not None,
            "market_model requires either total_addressable_market_millions, addressable_patients_annual, "
            "or lines_of_therapy (multi-line of therapy segments)"
        )
        _check(m.get("peak_penetration") is not None, "market_model.peak_penetration is required (or use lines_of_therapy)")
        pp = m.get("peak_penetration")
        if pp is not None:
            _check(0 < float(pp) <= 1, f"market_model.peak_penetration must be between 0 and 1, got: {pp}")

    pos = cfg.get("pos_adjusters", {})
    if pos.get("apply_pos_model"):
        for phase_key in ("phase_1", "phase_2", "phase_3", "nda_bla"):
            pc = pos.get(phase_key)
            if pc is None:
                continue
            prefix = f"pos_adjusters.{phase_key}"
            if pc.get("moa_precedent"):
                _check(pc["moa_precedent"] in _VALID_MOA_PRECEDENT,
                       f"{prefix}.moa_precedent must be one of {sorted(_VALID_MOA_PRECEDENT)}, got: {pc['moa_precedent']!r}")
            if pc.get("sample_size_adequacy"):
                _check(pc["sample_size_adequacy"] in _VALID_SAMPLE_ADEQUACY,
                       f"{prefix}.sample_size_adequacy must be one of {sorted(_VALID_SAMPLE_ADEQUACY)}, got: {pc['sample_size_adequacy']!r}")
            if pc.get("safety_profile"):
                _check(pc["safety_profile"] in _VALID_SAFETY,
                       f"{prefix}.safety_profile must be one of {sorted(_VALID_SAFETY)}, got: {pc['safety_profile']!r}")
            if pc.get("competitive_pressure"):
                _check(pc["competitive_pressure"] in _VALID_COMPETITION,
                       f"{prefix}.competitive_pressure must be one of {sorted(_VALID_COMPETITION)}, got: {pc['competitive_pressure']!r}")

    td = cfg.get("trial_design", {})
    if td.get("apply_design_model"):
        for phase_key in ("phase_1", "phase_2", "phase_3", "nda_bla"):
            pc = td.get(phase_key)
            if pc is None:
                continue
            prefix = f"trial_design.{phase_key}"
            if pc.get("endpoint_basis"):
                _check(pc["endpoint_basis"] in _VALID_ENDPOINT_BASIS,
                       f"{prefix}.endpoint_basis must be one of {sorted(_VALID_ENDPOINT_BASIS)}, got: {pc['endpoint_basis']!r}")
            if pc.get("evidence_design"):
                _check(pc["evidence_design"] in _VALID_EVIDENCE_DESIGN,
                       f"{prefix}.evidence_design must be one of {sorted(_VALID_EVIDENCE_DESIGN)}, got: {pc['evidence_design']!r}")
            if pc.get("approval_pathway"):
                _check(pc["approval_pathway"] in _VALID_APPROVAL_PATHWAY,
                       f"{prefix}.approval_pathway must be one of {sorted(_VALID_APPROVAL_PATHWAY)}, got: {pc['approval_pathway']!r}")

    if errors:
        print(f"\nERROR: Config validation failed — {path}", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)


def _load_config(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def _build_objects(cfg: dict):
    """Parse config dict → Asset, Company, trials, MarketModel."""
    from bve.entities.asset import Asset, DevelopmentStage, TherapeuticArea, Modality, Catalyst
    from bve.entities.company import Company
    from bve.entities.trial import ClinicalTrial, TrialPhase, EndpointType
    from bve.models.market_model import MarketModel

    a = cfg["asset"]
    asset = Asset(
        id=a["id"],
        name=a["name"],
        indication=a["indication"],
        therapeutic_area=TherapeuticArea(a["therapeutic_area"]),
        stage=DevelopmentStage(a["stage"]),
        modality=Modality(a.get("modality", "small_molecule")),
        mechanism_of_action=a.get("mechanism_of_action"),
        discount_rate=a.get("discount_rate", float(_COMMERCIAL_DEFAULTS["discount_rate"])),
        royalty_rate=a.get("royalty_rate", 0.0),
        upcoming_catalysts=[Catalyst(**c) for c in a.get("upcoming_catalysts", [])],
        competitor_assets=a.get("competitor_assets", []),
        differentiation_notes=a.get("differentiation_notes"),
        notes=a.get("notes"),
    )

    c = cfg["company"]
    company = Company(
        id=c["id"],
        name=c["name"],
        ticker=c.get("ticker"),
        cash_millions=c["cash_millions"],
        debt_millions=c.get("debt_millions", 0.0),
        shares_outstanding_millions=c["shares_outstanding_millions"],
        burn_rate_millions_per_quarter=c.get("burn_rate_millions_per_quarter"),
        current_price=c.get("current_price"),
        asset_ids=[asset.id],
        notes=c.get("notes"),
    )

    trials = []
    for t in cfg.get("trials", []):
        trials.append(ClinicalTrial(
            asset_id=asset.id,
            phase=TrialPhase(t["phase"]),
            nct_id=t.get("nct_id"),
            success_probability=t["success_probability"],
            duration_years=t["duration_years"],
            cost_millions=t["cost_millions"],
            enrollment=t.get("enrollment"),
            primary_endpoint=t.get("primary_endpoint"),
            endpoint_type=EndpointType(t.get("endpoint_type", "surrogate_validated")),
            notes=t.get("notes"),
        ))

    m = cfg["market_model"]
    from bve.models.market_model import LineOfTherapySegment, LifecycleEvent
    from bve.models.competition_model import (
        CompetitionModel, CompetitorLaunch, CrowdingModel, FirstMoverConfig, ClassSaturationProfile
    )
    lot_cfgs = m.get("lines_of_therapy", [])
    lots = [LineOfTherapySegment(**seg) for seg in lot_cfgs] if lot_cfgs else []

    # Support competition_model nested in market_model (new) or top-level competition list (legacy)
    competition = None
    comp_section = m.get("competition_model") or {}
    comp_cfgs_nested = comp_section.get("competitors", [])
    comp_cfgs_legacy = cfg.get("competition", [])
    raw_comp_cfgs = comp_cfgs_nested or comp_cfgs_legacy
    if raw_comp_cfgs:
        competitors = [CompetitorLaunch(**c) for c in raw_comp_cfgs]
        cm_kwargs: dict = {"competitors": competitors}
        crowding_cfg = comp_section.get("crowding_model")
        if crowding_cfg:
            cm_kwargs["crowding_model"] = CrowdingModel(**crowding_cfg)
        fm_cfg = comp_section.get("first_mover_config")
        if fm_cfg:
            cm_kwargs["first_mover_config"] = FirstMoverConfig(**fm_cfg)
        sat_cfg = comp_section.get("saturation_profile")
        if sat_cfg:
            cm_kwargs["saturation_profile"] = ClassSaturationProfile(**sat_cfg)
        competition = CompetitionModel(**cm_kwargs)

    # Lifecycle events nested in market_model
    lc_cfgs = m.get("lifecycle_events", [])
    lifecycle_events = [LifecycleEvent(**e) for e in lc_cfgs] if lc_cfgs else []

    market_model = MarketModel(
        asset_id=asset.id,
        lines_of_therapy=lots,
        competition_model=competition,
        lifecycle_events=lifecycle_events,
        total_addressable_market_millions=m.get("total_addressable_market_millions"),
        addressable_patients_annual=m.get("addressable_patients_annual"),
        net_price_per_patient_usd=m.get("net_price_per_patient_usd"),
        peak_penetration=m.get("peak_penetration", float(_COMMERCIAL_DEFAULTS["peak_penetration"])),
        years_to_peak=m.get("years_to_peak", 5),
        patent_life_years=m.get("patent_life_years", 12),
        cogs_rate=m.get("cogs_rate", float(_COMMERCIAL_DEFAULTS["cogs_rate"])),
        sgna_rate_launch=m.get("sgna_rate_launch", 0.40),
        sgna_rate_mature=m.get("sgna_rate_mature", 0.20),
    )

    return asset, company, trials, market_model


def _build_pos_adjusters(cfg: dict):
    """Parse optional pos_adjusters section from config."""
    from bve.entities.trial import TrialPhase
    from bve.models.pos_model import (
        POSAdjusters, CompetitivePressure, MoAPrecedent, SafetyProfile, SampleSizeAdequacy
    )
    from bve.entities.trial import EndpointType

    pos_cfg = cfg.get("pos_adjusters", {})
    if not pos_cfg.get("apply_pos_model", False):
        return None, False

    phase_map = {
        "phase_1": TrialPhase.PHASE_1,
        "phase_2": TrialPhase.PHASE_2,
        "phase_3": TrialPhase.PHASE_3,
        "nda_bla": TrialPhase.NDA_BLA,
    }

    adjusters = {}
    for phase_key, phase_enum in phase_map.items():
        phase_cfg = pos_cfg.get(phase_key)
        if phase_cfg is None:
            continue
        adjusters[phase_enum] = POSAdjusters(
            endpoint_type=EndpointType(phase_cfg.get("endpoint_type", "surrogate_validated")),
            moa_precedent=MoAPrecedent(phase_cfg.get("moa_precedent", "partial")),
            sample_size_adequacy=SampleSizeAdequacy(phase_cfg.get("sample_size_adequacy", "adequate")),
            safety_profile=SafetyProfile(phase_cfg.get("safety_profile", "minor")),
            competitive_pressure=CompetitivePressure(phase_cfg.get("competitive_pressure", "moderate")),
            biomarker_selected_population=phase_cfg.get("biomarker_selected_population", False),
            strong_prior_phase_data=phase_cfg.get("strong_prior_phase_data", False),
            has_breakthrough_designation=phase_cfg.get("has_breakthrough_designation", False),
        )

    return adjusters, True


def _build_design_adjusters(cfg: dict):
    """Parse optional trial_design section from config.

    Returns (design_adjusters_dict, apply_design_model_bool).
    design_adjusters_dict maps TrialPhase → TrialDesignFeatureSet.
    """
    from bve.entities.trial import TrialPhase
    from bve.models.trial_design_features import (
        ApprovalPathway, EndpointBasis, EvidenceDesign, TrialDesignFeatureSet
    )

    td_cfg = cfg.get("trial_design", {})
    if not td_cfg.get("apply_design_model", False):
        return None, False

    phase_map = {
        "phase_1": TrialPhase.PHASE_1,
        "phase_2": TrialPhase.PHASE_2,
        "phase_3": TrialPhase.PHASE_3,
        "nda_bla": TrialPhase.NDA_BLA,
    }

    adjusters = {}
    for phase_key, phase_enum in phase_map.items():
        phase_cfg = td_cfg.get(phase_key)
        if phase_cfg is None:
            continue
        adjusters[phase_enum] = TrialDesignFeatureSet(
            endpoint_basis=EndpointBasis(phase_cfg.get("endpoint_basis", "surrogate_validated")),
            evidence_design=EvidenceDesign(phase_cfg.get("evidence_design", "rct_comparative")),
            approval_pathway=ApprovalPathway(phase_cfg.get("approval_pathway", "standard")),
        )

    return adjusters, True


def _output_dir(cfg: dict, base: str) -> Path:
    """Derive output directory: outputs/<ticker_or_asset_name>/"""
    ticker = cfg.get("company", {}).get("ticker") or cfg.get("asset", {}).get("id", "asset")
    return Path(base) / ticker.upper()


def main():
    parser = argparse.ArgumentParser(description="BVE: Run single-asset valuation")
    parser.add_argument("--config", required=True, help="Path to asset YAML config")
    parser.add_argument("--memo", choices=["bd", "vc", "hf"], default="bd")
    parser.add_argument("--all-memos", action="store_true", help="Generate all three memo types")
    parser.add_argument("--charts", action="store_true", help="Save charts")
    parser.add_argument("--out", default="outputs", help="Base output directory (default: outputs/)")
    parser.add_argument("--n-sims", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"ERROR: Config file not found: {cfg_path}", file=sys.stderr)
        sys.exit(1)

    cfg = _load_config(cfg_path)
    _validate_config(cfg, cfg_path)
    asset, company, trials, market_model = _build_objects(cfg)
    pos_adjusters, apply_pos = _build_pos_adjusters(cfg)
    design_adjusters, apply_design = _build_design_adjusters(cfg)

    from bve.models.monte_carlo import MonteCarloParams, PhaseSuccessDistribution
    from bve.entities.trial import TrialPhase
    from bve.valuation.valuation_engine import ValuationEngine
    from bve.reporting.export import export_full_package
    from bve.reporting.memo_generator import save_memo

    # Build MC params — allow per-phase distributions from config
    mc_cfg = cfg.get("monte_carlo", {})
    phase_dists = []
    for phase_key, mean_key in [("phase_1", None), ("phase_2", None), ("phase_3", None), ("nda_bla", None)]:
        pd_cfg = mc_cfg.get("phase_distributions", {}).get(phase_key)
        if pd_cfg:
            phase_dists.append(PhaseSuccessDistribution(
                phase=TrialPhase(phase_key),
                mean=pd_cfg["mean"],
                equivalent_sample_size=pd_cfg.get("ess", 20),
            ))

    mc_params = MonteCarloParams(
        n_simulations=args.n_sims,
        random_seed=mc_cfg.get("random_seed", args.seed),
        peak_sales_cv=mc_cfg.get("peak_sales_cv", _MC_DEFAULTS.mc_peak_sales_cv),
        discount_rate_std=mc_cfg.get("discount_rate_std", _MC_DEFAULTS.mc_discount_rate_std),
        years_to_peak_std=mc_cfg.get("years_to_peak_std", _MC_DEFAULTS.mc_years_to_peak_std),
        phase_distributions=phase_dists,
        use_default_correlations=mc_cfg.get("use_default_correlations", True),
    )

    engine = ValuationEngine(
        asset, company, trials, market_model,
        pos_adjusters=pos_adjusters,
        design_adjusters=design_adjusters,
        mc_params=mc_params,
        apply_pos_model=apply_pos,
        apply_design_model=apply_design,
        analyst_notes=cfg.get("analyst_notes"),
        config_path=str(cfg_path.resolve()),
        limitations=cfg.get("limitations"),
        thesis_changers=cfg.get("thesis_changers"),
    )

    # Optional: assumption source overrides and decision framing
    engine.sources = cfg.get("sources")
    decision_framing_cfg = cfg.get("decision_framing")
    if decision_framing_cfg:
        from bve.valuation.assumptions import DecisionFraming, DownsideDriver, VariantPerception
        vp_cfg = decision_framing_cfg.get("variant_perception")
        vp = VariantPerception(**vp_cfg) if vp_cfg else None
        dd_list = [DownsideDriver(**d) for d in decision_framing_cfg.get("downside_drivers", [])]
        engine.decision_framing = DecisionFraming(
            variant_perception=vp,
            kill_criteria=decision_framing_cfg.get("kill_criteria", []),
            downside_drivers=dd_list,
        )

    print(f"\nRunning valuation: {asset.name} ({company.ticker or company.name})")
    print(f"  Config:       {cfg_path}")
    print(f"  POS model:    {'enabled' if apply_pos else 'using YAML point estimates'}")
    if apply_design:
        phase_summaries = []
        for ph, feat in (design_adjusters or {}).items():
            phase_summaries.append(f"{ph.value}: {feat.evidence_design.value}/{feat.approval_pathway.value}")
        print(f"  Design model: enabled ({'; '.join(phase_summaries)})")
    print(f"  MC sims:      {args.n_sims:,}")
    if market_model.competition_model and market_model.competition_model.competitors:
        print(f"  Competition:  {market_model.competition_model.summary()}")
    output = engine.run()

    # --- Console summary ---
    d = output.summary_dict
    print(f"\n{'═'*58}")
    print(f"  {asset.name} | {asset.indication}")
    print(f"  {company.name} ({company.ticker or '—'})")
    print(f"{'═'*58}")
    print(f"  {'rNPV':<34} ${d['rnpv_millions']:>10,.1f}M")
    print(f"  {'P(Approval)':<34} {d['prob_approval_pct']:>11}")
    print(f"  {'Peak Sales (base)':<34} ${d['peak_sales_millions']:>10,.0f}M")
    print(f"  {'Years to Launch':<34} {d['years_to_launch']:>11.1f} yrs")
    print(f"  {'Net Cash':<34} ${d['net_cash_millions']:>10,.0f}M")
    print(f"  {'NAV/Share':<34} ${d['nav_per_share']:>10.2f}")
    if d["current_price"]:
        print(f"  {'Current Price':<34} ${d['current_price']:>10.2f}")
        upside = d["implied_upside_pct"]
        direction = "upside" if upside and upside > 0 else "downside"
        print(f"  {'Implied vs NAV':<34} {abs(upside or 0):>10.0f}% {direction}")
    print(f"{'─'*58}")
    print(f"  {'MC Mean':<34} ${d['mc_mean']:>10,.0f}M")
    print(f"  {'MC P10 – P90':<34}   ${d['mc_p10']:>7,.0f}M – ${d['mc_p90']:,.0f}M")
    print(f"  {'Scenarios Bull / Base / Bear':<34}   "
          f"${d['bull_rnpv']:,.0f} / ${d['base_rnpv']:,.0f} / ${d['bear_rnpv']:,.0f}M")
    print(f"{'═'*58}")

    # --- Save outputs ---
    out_dir = _output_dir(cfg, args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, str] = {}

    # JSON
    json_path = output.save_json(out_dir / "valuation.json")
    artifacts["valuation.json"] = str(json_path)

    # Memos
    memo_types = ["bd", "vc", "hf"] if args.all_memos else [args.memo]
    for mt in memo_types:
        from bve.reporting.memo_generator import generate_memo
        from bve.reporting.export import markdown_to_docx
        md = generate_memo(output, memo_type=mt)
        md_path = out_dir / f"{mt}_memo.md"
        md_path.write_text(md, encoding="utf-8")
        artifacts[f"{mt}_memo.md"] = str(md_path)
        try:
            docx_path = out_dir / f"{mt}_memo.docx"
            markdown_to_docx(md, docx_path, title=f"{asset.name} — {mt.upper()} Memo")
            artifacts[f"{mt}_memo.docx"] = str(docx_path)
        except Exception as e:
            artifacts[f"{mt}_memo.docx"] = f"ERROR: {e}"

    # Charts
    if args.charts:
        from bve.reporting.charts import save_all_charts
        chart_dir = out_dir / "charts"
        chart_paths = save_all_charts(output, str(chart_dir))
        for k, v in chart_paths.items():
            artifacts[f"chart_{k}"] = v

    print(f"\nOutputs → {out_dir}/")
    for k, v in artifacts.items():
        rel = Path(v).relative_to(Path(args.out)) if Path(v).exists() else Path(v)
        print(f"  {k:<28} {rel}")


if __name__ == "__main__":
    main()
