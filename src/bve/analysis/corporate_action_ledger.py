"""CorporateActionLedger — chains CorporateAction rows and resolves terminal proceeds.

Replaces the single-scalar `share_conversion_ratio` column in
`failed_delisted_biotech_candidates.csv` (proven inadequate by the 6-name pilot:
CNAT and CEMP each involve a reverse split of the *original* security distinct
from any merger exchange ratio applied to the *other* side of the deal, and CEMP's
true terminal outcome only appears after chaining through MLNT's later bankruptcy).

Price-basis invariant (locked)
------------------------------
`resolve()` requires RAW (actual, as-traded, unadjusted) entry prices and share
counts — never a split/dividend-adjusted price series (e.g. a vendor "Adj Close"
column that has already been retroactively divided by a split ratio that hasn't
happened yet at the entry date). This module is the *only* place split/merger
ratios are applied; if the input price were already adjusted, applying a
REVERSE_SPLIT/FORWARD_SPLIT action here would double-adjust the position.
`price_basis=PriceBasis.SPLIT_ADJUSTED` is accepted as an explicit input only to
raise immediately — there is no supported reconciliation path for pre-adjusted
prices, on purpose, rather than attempting (and risking getting wrong) an
automatic re-basing.

Point-in-time separation (locked)
----------------------------------
Every action carries both `effective_date` (when shareholders were actually
affected) and `known_at` (when the terms became knowable/disclosed). `resolve()`
accepts an optional `as_of_date`: when given, the chain walk stops at the first
action whose `known_at` is None or later than `as_of_date` — a later action can
never be applied just because its own `known_at` happens to be <= `as_of_date`
while an earlier one in the chain is not yet known, since that would let future
information leak past a still-unresolved event. Not supplying `as_of_date` (the
default) does full-hindsight resolution — appropriate for a final, dated
reconciliation report, never for a walk-forward backtest.

Security lineage vs ticker lineage
-----------------------------------
Every method here is keyed exclusively by permanent `security_id` strings
(e.g. "SEC-ARRY"). Tickers are never read by this module — ARRY's ticker being
reassigned to Array Technologies in 2020 must not be able to cross-contaminate
a lookup, because ticker strings are display metadata only, resolved elsewhere.

Terminal completeness (locked)
-------------------------------
`ReconciliationResult.realized_return_pct` is None whenever ANY economically
material component is unresolved (missing CVR realization, missing successor
price while still trading, a point-in-time cutoff that stopped the chain before
a terminal event) — never just a warning attached to a computed number.
"""
from __future__ import annotations

import math
from csv import DictReader
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Optional

from bve.models.corporate_action import CorporateAction, CorporateActionType


class PriceBasis(str, Enum):
    RAW = "raw"  # actual/nominal price paid and shares held on the entry date — the only supported basis
    SPLIT_ADJUSTED = "split_adjusted"  # NOT supported; see module docstring


def _parse_date(value: str) -> Optional[date]:
    """Parses ISO dates; also accepts a bare "YYYY-MM" (this ledger sometimes only
    has month-level precision for an announcement, e.g. "Melinta filed Chapter 11
    Dec 2019" with no exact day confirmed) by anchoring to the first of the month."""
    value = (value or "").strip()
    if not value or value == "PENDING_VERIFICATION":
        return None
    if len(value) == 7:  # "YYYY-MM"
        value = f"{value}-01"
    return date.fromisoformat(value)


def _parse_float(value: str) -> Optional[float]:
    value = (value or "").strip()
    if not value or value == "PENDING_VERIFICATION":
        return None
    return float(value)


@dataclass(frozen=True)
class ReconciliationResult:
    entry_security_id: str
    entry_shares: float
    entry_price: float
    entry_cost: float
    price_basis: PriceBasis

    terminal_security_id: str
    terminal_shares: float  # nonzero only if chain ended without a terminal event (still trading)
    still_trading: bool
    point_in_time_truncated: bool  # True if an as_of_date cutoff stopped the chain before a terminal event

    cash_proceeds: float = 0.0
    distribution_proceeds: float = 0.0
    cvr_proceeds: float = 0.0
    cash_in_lieu_proceeds: float = 0.0

    actions_applied: list[str] = field(default_factory=list)
    unresolved_components: list[str] = field(default_factory=list)
    entry_timing_warnings: list[str] = field(default_factory=list)

    @property
    def total_proceeds(self) -> float:
        return self.cash_proceeds + self.distribution_proceeds + self.cvr_proceeds + self.cash_in_lieu_proceeds

    @property
    def realized_return_pct(self) -> Optional[float]:
        """None whenever any economically material component is unresolved: still
        trading (no terminal $ figure), a point-in-time cutoff truncated the chain
        before termination, or a required value (e.g. CVR realization) is missing.
        A missing/未-known component must never be silently treated as zero."""
        if self.still_trading or self.point_in_time_truncated or self.unresolved_components:
            return None
        if self.entry_cost == 0:
            return None
        return (self.total_proceeds - self.entry_cost) / self.entry_cost * 100.0


class CorporateActionLedger:
    def __init__(self, actions: list[CorporateAction]):
        by_security: dict[str, list[CorporateAction]] = {}
        for a in actions:
            by_security.setdefault(a.security_id, []).append(a)
        for sid in by_security:
            by_security[sid].sort(key=lambda a: a.action_sequence)
        self._by_security = by_security

    @classmethod
    def load_csv(cls, path: str | Path) -> "CorporateActionLedger":
        actions: list[CorporateAction] = []
        with open(path, newline="", encoding="utf-8") as f:
            for row in DictReader(f):
                actions.append(
                    CorporateAction(
                        security_id=row["security_id"],
                        action_sequence=int(row["action_sequence"]),
                        action_type=CorporateActionType(row["action_type"]),
                        announcement_date=_parse_date(row["announcement_date"]),
                        effective_date=_parse_date(row["effective_date"]),
                        known_at=_parse_date(row.get("known_at", "")),
                        from_security_id=row["from_security_id"],
                        to_security_id=row["to_security_id"],
                        reverse_split_ratio=_parse_float(row["reverse_split_ratio"]),
                        merger_exchange_ratio=_parse_float(row["merger_exchange_ratio"]),
                        cash_in_lieu_price_per_share=_parse_float(row.get("cash_in_lieu_price_per_share", "")),
                        cash_per_share=_parse_float(row["cash_per_share"]),
                        cvr_terms=(row["cvr_terms"] or "").strip() or None,
                        cvr_value_realized=_parse_float(row["cvr_value_realized"]),
                        distribution_per_share=_parse_float(row["distribution_per_share"]),
                        source=(row["source"] or "").strip(),
                        verification_status=(row["verification_status"] or "unverified").strip(),
                    )
                )
        return cls(actions)

    def full_chain_for(self, security_id: str) -> list[CorporateAction]:
        """All actions reachable from `security_id`, in application order, following
        chain-transition actions (mergers, ticker changes, OTC continuations).
        Stops at the first terminal action encountered, or when the next
        security_id has no recorded actions. No point-in-time filtering — full
        hindsight."""
        result: list[CorporateAction] = []
        current = security_id
        seen: set[str] = set()
        while current in self._by_security and current not in seen:
            seen.add(current)
            for action in self._by_security[current]:
                result.append(action)
                if action.is_terminal:
                    return result
                if action.is_chain_transition:
                    current = action.to_security_id
                    break
            else:
                break
        return result

    # Backwards-compatible alias used by earlier pilot tests.
    def chain_for(self, security_id: str) -> list[CorporateAction]:
        return self.full_chain_for(security_id)

    def resolve(
        self,
        entry_security_id: str,
        entry_shares: float,
        entry_price: float,
        *,
        entry_date: Optional[date] = None,
        as_of_date: Optional[date] = None,
        price_basis: PriceBasis = PriceBasis.RAW,
    ) -> ReconciliationResult:
        if price_basis is not PriceBasis.RAW:
            raise ValueError(
                "CorporateActionLedger.resolve() only supports price_basis=PriceBasis.RAW. "
                "Feeding a split/dividend-adjusted price series here would double-adjust "
                "against this ledger's own split/merger actions — re-derive a raw entry "
                "price instead of adjusting this resolver."
            )

        full_chain = self.full_chain_for(entry_security_id)

        # Entry-timing check runs against the full (unfiltered) chain: flags any action
        # where entry_date falls after the public announcement but before the action
        # became effective — per the exit-price conventions this should likely be an
        # EXCLUDED entry (adverse selection / merger-arb, not a clean valuation-dislocation
        # entry), not silently resolved as if bought before the news broke.
        entry_timing_warnings: list[str] = []
        if entry_date is not None:
            for action in full_chain:
                if (
                    action.announcement_date is not None
                    and action.effective_date is not None
                    and action.announcement_date < entry_date < action.effective_date
                ):
                    entry_timing_warnings.append(
                        f"entry_date={entry_date} is after {action.action_type.value} was announced "
                        f"({action.announcement_date}) but before it became effective ({action.effective_date}) "
                        "-- per exit-price convention this entry should likely be EXCLUDED, not resolved "
                        "as a clean pre-announcement entry"
                    )

        # Point-in-time filter: walk the full chain but stop at the first action whose
        # terms weren't yet knowable as of as_of_date. This must stop the walk entirely
        # (not skip-and-continue) -- a later action's known_at being <= as_of_date can't
        # rescue an earlier, still-unresolved action.
        chain = full_chain
        point_in_time_truncated = False
        if as_of_date is not None:
            truncated: list[CorporateAction] = []
            for action in full_chain:
                if action.known_at is None or action.known_at > as_of_date:
                    point_in_time_truncated = True
                    break
                truncated.append(action)
            chain = truncated

        shares = entry_shares
        current_sid = entry_security_id
        cash = 0.0
        distribution = 0.0
        cvr = 0.0
        cash_in_lieu = 0.0
        applied: list[str] = []
        unresolved: list[str] = []
        still_trading = True

        for action in chain:
            t = action.action_type
            if t in (CorporateActionType.REVERSE_SPLIT, CorporateActionType.FORWARD_SPLIT):
                shares *= action.reverse_split_ratio  # type: ignore[operator]
                applied.append(f"{t.value}@{action.effective_date} ratio={action.reverse_split_ratio} -> {shares:.4f} shares")
            elif t in (CorporateActionType.STOCK_MERGER, CorporateActionType.CASH_AND_STOCK_MERGER):
                exact_new_shares = shares * action.merger_exchange_ratio  # type: ignore[operator]
                if action.cash_in_lieu_price_per_share is not None:
                    whole_shares = math.floor(exact_new_shares + 1e-9)
                    fractional_remainder = exact_new_shares - whole_shares
                    lieu = fractional_remainder * action.cash_in_lieu_price_per_share
                    cash_in_lieu += lieu
                    applied.append(
                        f"cash_in_lieu={lieu:.4f} for fractional remainder {fractional_remainder:.6f} shares "
                        f"@ {action.cash_in_lieu_price_per_share}/share"
                    )
                    new_shares = float(whole_shares)
                else:
                    new_shares = exact_new_shares
                if t == CorporateActionType.CASH_AND_STOCK_MERGER:
                    cash += shares * action.cash_per_share  # type: ignore[operator]
                    applied.append(
                        f"{t.value}@{action.effective_date} cash_per_share={action.cash_per_share} on {shares:.4f} shares "
                        f"+ stock ratio={action.merger_exchange_ratio} -> {new_shares:.4f} shares of {action.to_security_id}"
                    )
                else:
                    applied.append(
                        f"{t.value}@{action.effective_date} ratio={action.merger_exchange_ratio} "
                        f"-> {new_shares:.4f} shares of {action.to_security_id}"
                    )
                shares = new_shares
                current_sid = action.to_security_id
            elif t in (CorporateActionType.TICKER_CHANGE, CorporateActionType.EXCHANGE_DELISTING_CONTINUED_OTC):
                current_sid = action.to_security_id
                applied.append(f"{t.value}@{action.effective_date} -> {current_sid} (no share/value change)")
            elif t == CorporateActionType.CASH_MERGER:
                cash += shares * action.cash_per_share  # type: ignore[operator]
                applied.append(f"{t.value}@{action.effective_date} cash_per_share={action.cash_per_share} on {shares:.4f} shares")
                shares = 0.0
                still_trading = False
            elif t == CorporateActionType.CASH_PLUS_CVR_MERGER:
                cash += shares * action.cash_per_share  # type: ignore[operator]
                applied.append(f"{t.value}@{action.effective_date} cash_per_share={action.cash_per_share} on {shares:.4f} shares")
                if action.cvr_value_realized is not None:
                    cvr += shares * action.cvr_value_realized
                    applied.append(f"cvr_value_realized={action.cvr_value_realized} on {shares:.4f} shares")
                else:
                    unresolved.append(
                        f"cvr_value_realized unresolved for {action.security_id} ({action.cvr_terms or 'terms unknown'})"
                    )
                shares = 0.0
                still_trading = False
            elif t in (CorporateActionType.BANKRUPTCY_RECOVERY, CorporateActionType.LIQUIDATION_DISTRIBUTION):
                if action.distribution_per_share is not None:
                    distribution += shares * action.distribution_per_share
                    applied.append(
                        f"{t.value}@{action.effective_date} distribution_per_share={action.distribution_per_share} on {shares:.4f} shares"
                    )
                else:
                    unresolved.append(
                        f"distribution_per_share unresolved for {action.security_id} ({t.value}@{action.effective_date})"
                    )
                    applied.append(f"{t.value}@{action.effective_date} distribution_per_share=UNRESOLVED on {shares:.4f} shares")
                shares = 0.0
                still_trading = False

        return ReconciliationResult(
            entry_security_id=entry_security_id,
            entry_shares=entry_shares,
            entry_price=entry_price,
            entry_cost=entry_shares * entry_price,
            price_basis=price_basis,
            terminal_security_id=current_sid,
            terminal_shares=shares if still_trading else 0.0,
            still_trading=still_trading,
            point_in_time_truncated=point_in_time_truncated,
            cash_proceeds=cash,
            distribution_proceeds=distribution,
            cvr_proceeds=cvr,
            cash_in_lieu_proceeds=cash_in_lieu,
            actions_applied=applied,
            unresolved_components=unresolved,
            entry_timing_warnings=entry_timing_warnings,
        )
