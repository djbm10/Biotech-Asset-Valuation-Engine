"""
Standard charts for the BVE reporting layer.

All functions accept a ValuationOutput and return a matplotlib Figure.
Call fig.savefig(path, dpi=150, bbox_inches='tight') to export.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

if TYPE_CHECKING:
    from bve.valuation.outputs import ValuationOutput

# Color palette
C_BASE = "#2e75b6"
C_BULL = "#2e8b57"
C_BEAR = "#c0392b"
C_NEUTRAL = "#7f7f7f"
C_LIGHT = "#d6e4f0"


def _fmt_millions(x, _):
    if abs(x) >= 1000:
        return f"${x/1000:.1f}B"
    return f"${x:.0f}M"


# ---------------------------------------------------------------------------
# 1. Monte Carlo distribution histogram
# ---------------------------------------------------------------------------

def plot_mc_distribution(output: "ValuationOutput", bins: int = 60) -> plt.Figure:
    mc = output.monte_carlo
    values = mc.simulated_values_millions

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.hist(values, bins=bins, color=C_BASE, alpha=0.75, edgecolor="white", linewidth=0.4)

    # Percentile lines
    for pct, val, label, color in [
        (10, mc.percentile_10_millions, "P10", C_BEAR),
        (50, mc.percentile_50_millions, "P50", C_NEUTRAL),
        (90, mc.percentile_90_millions, "P90", C_BULL),
    ]:
        ax.axvline(val, color=color, linestyle="--", linewidth=1.5, label=f"{label}: ${val:,.0f}M")

    ax.axvline(mc.mean_millions, color="#e67e22", linestyle="-", linewidth=1.5, label=f"Mean: ${mc.mean_millions:,.0f}M")
    ax.axvline(0, color="black", linestyle=":", linewidth=1, alpha=0.5)

    ax.xaxis.set_major_formatter(mticker.FuncFormatter(_fmt_millions))
    ax.set_xlabel("rNPV ($M)", fontsize=11)
    ax.set_ylabel("Simulations", fontsize=11)
    ax.set_title(
        f"{output.asset.name} — rNPV Distribution ({mc.n_simulations:,} simulations)\n"
        f"P(positive): {mc.probability_positive:.1%}",
        fontsize=12,
        fontweight="bold",
    )
    ax.legend(fontsize=9)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# 2. Tornado / sensitivity chart
# ---------------------------------------------------------------------------

def plot_tornado(output: "ValuationOutput") -> plt.Figure:
    sensitivities = output.sensitivities
    base = output.rnpv.rnpv_millions

    fig, ax = plt.subplots(figsize=(10, max(4, len(sensitivities) * 0.9)))

    y_positions = list(range(len(sensitivities)))
    labels = [s.parameter for s in sensitivities]

    for i, s in enumerate(sensitivities):
        lo = min(s.low_rnpv, s.high_rnpv) - base
        hi = max(s.low_rnpv, s.high_rnpv) - base
        ax.barh(i, lo, left=base, color=C_BEAR, alpha=0.85)
        ax.barh(i, hi - lo, left=base + lo, color=C_BULL, alpha=0.85)

    ax.axvline(base, color="black", linewidth=1.5, label=f"Base: ${base:,.0f}M")
    ax.set_yticks(y_positions)
    ax.set_yticklabels(labels, fontsize=10)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(_fmt_millions))
    ax.set_xlabel("rNPV ($M)", fontsize=11)
    ax.set_title(f"{output.asset.name} — Sensitivity Tornado", fontsize=12, fontweight="bold")
    ax.legend(fontsize=9)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# 3. Revenue curve (base / bull / bear)
# ---------------------------------------------------------------------------

def plot_revenue_curve(output: "ValuationOutput") -> plt.Figure:
    market = output.market_model
    years = list(range(1, market.patent_life_years + 1))
    base_rev = market.revenue_curve()

    # Bull/bear scale revenue by scenario peak_sales multiplier
    bull_mult = output.scenarios.bull.peak_sales_millions / output.rnpv.peak_sales_millions if output.rnpv.peak_sales_millions else 1.0
    bear_mult = output.scenarios.bear.peak_sales_millions / output.rnpv.peak_sales_millions if output.rnpv.peak_sales_millions else 1.0

    bull_rev = [r * bull_mult for r in base_rev]
    bear_rev = [r * bear_mult for r in base_rev]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.fill_between(years, bear_rev, bull_rev, alpha=0.15, color=C_BASE, label="Bull–Bear range")
    ax.plot(years, bull_rev, color=C_BULL, linestyle="--", linewidth=1.5, label=f"Bull (${max(bull_rev):.0f}M peak)")
    ax.plot(years, base_rev, color=C_BASE, linewidth=2.5, label=f"Base (${max(base_rev):.0f}M peak)")
    ax.plot(years, bear_rev, color=C_BEAR, linestyle="--", linewidth=1.5, label=f"Bear (${max(bear_rev):.0f}M peak)")

    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_millions))
    ax.set_xlabel("Years Post-Launch", fontsize=11)
    ax.set_ylabel("Net Revenue ($M)", fontsize=11)
    ax.set_title(f"{output.asset.name} — Revenue Curve (Net, Post-Launch)", fontsize=12, fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# 4. Scenario comparison bar chart
# ---------------------------------------------------------------------------

def plot_scenario_bars(output: "ValuationOutput") -> plt.Figure:
    scenarios = output.scenarios.as_list
    labels = [s.label for s in scenarios]
    values = [s.nav_millions for s in scenarios]
    colors = [C_BULL, C_BASE, C_BEAR]

    fig, ax = plt.subplots(figsize=(7, 5))
    bars = ax.bar(labels, values, color=colors, alpha=0.85, width=0.5)

    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(values) * 0.02,
            f"${val:,.0f}M",
            ha="center", va="bottom", fontsize=11, fontweight="bold",
        )

    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_millions))
    ax.set_ylabel("Total NAV ($M)", fontsize=11)
    ax.set_title(f"{output.asset.name} — NAV by Scenario", fontsize=12, fontweight="bold")
    ax.axhline(0, color="black", linewidth=0.8)

    # Strategic takeout band (opt-in; only when enabled). Reference overlay showing the
    # estimated acquisition (takeout) price range relative to the scenario NAV bars.
    st = output.strategic_takeout
    if st is not None:
        ax.axhspan(
            st.low_millions, st.high_millions,
            color=C_NEUTRAL, alpha=0.12, zorder=0,
            label="Strategic takeout range (low–high)",
        )
        ax.axhline(st.base_millions, color=C_NEUTRAL, linestyle="--", linewidth=1.2, zorder=1)
        ax.axhline(st.floor_millions, color="black", linestyle=":", linewidth=1.0, zorder=1)
        x_right = ax.get_xlim()[1]
        ax.text(x_right, st.base_millions, f"takeout base ${st.base_millions:,.0f}M ",
                ha="right", va="bottom", fontsize=8, color=C_NEUTRAL)
        ax.text(x_right, st.floor_millions, f"rNPV floor ${st.floor_millions:,.0f}M ",
                ha="right", va="bottom", fontsize=8, color="black")
        ax.set_ylim(top=max(max(values, default=0.0), st.high_millions) * 1.15)
        ax.legend(loc="upper left", fontsize=8, framealpha=0.6)

    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# 5. Catalyst timeline
# ---------------------------------------------------------------------------

def plot_catalyst_timeline(output: "ValuationOutput") -> plt.Figure:
    catalysts = output.asset.upcoming_catalysts
    if not catalysts:
        fig, ax = plt.subplots(figsize=(8, 2))
        ax.text(0.5, 0.5, "No catalysts defined", ha="center", va="center", transform=ax.transAxes)
        return fig

    fig, ax = plt.subplots(figsize=(max(8, len(catalysts) * 2), 3))
    y = 0.5
    ax.axhline(y, color=C_NEUTRAL, linewidth=1.5, zorder=0)

    colors_by_type = {
        "readout": C_BASE,
        "fda_action": "#8e44ad",
        "partnership": "#27ae60",
        "milestone": C_NEUTRAL,
    }

    for i, cat in enumerate(catalysts):
        color = colors_by_type.get(cat.catalyst_type, C_BASE)
        ax.scatter(i, y, s=150, color=color, zorder=5)
        ax.text(i, y + 0.15, cat.expected_date or "TBD", ha="center", va="bottom", fontsize=8.5)
        ax.text(i, y - 0.18, cat.description[:30], ha="center", va="top", fontsize=8, wrap=True)

    ax.set_xlim(-0.5, len(catalysts) - 0.5)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.set_title(f"{output.asset.name} — Catalyst Calendar", fontsize=12, fontweight="bold")
    fig.tight_layout()
    return fig


def save_all_charts(output: "ValuationOutput", output_dir: str = "memos/charts") -> dict[str, str]:
    """Save all standard charts and return dict of {chart_name: path}."""
    from pathlib import Path
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    asset_slug = output.asset.name.replace(" ", "_")
    saved = {}

    chart_fns = {
        "mc_distribution": plot_mc_distribution,
        "tornado": plot_tornado,
        "revenue_curve": plot_revenue_curve,
        "scenario_bars": plot_scenario_bars,
        "catalyst_timeline": plot_catalyst_timeline,
    }

    for name, fn in chart_fns.items():
        try:
            fig = fn(output)
            path = out / f"{asset_slug}_{name}.png"
            fig.savefig(path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            saved[name] = str(path)
        except Exception as e:
            saved[name] = f"ERROR: {e}"

    return saved
