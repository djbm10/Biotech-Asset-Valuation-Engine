"""PortfolioAllocator — applies constraints and produces final allocation."""

from __future__ import annotations

from dataclasses import dataclass, field

from .constraints import PortfolioConstraints
from .risk_model import PositionInput, RiskModel


@dataclass
class AllocationResult:
    """Final allocation recommendation for a single name."""

    ticker: str
    action: str                          # "buy" | "no_action" | "reduce"
    suggested_size_pct_nav: float
    max_loss_contribution_pct_nav: float
    cap_reason: str | None               # why size was capped (None if uncapped)
    blocked_reason: str | None           # why action = no_action
    raw_size_pct_nav: float              # pre-constraint size

    def describe(self) -> str:
        lines = [f"Action: {self.action}"]
        lines.append(f"Suggested size: {self.suggested_size_pct_nav:.2f}% NAV")
        lines.append(f"Max loss contribution: {self.max_loss_contribution_pct_nav:.2f}% NAV")
        if self.cap_reason:
            lines.append(f"Reason size capped: {self.cap_reason}")
        if self.blocked_reason:
            lines.append(f"Blocked: {self.blocked_reason}")
        return "\n".join(lines)


@dataclass
class PortfolioState:
    """Current portfolio exposure used to enforce constraints."""

    positions: dict[str, float] = field(default_factory=dict)          # ticker → % NAV
    phase2_total_pct: float = 0.0
    preclinical_total_pct: float = 0.0
    catalyst_month_exposure: dict[str, float] = field(default_factory=dict)  # month → % NAV
    modality_exposure: dict[str, float] = field(default_factory=dict)   # modality → % NAV


class PortfolioAllocator:
    """Applies constraint-based position sizing."""

    def __init__(
        self,
        constraints: PortfolioConstraints | None = None,
        risk_model: RiskModel | None = None,
    ) -> None:
        self._constraints = constraints or PortfolioConstraints()
        self._risk = risk_model or RiskModel()

    def allocate(
        self,
        inp: PositionInput,
        portfolio: PortfolioState | None = None,
    ) -> AllocationResult:
        state = portfolio or PortfolioState()
        c = self._constraints

        # Check hard blocks first
        blocked = self._check_hard_blocks(inp, state, c)
        if blocked:
            return AllocationResult(
                ticker=inp.ticker,
                action="no_action",
                suggested_size_pct_nav=0.0,
                max_loss_contribution_pct_nav=0.0,
                cap_reason=None,
                blocked_reason=blocked,
                raw_size_pct_nav=0.0,
            )

        raw_size = self._risk.compute_raw_size_pct(inp)
        capped_size, cap_reason = self._apply_caps(raw_size, inp, state, c)

        # Enforce max_loss per position
        max_loss = self._risk.max_loss_contribution_pct(capped_size, inp.downside_case)

        return AllocationResult(
            ticker=inp.ticker,
            action="buy" if capped_size > 0 else "no_action",
            suggested_size_pct_nav=round(capped_size, 3),
            max_loss_contribution_pct_nav=round(max_loss, 3),
            cap_reason=cap_reason,
            blocked_reason=None,
            raw_size_pct_nav=round(raw_size, 3),
        )

    def _check_hard_blocks(
        self, inp: PositionInput, state: PortfolioState, c: PortfolioConstraints
    ) -> str | None:
        if inp.phase == "preclinical" and c.max_preclinical_pct_nav == 0:
            return "preclinical positions not allowed by policy"
        if inp.expected_return <= 0:
            return "expected return is non-positive"
        if inp.downside_case >= 0:
            return "no identifiable downside (downside_case must be negative)"
        return None

    def _apply_caps(
        self,
        raw_size: float,
        inp: PositionInput,
        state: PortfolioState,
        c: PortfolioConstraints,
    ) -> tuple[float, str | None]:
        size = raw_size
        cap_reason = None

        # Single-name cap
        if size > c.max_single_name_pct_nav:
            size = c.max_single_name_pct_nav
            cap_reason = f"single-name limit ({c.max_single_name_pct_nav:.1f}% NAV)"

        # Phase 2 cluster cap
        if inp.phase == "phase_2":
            headroom = max(0.0, c.max_phase2_pct_nav - state.phase2_total_pct)
            if size > headroom:
                size = headroom
                cap_reason = f"Phase 2 cluster exposure limit ({c.max_phase2_pct_nav:.1f}% NAV)"

        # Catalyst month cap
        if inp.catalyst_month:
            month_exposure = state.catalyst_month_exposure.get(inp.catalyst_month, 0.0)
            headroom = max(0.0, c.max_same_catalyst_month_pct_nav - month_exposure)
            if size > headroom:
                size = headroom
                cap_reason = f"same-catalyst-month cluster limit ({c.max_same_catalyst_month_pct_nav:.1f}% NAV)"

        # Modality cap
        if inp.modality:
            mod_exposure = state.modality_exposure.get(inp.modality, 0.0)
            headroom = max(0.0, c.max_same_modality_pct_nav - mod_exposure)
            if size > headroom:
                size = headroom
                cap_reason = f"same-modality limit ({c.max_same_modality_pct_nav:.1f}% NAV)"

        return max(0.0, size), cap_reason
