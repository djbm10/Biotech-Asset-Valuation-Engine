"""
Portfolio (company-level) valuation.

Aggregates individual asset rNPV valuations for a company with multiple pipeline
assets, adds net cash, and computes NAV/share.

Usage
-----
    from bve.valuation.portfolio import run_portfolio_valuation

    result = run_portfolio_valuation(company, asset_outputs)
    print(result.summary())
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from bve.entities.company import Company


class AssetContribution(BaseModel):
    """Per-asset contribution to company NAV."""
    asset_id: str
    asset_name: str
    indication: str
    stage: str
    rnpv_millions: float
    prob_approval: float
    peak_sales_millions: float
    years_to_launch: float
    config_path: Optional[str] = None

    @property
    def rnpv_per_share(self) -> float:
        """Placeholder; set externally after dividing by shares."""
        return 0.0


class DilutionScenario(BaseModel):
    """Models future equity dilution from capital raises."""
    label: str                         # e.g., "Base (no dilution)", "Phase 3 raise"
    additional_shares_millions: float  # new shares issued
    proceeds_millions: float           # cash raised (adds to cash balance)

    @property
    def diluted_shares(self) -> float:
        return self.additional_shares_millions


class PortfolioValuation(BaseModel):
    """
    Company-level NAV aggregating multiple pipeline assets.

    NAV = sum(asset rNPVs) + net cash
    NAV/share = NAV / shares_outstanding
    """
    company: Company
    assets: list[AssetContribution]

    # Optional dilution scenarios (what if the company raises equity?)
    dilution_scenarios: list[DilutionScenario] = []

    model_config = {"arbitrary_types_allowed": True}

    @property
    def total_pipeline_rnpv(self) -> float:
        return round(sum(a.rnpv_millions for a in self.assets), 2)

    @property
    def nav_millions(self) -> float:
        return round(self.total_pipeline_rnpv + self.company.net_cash_millions, 2)

    @property
    def nav_per_share(self) -> float:
        return round(self.nav_millions / self.company.shares_outstanding_millions, 2)

    @property
    def implied_upside_pct(self) -> Optional[float]:
        price = self.company.current_price
        if price and price > 0:
            return round((self.nav_per_share / price - 1) * 100, 1)
        return None

    @property
    def pipeline_value_per_share(self) -> float:
        return round(self.total_pipeline_rnpv / self.company.shares_outstanding_millions, 2)

    @property
    def cash_per_share(self) -> float:
        return round(self.company.net_cash_millions / self.company.shares_outstanding_millions, 2)

    def nav_under_dilution(self, scenario: DilutionScenario) -> dict:
        """Compute NAV/share under a dilution scenario."""
        diluted_shares = self.company.shares_outstanding_millions + scenario.additional_shares_millions
        diluted_cash = self.company.net_cash_millions + scenario.proceeds_millions
        diluted_nav = self.total_pipeline_rnpv + diluted_cash
        diluted_nav_ps = round(diluted_nav / diluted_shares, 2)
        dilution_impact = round(diluted_nav_ps - self.nav_per_share, 2)
        return {
            "label": scenario.label,
            "additional_shares_m": scenario.additional_shares_millions,
            "proceeds_m": scenario.proceeds_millions,
            "diluted_shares_m": diluted_shares,
            "diluted_nav_m": round(diluted_nav, 2),
            "diluted_nav_per_share": diluted_nav_ps,
            "nav_per_share_impact": dilution_impact,
        }

    def summary(self) -> str:
        lines = [
            f"\n{'='*60}",
            f"  {self.company.name} ({self.company.ticker or '—'}) — Portfolio NAV",
            f"{'='*60}",
        ]
        for a in sorted(self.assets, key=lambda x: x.rnpv_millions, reverse=True):
            lines.append(
                f"  {a.asset_name:<25} {a.indication[:30]:<30}  "
                f"rNPV: ${a.rnpv_millions:>8,.1f}M  "
                f"P(approval): {a.prob_approval:.1%}"
            )
        lines += [
            f"{'─'*60}",
            f"  {'Pipeline rNPV':<55} ${self.total_pipeline_rnpv:>8,.1f}M",
            f"  {'Net Cash':<55} ${self.company.net_cash_millions:>8,.1f}M",
            f"  {'Total NAV':<55} ${self.nav_millions:>8,.1f}M",
            f"  {'NAV/Share':<55} ${self.nav_per_share:>8.2f}",
        ]
        if self.company.current_price:
            upside = self.implied_upside_pct or 0
            lines.append(
                f"  {'Current Price':<55} ${self.company.current_price:>8.2f}"
            )
            lines.append(
                f"  {'Implied vs. NAV':<55} {abs(upside):>7.0f}% {'upside' if upside > 0 else 'downside'}"
            )
        lines.append(f"{'='*60}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        result = {
            "company": {
                "name": self.company.name,
                "ticker": self.company.ticker,
                "net_cash_millions": self.company.net_cash_millions,
                "shares_outstanding_millions": self.company.shares_outstanding_millions,
                "current_price": self.company.current_price,
            },
            "assets": [
                {
                    "asset_name": a.asset_name,
                    "indication": a.indication,
                    "stage": a.stage,
                    "rnpv_millions": a.rnpv_millions,
                    "prob_approval": a.prob_approval,
                    "peak_sales_millions": a.peak_sales_millions,
                    "years_to_launch": a.years_to_launch,
                }
                for a in self.assets
            ],
            "summary": {
                "total_pipeline_rnpv_millions": self.total_pipeline_rnpv,
                "nav_millions": self.nav_millions,
                "nav_per_share": self.nav_per_share,
                "pipeline_value_per_share": self.pipeline_value_per_share,
                "cash_per_share": self.cash_per_share,
                "implied_upside_pct": self.implied_upside_pct,
            },
        }
        if self.dilution_scenarios:
            result["dilution_scenarios"] = [
                self.nav_under_dilution(s) for s in self.dilution_scenarios
            ]
        return result


def run_portfolio_valuation(
    company: Company,
    asset_outputs: list,          # list[ValuationOutput]
    dilution_scenarios: Optional[list[DilutionScenario]] = None,
) -> PortfolioValuation:
    """
    Aggregate individual ValuationOutput objects into a company-level NAV.

    Parameters
    ----------
    company:          Company entity (provides cash, shares, price)
    asset_outputs:    List of ValuationOutput from ValuationEngine.run()
    dilution_scenarios: Optional list of equity raise scenarios to model

    Returns
    -------
    PortfolioValuation with per-asset contributions and aggregate NAV
    """
    contributions = []
    for out in asset_outputs:
        contributions.append(AssetContribution(
            asset_id=out.asset.id,
            asset_name=out.asset.name,
            indication=out.asset.indication,
            stage=out.asset.stage.value,
            rnpv_millions=out.rnpv.rnpv_millions,
            prob_approval=out.rnpv.cumulative_success_probability,
            peak_sales_millions=out.rnpv.peak_sales_millions,
            years_to_launch=out.rnpv.years_to_launch,
            config_path=out.config_path,
        ))

    return PortfolioValuation(
        company=company,
        assets=contributions,
        dilution_scenarios=dilution_scenarios or [],
    )
