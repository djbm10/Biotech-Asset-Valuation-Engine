"""
Example: End-to-end valuation for XYZ-101 (KRAS G12C inhibitor, Phase 2 NSCLC).

Demonstrates the full BVE pipeline:
  1. Define entities (Asset, Company, Trials, MarketModel)
  2. Apply POS model with analyst qualitative inputs
  3. Run ValuationEngine (rNPV + scenarios + Monte Carlo + sensitivity)
  4. Generate a BD memo
  5. Save charts

Run from project root:
    pip install -e .
    python examples/single_asset_valuation.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bve import (
    Asset, Company, ClinicalTrial, Indication,
    DevelopmentStage, TherapeuticArea, Modality, Catalyst,
    TrialPhase, EndpointType,
    MarketModel,
    POSAdjusters, MoAPrecedent, SafetyProfile, CompetitivePressure,
    MonteCarloParams, PhaseSuccessDistribution,
    ValuationEngine,
    generate_memo, save_all_charts,
)
from bve.models.pos_model import SampleSizeAdequacy


# ---------------------------------------------------------------------------
# 1. Entities
# ---------------------------------------------------------------------------
asset = Asset(
    id="xyz-101",
    name="XYZ-101",
    indication="KRAS G12C NSCLC (2nd line)",
    therapeutic_area=TherapeuticArea.ONCOLOGY,
    stage=DevelopmentStage.PHASE_2,
    modality=Modality.SMALL_MOLECULE,
    mechanism_of_action="KRAS G12C covalent inhibitor — improved CNS penetration vs. approved agents",
    discount_rate=0.10,
    royalty_rate=0.0,
    differentiation_notes="Best-in-class CNS penetration; active vs. acquired resistance (Y96D/H95R)",
    competitor_assets=["Sotorasib (Lumakras)", "Adagrasib (Krazati)", "Divarasib"],
    upcoming_catalysts=[
        Catalyst(
            description="Phase 2 topline readout (ORR primary endpoint)",
            expected_date="Q3 2026",
            catalyst_type="readout",
            probability_positive=0.40,
        ),
    ],
)

company = Company(
    id="bioxy-inc",
    name="BioXYZ, Inc.",
    ticker="BXYZ",
    cash_millions=450.0,
    debt_millions=50.0,
    shares_outstanding_millions=120.0,
    burn_rate_millions_per_quarter=28.0,
    current_price=7.50,
    asset_ids=["xyz-101"],
)

trials = [
    ClinicalTrial(
        asset_id="xyz-101",
        phase=TrialPhase.PHASE_2,
        success_probability=0.40,    # will be overridden by POS model below
        duration_years=2.5,
        cost_millions=80.0,
        enrollment=120,
        primary_endpoint="ORR ≥ 40%",
        endpoint_type=EndpointType.SURROGATE_VALIDATED,
        is_randomized=False,         # single-arm Ph2
    ),
    ClinicalTrial(
        asset_id="xyz-101",
        phase=TrialPhase.PHASE_3,
        success_probability=0.55,
        duration_years=3.5,
        cost_millions=250.0,
        enrollment=500,
        primary_endpoint="PFS (HR < 0.70 vs. docetaxel)",
        endpoint_type=EndpointType.SURROGATE_VALIDATED,
    ),
    ClinicalTrial(
        asset_id="xyz-101",
        phase=TrialPhase.NDA_BLA,
        success_probability=0.87,
        duration_years=1.5,
        cost_millions=30.0,
    ),
]

# US market: ~50K eligible KRAS G12C NSCLC patients/yr, $78K net price
market_model = MarketModel(
    asset_id="xyz-101",
    addressable_patients_annual=50_000,
    net_price_per_patient_usd=78_000,
    peak_penetration=0.18,
    years_to_peak=5,
    patent_life_years=12,
    cogs_rate=0.15,
    sgna_rate_launch=0.40,
    sgna_rate_mature=0.20,
)

# ---------------------------------------------------------------------------
# 2. POS model with analyst qualitative inputs
# ---------------------------------------------------------------------------
pos_adjusters = {
    TrialPhase.PHASE_2: POSAdjusters(
        endpoint_type=EndpointType.SURROGATE_VALIDATED,
        moa_precedent=MoAPrecedent.VALIDATED,       # class is validated (sotorasib/adagrasib approved)
        sample_size_adequacy=SampleSizeAdequacy.BORDERLINE,  # single-arm, n=120
        safety_profile=SafetyProfile.MINOR,
        competitive_pressure=CompetitivePressure.HIGH,
        biomarker_selected_population=True,          # KRAS G12C-selected population
        strong_prior_phase_data=True,                # Phase 1 showed ORR ~35%
    ),
    TrialPhase.PHASE_3: POSAdjusters(
        endpoint_type=EndpointType.SURROGATE_VALIDATED,
        moa_precedent=MoAPrecedent.VALIDATED,
        sample_size_adequacy=SampleSizeAdequacy.ADEQUATE,
        safety_profile=SafetyProfile.MINOR,
        competitive_pressure=CompetitivePressure.HIGH,
        biomarker_selected_population=True,
    ),
    TrialPhase.NDA_BLA: POSAdjusters(),
}

# ---------------------------------------------------------------------------
# 3. Monte Carlo parameters
# ---------------------------------------------------------------------------
mc_params = MonteCarloParams(
    n_simulations=10_000,
    random_seed=42,
    peak_sales_cv=0.35,
    discount_rate_std=0.02,
    years_to_peak_std=1.5,
    phase_distributions=[
        PhaseSuccessDistribution(phase=TrialPhase.PHASE_2, mean=0.40, equivalent_sample_size=12),
        PhaseSuccessDistribution(phase=TrialPhase.PHASE_3, mean=0.55, equivalent_sample_size=18),
        PhaseSuccessDistribution(phase=TrialPhase.NDA_BLA, mean=0.87, equivalent_sample_size=35),
    ],
    use_default_correlations=True,
)

# ---------------------------------------------------------------------------
# 4. Run ValuationEngine
# ---------------------------------------------------------------------------
engine = ValuationEngine(
    asset=asset,
    company=company,
    trials=trials,
    market_model=market_model,
    pos_adjusters=pos_adjusters,
    mc_params=mc_params,
    apply_pos_model=True,           # override trial POS with the POS model
    analyst_notes="Strong clinical validation in KRAS G12C class. Key differentiator is CNS activity.",
)

print("Running valuation...")
output = engine.run()
d = output.summary_dict

# ---------------------------------------------------------------------------
# 5. Print results
# ---------------------------------------------------------------------------
print(f"\n{'='*60}")
print(f"  {asset.name} — {asset.indication}")
print(f"{'='*60}")
print(f"  {'rNPV':<30} ${d['rnpv_millions']:>10,.1f}M")
print(f"  {'P(Approval)':<30} {d['prob_approval_pct']:>11}")
print(f"  {'Peak Sales (base)':<30} ${d['peak_sales_millions']:>10,.0f}M")
print(f"  {'Years to Launch':<30} {d['years_to_launch']:>11}")
print(f"  {'Net Ownership':<30} {d['net_ownership_pct']:>11}")
print(f"  {'Discount Rate (WACC)':<30} {d['discount_rate_pct']:>11}")

print(f"\n  Phase Cost Breakdown (prob-weighted PV):")
for pb in output.rnpv.phase_breakdown:
    print(f"    {pb.phase:<12}  P(reach)={pb.prob_reaching:.1%}  PV cost=${pb.pv_cost_weighted:,.1f}M")

print(f"\n  {'─'*55}")
print(f"  {'Gross Revenue PV':<30} ${output.rnpv.gross_revenue_pv_millions:>10,.1f}M")
print(f"  {'× P(Approval)':<30} {output.rnpv.cumulative_success_probability:>11.1%}")
print(f"  {'Prob-Adj Revenue PV':<30} ${output.rnpv.probability_adjusted_revenue_pv_millions:>10,.1f}M")
print(f"  {'Trial Costs PV (weighted)':<30} (${output.rnpv.trial_costs_pv_millions:>8,.1f}M)")
print(f"  {'rNPV':<30} ${d['rnpv_millions']:>10,.1f}M")
print(f"  {'Net Cash':<30} ${d['net_cash_millions']:>10,.1f}M")
print(f"  {'Total NAV':<30} ${d['nav_millions']:>10,.1f}M")
print(f"  {'NAV/Share':<30} ${d['nav_per_share']:>10.2f}")
if output.implied_upside_pct is not None:
    price_label = f"Implied upside vs ${d['current_price']:.2f}"
    print(f"  {price_label:<30} {output.implied_upside_pct:>10.0f}%")

print(f"\n{'='*60}")
print(f"  Scenario Analysis")
print(f"{'='*60}")
for s in output.scenarios.as_list:
    print(f"  {s.label:<8}  rNPV=${s.rnpv_millions:>8,.0f}M  NAV/sh=${s.nav_per_share:>6.2f}  P={s.cumulative_success_probability:.1%}")

print(f"\n{'='*60}")
print(f"  Monte Carlo (n={mc_params.n_simulations:,})")
print(f"{'='*60}")
mc = output.monte_carlo
print(f"  {'Mean':<10} ${mc.mean_millions:>10,.1f}M")
print(f"  {'Std Dev':<10} ${mc.std_millions:>10,.1f}M")
print(f"  {'P10':<10} ${mc.percentile_10_millions:>10,.1f}M")
print(f"  {'P50':<10} ${mc.percentile_50_millions:>10,.1f}M")
print(f"  {'P90':<10} ${mc.percentile_90_millions:>10,.1f}M")
print(f"  {'P(>0)':<10} {mc.probability_positive:>11.1%}")
print(f"  {'P(>$500M)':<10} {mc.probability_above_500m:>11.1%}")

print(f"\n{'='*60}")
print(f"  Tornado Sensitivities (sorted by |swing|)")
print(f"{'='*60}")
for s in output.sensitivities:
    print(f"  {s.parameter:<30}  bear=${s.low_rnpv:>7,.0f}M  bull=${s.high_rnpv:>7,.0f}M  Δ=${abs(s.swing):>6,.0f}M")

# ---------------------------------------------------------------------------
# 6. Generate BD memo
# ---------------------------------------------------------------------------
print(f"\nGenerating BD memo...")
memo_md = generate_memo(output, memo_type="bd")
memo_path = Path("memos/bd/XYZ-101_bd_memo.md")
memo_path.parent.mkdir(parents=True, exist_ok=True)
memo_path.write_text(memo_md)
print(f"  Saved: {memo_path}")

# ---------------------------------------------------------------------------
# 7. Save charts
# ---------------------------------------------------------------------------
print(f"\nSaving charts...")
chart_paths = save_all_charts(output, output_dir="memos/charts")
for name, path in chart_paths.items():
    print(f"  {name:<25} {path}")
