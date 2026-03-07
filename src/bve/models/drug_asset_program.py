"""
DrugAssetProgram — typed, immutable container bundling all inputs for a single drug program.

Design
------
This is a pure data container with no computation logic.  All valuation
engines (ProbabilityModel, RevenueModel, CostModel, RNPVModel) receive their
inputs from this container rather than through ad-hoc dicts or direct engine
coupling.

DrugAssetProgram is frozen (Pydantic ConfigDict frozen=True).  Once assembled,
its fields cannot be reassigned.  Use model_copy(update=...) to derive a
modified program from an existing one.

Components
----------
asset           : Asset entity (id, modality, discount_rate, royalty_rate …)
trials          : ClinicalTrial objects for this program
market_model    : Commercial revenue model (TAM/patient/LOT modes)
pos_adjusters   : Per-phase POSAdjusters (optional first POS layer)
design_features : Per-phase TrialDesignFeatureSet (optional second POS layer)
commercial_plan : CommercialPlan with the LOE erosion profile (see below)

CommercialPlan — three distinct states
---------------------------------------
"unset"      CommercialPlan() bare constructor.  loe_profile=None, loe_source="unset".
             Signals: nobody configured this explicitly.
             Engine behaviour: fall back to AssumptionsLoader.loe_erosion_profile(modality).

"suppressed" CommercialPlan.no_loe().  loe_profile=None, loe_source="suppressed".
             Signals: no post-LOE tail is intentionally modelled.
             Engine behaviour: revenue stops exactly at patent_life_years.

"loaded"     CommercialPlan.from_modality(m).  loe_profile=dict(...), loe_source="modality:<m>".
             Signals: an explicit profile was fetched from the assumptions layer.
             Engine behaviour: three LOE tail years are appended to the revenue curve.

These three states are behaviourally different and must not be conflated.
CommercialPlan validates that loe_profile is not set when loe_source="unset" — that
inconsistent combination would cause the engine to silently ignore the profile.

Invariant
---------
market_model.asset_id must equal asset.id.  Checked at construction;
raises ValueError on mismatch.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bve.entities.asset import Asset
from bve.entities.trial import ClinicalTrial, TrialPhase
from bve.models.deal_economics import DealEconomics
from bve.models.market_model import MarketModel
from bve.models.pos_model import POSAdjusters
from bve.models.trial_design_features import TrialDesignFeatureSet


# ---------------------------------------------------------------------------
# CommercialPlan
# ---------------------------------------------------------------------------

class CommercialPlan(BaseModel):
    """
    Commercial assumptions that supplement MarketModel.

    Three states with distinct semantics — see module docstring.

    loe_profile : dict when loaded, None when suppressed or unset.
    loe_source  : "unset" | "suppressed" | "modality:<name>"
        "unset"     — bare constructor; engine falls back to AssumptionsLoader.
        "suppressed"— no_loe() was called; engine applies no tail.
        "modality:*"— from_modality() loaded a specific profile.

    Do not pass loe_profile=dict(...) with loe_source="unset" — the engine
    would ignore the profile and fetch from AssumptionsLoader instead.  That
    combination is rejected at construction.
    """
    loe_profile: Optional[dict] = None
    loe_source: str = "unset"

    @model_validator(mode="after")
    def _check_source_consistency(self) -> "CommercialPlan":
        if self.loe_profile is not None and self.loe_source == "unset":
            raise ValueError(
                "loe_profile is set but loe_source='unset'. "
                "The engine would ignore the profile and fall back to AssumptionsLoader. "
                "Use CommercialPlan.from_modality() or set loe_source explicitly "
                "(e.g. loe_source='custom')."
            )
        return self

    # -- State queries -------------------------------------------------------

    @property
    def is_unset(self) -> bool:
        """True when nobody explicitly configured this plan (bare constructor)."""
        return self.loe_source == "unset"

    @property
    def is_suppressed(self) -> bool:
        """True when LOE tail was explicitly turned off via no_loe()."""
        return self.loe_source == "suppressed"

    @property
    def is_loaded(self) -> bool:
        """True when a profile was explicitly loaded (from_modality or custom)."""
        return not self.is_unset and not self.is_suppressed

    # -- Factories -----------------------------------------------------------

    @classmethod
    def from_modality(cls, modality: str) -> "CommercialPlan":
        """
        Load the LOE erosion profile for a modality from AssumptionsLoader.

        If the modality is not found in the assumptions YAML, AssumptionsLoader
        emits a UserWarning and falls back to 'other'.  The loe_source records
        the *requested* modality so the fallback is visible on inspection.
        """
        from bve.config.assumptions_loader import AssumptionsLoader
        profile = AssumptionsLoader.get().loe_erosion_profile(modality)
        return cls(loe_profile=dict(profile), loe_source=f"modality:{modality}")

    @classmethod
    def no_loe(cls) -> "CommercialPlan":
        """
        Explicitly no post-LOE tail.

        Revenue stops at patent_life_years.  This is distinct from an unset
        plan (loe_source='unset') which causes the engine to fetch a default.
        """
        return cls(loe_profile=None, loe_source="suppressed")


# ---------------------------------------------------------------------------
# DrugAssetProgram
# ---------------------------------------------------------------------------

class DrugAssetProgram(BaseModel):
    """
    Typed, immutable container bundling all program-level inputs for a single drug asset.

    Frozen: fields cannot be reassigned after construction.  Use model_copy(update=...)
    to derive a modified program.

    Parameters
    ----------
    asset           : Asset entity.
    trials          : All ClinicalTrial objects for this program.  The engine
                      filters to trials whose asset_id matches asset.id.
    market_model    : Commercial revenue model; must share asset_id with asset.
    pos_adjusters   : {TrialPhase: POSAdjusters} — optional first POS layer.
                      When non-empty and apply_pos_model=True, the engine
                      overrides trial.success_probability.
    design_features : {TrialPhase: TrialDesignFeatureSet} — optional second
                      POS layer applied after pos_adjusters.
    commercial_plan : CommercialPlan describing the LOE profile state.
                      Default is CommercialPlan() with loe_source='unset',
                      which causes the engine to fetch the profile at run time.
                      Prefer DrugAssetProgram.build() which sets this explicitly.

    Invariant: market_model.asset_id == asset.id (raises ValueError on mismatch).
    """
    model_config = ConfigDict(frozen=True)

    asset: Asset
    trials: list[ClinicalTrial]
    market_model: MarketModel
    pos_adjusters: dict[TrialPhase, POSAdjusters] = Field(default_factory=dict)
    design_features: dict[TrialPhase, TrialDesignFeatureSet] = Field(default_factory=dict)
    commercial_plan: CommercialPlan = Field(default_factory=CommercialPlan)
    deal_economics: DealEconomics = Field(default_factory=DealEconomics)

    @model_validator(mode="after")
    def _validate_asset_id_consistency(self) -> "DrugAssetProgram":
        if self.market_model.asset_id != self.asset.id:
            raise ValueError(
                f"market_model.asset_id={self.market_model.asset_id!r} "
                f"does not match asset.id={self.asset.id!r}"
            )
        return self

    @property
    def active_trials(self) -> list[ClinicalTrial]:
        """Trials filtered to this asset's ID (same filter ValuationEngine applies)."""
        return [t for t in self.trials if t.asset_id == self.asset.id]

    # ------------------------------------------------------------------
    # Alternate constructor
    # ------------------------------------------------------------------

    @classmethod
    def build(
        cls,
        asset: Asset,
        trials: list[ClinicalTrial],
        market_model: MarketModel,
        pos_adjusters: Optional[dict] = None,
        design_features: Optional[dict] = None,
        load_loe: bool = True,
        deal_economics: Optional[DealEconomics] = None,
    ) -> "DrugAssetProgram":
        """
        Build a DrugAssetProgram with an explicit CommercialPlan.

        Parameters
        ----------
        load_loe : bool
            True (default): fetch the LOE profile from AssumptionsLoader using
            asset.modality, storing it with loe_source='modality:<name>'.
            If the modality is unknown, AssumptionsLoader warns and falls back to
            'other' — the UserWarning is emitted here, before run().

            False: explicitly suppress the LOE tail (loe_source='suppressed').
            Revenue will stop at patent_life_years with no tail appended.

        In both cases the LOE state is explicit and inspectable on
        program.commercial_plan before run() is called.
        """
        commercial_plan = (
            CommercialPlan.from_modality(asset.modality.value)
            if load_loe
            else CommercialPlan.no_loe()
        )
        return cls(
            asset=asset,
            trials=trials,
            market_model=market_model,
            pos_adjusters=pos_adjusters or {},
            design_features=design_features or {},
            commercial_plan=commercial_plan,
            deal_economics=deal_economics or DealEconomics(),
        )
