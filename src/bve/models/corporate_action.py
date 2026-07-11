"""CorporateAction — one atomic, dated event in a security's ownership chain.

Design boundary
---------------
A single scalar "share_conversion_ratio" per security cannot represent a name like
CEMP: reverse split -> renamed/continued as MLNT -> MLNT files bankruptcy -> $0
recovery. Each of those is a distinct dated event with its own source and its own
verification confidence, and they must be applied in order, not collapsed into one
number. CorporateAction is the atomic record; CorporateActionLedger (in
bve.analysis.corporate_action_ledger) chains them per security and resolves
terminal proceeds.

Reverse/forward split ratios and merger exchange ratios are both expressed as
"new units per one old unit" (e.g. a 1-for-10 reverse split is 0.10; a merger
where each old share becomes 1.4750 new shares is 1.4750). This keeps
`shares *= ratio` valid for every ratio-bearing action type.

Two dates, not one
-------------------
`effective_date` is when shareholders were actually affected (the split ratio
applied, the deal closed, the plan became effective). `known_at` is when the
terms became knowable/public (e.g. an S-4 or 8-K was filed, a plan was
confirmed, a CVR milestone was resolved and disclosed). These are often the
same day for a routine split, but diverge materially for a CVR ("known_at" is
whenever the milestone outcome is later disclosed — years after
`effective_date`, which is deal close) and for any recovery figure that is only
confirmed well after a bankruptcy filing. `known_at=None` means "not yet known"
— the resolver's point-in-time mode (CorporateActionLedger.resolve(..., as_of_date=...))
must never apply an action whose terms weren't yet knowable as of that date.
"""
from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, model_validator


class CorporateActionType(str, Enum):
    REVERSE_SPLIT = "reverse_split"
    FORWARD_SPLIT = "forward_split"
    STOCK_MERGER = "stock_merger"  # stock-for-stock exchange into a new/continuing security
    CASH_MERGER = "cash_merger"  # all-cash acquisition, terminal
    CASH_PLUS_CVR_MERGER = "cash_plus_cvr_merger"  # cash + contingent value right, terminal
    CASH_AND_STOCK_MERGER = "cash_and_stock_merger"  # mixed consideration; continues chain AND pays cash
    TICKER_CHANGE = "ticker_change"  # relabeling only; no share count or value change
    EXCHANGE_DELISTING_CONTINUED_OTC = "exchange_delisting_continued_otc"  # venue change only; not an exit
    BANKRUPTCY_RECOVERY = "bankruptcy_recovery"  # terminal; distribution_per_share often 0
    LIQUIDATION_DISTRIBUTION = "liquidation_distribution"  # terminal wind-down distribution


# Action types that end the chain for the shares involved (no further actions apply to them).
TERMINAL_ACTION_TYPES = frozenset(
    {
        CorporateActionType.CASH_MERGER,
        CorporateActionType.CASH_PLUS_CVR_MERGER,
        CorporateActionType.BANKRUPTCY_RECOVERY,
        CorporateActionType.LIQUIDATION_DISTRIBUTION,
    }
)

# Action types that carry the position to a different security_id (chain continues there).
# CASH_AND_STOCK_MERGER is here, not in TERMINAL_ACTION_TYPES: the cash leg is realized
# immediately but the stock leg continues the chain under to_security_id.
CHAIN_TRANSITION_ACTION_TYPES = frozenset(
    {
        CorporateActionType.STOCK_MERGER,
        CorporateActionType.CASH_AND_STOCK_MERGER,
        CorporateActionType.TICKER_CHANGE,
        CorporateActionType.EXCHANGE_DELISTING_CONTINUED_OTC,
    }
)


class CorporateAction(BaseModel):
    """One row of a security's corporate-action ledger.

    `security_id` is the permanent id the action is filed under (matches
    `permanent_security_id` in failed_delisted_biotech_candidates.csv, e.g. "SEC-CEMP").
    `action_sequence` orders multiple actions filed under the same security_id, including
    multiple actions effective on the same calendar date (e.g. a same-day split then rename).
    """

    model_config = ConfigDict(frozen=True)

    security_id: str
    action_sequence: int
    action_type: CorporateActionType
    announcement_date: Optional[date] = None
    effective_date: Optional[date] = None
    known_at: Optional[date] = None  # None = terms not yet knowable/disclosed
    from_security_id: str
    to_security_id: str

    reverse_split_ratio: Optional[float] = None  # new shares per old share, e.g. 0.10
    merger_exchange_ratio: Optional[float] = None  # new shares per old share
    cash_in_lieu_price_per_share: Optional[float] = None  # price used to cash out the fractional remainder
    cash_per_share: Optional[float] = None
    cvr_terms: Optional[str] = None  # free-text description of contingent terms
    cvr_value_realized: Optional[float] = None  # $/share actually realized; None = unresolved
    distribution_per_share: Optional[float] = None  # bankruptcy/liquidation payout per share

    source: str = ""
    verification_status: str = "unverified"  # "verified" | "unverified" | "quarantined"

    @model_validator(mode="after")
    def _check_required_fields_for_type(self) -> "CorporateAction":
        t = self.action_type
        if t in (CorporateActionType.REVERSE_SPLIT, CorporateActionType.FORWARD_SPLIT):
            if self.reverse_split_ratio is None:
                raise ValueError(f"{t.value} action requires reverse_split_ratio")
        if t in (CorporateActionType.STOCK_MERGER, CorporateActionType.CASH_AND_STOCK_MERGER):
            if self.merger_exchange_ratio is None:
                raise ValueError(f"{t.value} action requires merger_exchange_ratio")
        if t in (
            CorporateActionType.CASH_MERGER,
            CorporateActionType.CASH_PLUS_CVR_MERGER,
            CorporateActionType.CASH_AND_STOCK_MERGER,
        ):
            if self.cash_per_share is None:
                raise ValueError(f"{t.value} action requires cash_per_share")
        if t in (CorporateActionType.BANKRUPTCY_RECOVERY, CorporateActionType.LIQUIDATION_DISTRIBUTION):
            if self.distribution_per_share is None:
                raise ValueError(f"{t.value} action requires distribution_per_share (use 0.0 for confirmed wipeout)")
        return self

    @property
    def is_terminal(self) -> bool:
        return self.action_type in TERMINAL_ACTION_TYPES

    @property
    def is_chain_transition(self) -> bool:
        return self.action_type in CHAIN_TRANSITION_ACTION_TYPES and self.to_security_id != self.security_id
