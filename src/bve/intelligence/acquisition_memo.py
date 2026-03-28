"""Deterministic acquisition memo generation on top of acquirer-fit output."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from bve.intelligence.acquirer_fit import (
    AcquirerFitEngine,
    AcquirerFitIntegrationConfig,
    AcquirerFitResult,
    AcquirerFitRow,
)
from bve.intelligence.acquirer_profiles import AcquirerProfileLoader
from bve.intelligence.knowledge_layer import MemoRecord, SourceTrace
from bve.models.deal_economics import DealEconomics, Milestone, MilestoneDirection, MilestoneTrigger
from bve.models.drug_asset_program import DrugAssetProgram
from bve.reporting.memo_generator import generate_memo
from bve.valuation.valuation_engine import ValuationEngine


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IndicativeDealTerms(BaseModel):
    """Indicative acquisition structure expressed through DealEconomics."""

    structure_type: str
    reference_enterprise_value_millions: float
    upfront_millions: float
    milestone_total_millions: float
    cdev_cost_share: float
    royalty_rate: float
    milestones: list[Milestone] = Field(default_factory=list)
    deal_economics: DealEconomics


class AcquisitionMemo(BaseModel):
    """Persistable acquisition memo artifact."""

    memo_id: str
    asset_id: str
    company_id: str | None = None
    acquirer_id: str
    acquirer_name: str
    generated_at: datetime
    fit_score: float
    passes_hard_filters: bool
    hard_fail_reasons: list[str] = Field(default_factory=list)
    standalone_rnpv_millions: float
    post_deal_rnpv_millions: float
    present_value_of_terms_millions: float
    indicative_terms: IndicativeDealTerms
    rendered_markdown: str
    source_trace: SourceTrace = Field(
        default_factory=lambda: SourceTrace(
            source_type="acquisition_memo_generator",
            source_ref="deterministic",
        )
    )

    def to_memo_record(self) -> MemoRecord:
        open_questions = [f"Resolve hard fail: {reason}" for reason in self.hard_fail_reasons]
        return MemoRecord(
            id=self.memo_id,
            company_id=self.company_id,
            asset_id=self.asset_id,
            title=f"Acquisition Memo — {self.acquirer_name} / {self.asset_id}",
            memo_type="acquisition_memo",
            content_markdown=self.rendered_markdown,
            created_at=self.generated_at,
            source_signal_ids=[],
            source_run_ids=[],
            referenced_event_ids=[],
            referenced_diff_ids=[],
            referenced_review_ids=[],
            open_questions=open_questions,
            source_trace=self.source_trace,
        )


class AcquisitionMemoGenerator:
    """Generate per-target acquisition memos using existing memo/reporting paths."""

    def __init__(
        self,
        *,
        fit_engine: Optional[AcquirerFitEngine] = None,
        knowledge_store=None,
        context_provider=None,
        integration_config: Optional[AcquirerFitIntegrationConfig] = None,
    ) -> None:
        self.fit_engine = fit_engine or AcquirerFitEngine(
            knowledge_store=knowledge_store,
            context_provider=context_provider,
            integration_config=integration_config,
        )
        self.knowledge = knowledge_store

    def generate_for_watchlist(
        self,
        watchlist_or_config,
        *,
        acquirer_id: str,
        snapshot_date: Optional[date] = None,
        top_n: Optional[int] = None,
        persist: bool = False,
    ) -> list[AcquisitionMemo]:
        watchlist = list(getattr(watchlist_or_config, "watchlist", watchlist_or_config))
        fit_result = self.fit_engine.screen_watchlist(
            watchlist,
            acquirer_id=acquirer_id,
            snapshot_date=snapshot_date,
            top_n=top_n,
        )
        return self.generate_from_fit_result(
            watchlist,
            fit_result=fit_result,
            persist=persist,
        )

    def generate_from_fit_result(
        self,
        watchlist: list[object],
        *,
        fit_result: AcquirerFitResult,
        persist: bool = False,
    ) -> list[AcquisitionMemo]:
        asset_by_id = {getattr(asset, "asset_id"): asset for asset in watchlist}
        memos = [
            self.generate_for_target(
                asset=asset_by_id[row.asset_id],
                fit_row=row,
                persist=persist,
            )
            for row in fit_result.rows
        ]
        return memos

    def generate_for_target(
        self,
        *,
        asset: object,
        fit_row: AcquirerFitRow,
        persist: bool = False,
    ) -> AcquisitionMemo:
        context = self.fit_engine.acquisition_screener._get_context(asset)
        acquirer = AcquirerProfileLoader.get_acquirer(
            self.fit_engine.integration_config.acquirer_profiles_path,
            fit_row.acquirer_id,
        )

        standalone_output = self._run_standalone_output(context)
        indicative_terms = self.plan_terms(fit_row)
        post_deal_output = self._run_deal_adjusted_output(
            context,
            deal_economics=indicative_terms.deal_economics,
        )

        base_markdown = generate_memo(standalone_output, memo_type="bd")
        rendered_markdown = base_markdown.rstrip() + "\n\n" + self._render_addendum(
            fit_row=fit_row,
            acquirer_name=acquirer.company_name,
            indicative_terms=indicative_terms,
            standalone_output=standalone_output,
            post_deal_output=post_deal_output,
        )

        memo = AcquisitionMemo(
            memo_id=self._memo_id(
                asset_id=fit_row.asset_id,
                company_id=fit_row.company_id,
                acquirer_id=fit_row.acquirer_id,
                generated_at=_utcnow(),
            ),
            asset_id=fit_row.asset_id,
            company_id=fit_row.company_id,
            acquirer_id=fit_row.acquirer_id,
            acquirer_name=acquirer.company_name,
            generated_at=_utcnow(),
            fit_score=fit_row.fit_score,
            passes_hard_filters=fit_row.passes_hard_filters,
            hard_fail_reasons=list(fit_row.hard_fail_reasons),
            standalone_rnpv_millions=round(float(standalone_output.rnpv.rnpv_millions), 6),
            post_deal_rnpv_millions=round(float(post_deal_output.rnpv.rnpv_millions), 6),
            present_value_of_terms_millions=round(
                float(standalone_output.rnpv.rnpv_millions)
                - float(post_deal_output.rnpv.rnpv_millions),
                6,
            ),
            indicative_terms=indicative_terms,
            rendered_markdown=rendered_markdown,
        )
        if persist:
            if self.knowledge is None:
                raise ValueError("knowledge_store is required when persist=True")
            self.knowledge.add_memo(memo.to_memo_record())
        return memo

    @staticmethod
    def plan_terms(fit_row: AcquirerFitRow) -> IndicativeDealTerms:
        reference_value = float(fit_row.enterprise_value_millions or 0.0)
        stage = (fit_row.stage or "").strip().lower()

        if stage == "approved":
            upfront_pct = 1.0
            structure_type = "full_acquisition_cash"
            milestones: list[Milestone] = []
        elif stage == "nda_bla":
            upfront_pct = 0.85
            structure_type = "full_acquisition_with_approval_cvr"
            milestones = [
                Milestone(
                    description="Regulatory approval CVR",
                    amount_millions=round(reference_value * 0.15, 6),
                    trigger=MilestoneTrigger.APPROVAL,
                    direction=MilestoneDirection.PAYABLE,
                )
            ]
        elif stage == "phase_3":
            upfront_pct = 0.70 if fit_row.fit_score >= 0.75 else 0.60
            remaining = max(reference_value - (reference_value * upfront_pct), 0.0)
            structure_type = "full_acquisition_with_contingent_approval_value"
            milestones = []
            if remaining > 0:
                milestones.append(
                    Milestone(
                        description="Approval milestone",
                        amount_millions=round(remaining * 0.70, 6),
                        trigger=MilestoneTrigger.APPROVAL,
                        direction=MilestoneDirection.PAYABLE,
                    )
                )
                milestones.append(
                    Milestone(
                        description="First-sale milestone",
                        amount_millions=round(remaining * 0.30, 6),
                        trigger=MilestoneTrigger.FIRST_SALE,
                        direction=MilestoneDirection.PAYABLE,
                    )
                )
        else:
            upfront_pct = 0.40 if stage == "phase_2" else 0.30
            remaining = max(reference_value - (reference_value * upfront_pct), 0.0)
            structure_type = "structured_acquisition_with_development_milestones"
            milestones = []
            if remaining > 0:
                milestones.append(
                    Milestone(
                        description="Phase 2 success milestone",
                        amount_millions=round(remaining * 0.35, 6),
                        trigger=MilestoneTrigger.PHASE_SUCCESS,
                        trigger_phase="phase_2",
                        direction=MilestoneDirection.PAYABLE,
                    )
                )
                milestones.append(
                    Milestone(
                        description="Approval milestone",
                        amount_millions=round(remaining * 0.45, 6),
                        trigger=MilestoneTrigger.APPROVAL,
                        direction=MilestoneDirection.PAYABLE,
                    )
                )
                milestones.append(
                    Milestone(
                        description="First-sale milestone",
                        amount_millions=round(remaining * 0.20, 6),
                        trigger=MilestoneTrigger.FIRST_SALE,
                        direction=MilestoneDirection.PAYABLE,
                    )
                )

        upfront_millions = round(reference_value * upfront_pct, 6)
        milestone_total = round(sum(m.amount_millions for m in milestones), 6)
        deal_economics = DealEconomics(
            upfront_cost_millions=upfront_millions,
            royalty_rate=0.0,
            cdev_cost_share=1.0,
            milestones=milestones,
        )
        return IndicativeDealTerms(
            structure_type=structure_type,
            reference_enterprise_value_millions=round(reference_value, 6),
            upfront_millions=upfront_millions,
            milestone_total_millions=milestone_total,
            cdev_cost_share=1.0,
            royalty_rate=0.0,
            milestones=milestones,
            deal_economics=deal_economics,
        )

    @staticmethod
    def _run_standalone_output(context) -> object:
        engine = ValuationEngine(
            context.asset,
            context.company,
            context.trials,
            context.market_model,
            pos_adjusters=context.pos_adjusters,
            design_adjusters=context.design_adjusters,
            apply_pos_model=context.apply_pos_model,
            apply_design_model=context.apply_design_model,
        )
        return engine.run()

    @staticmethod
    def _run_deal_adjusted_output(context, *, deal_economics: DealEconomics) -> object:
        program = DrugAssetProgram.build(
            context.asset,
            context.trials,
            context.market_model,
            pos_adjusters=context.pos_adjusters,
            design_features=context.design_adjusters,
            deal_economics=deal_economics,
        )
        engine = ValuationEngine.from_program(
            program,
            context.company,
            apply_pos_model=context.apply_pos_model,
            apply_design_model=context.apply_design_model,
        )
        return engine.run()

    @staticmethod
    def _memo_id(
        *,
        asset_id: str,
        company_id: Optional[str],
        acquirer_id: str,
        generated_at: datetime,
    ) -> str:
        seed = "|".join([asset_id, company_id or "", acquirer_id, generated_at.date().isoformat()])
        return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))

    @staticmethod
    def _render_addendum(
        *,
        fit_row: AcquirerFitRow,
        acquirer_name: str,
        indicative_terms: IndicativeDealTerms,
        standalone_output,
        post_deal_output,
    ) -> str:
        pv_of_terms = float(standalone_output.rnpv.rnpv_millions) - float(post_deal_output.rnpv.rnpv_millions)
        lines = [
            "---",
            "",
            "## 9. Acquirer Fit Addendum",
            "",
            "### Strategic Fit",
            f"- Acquirer: **{acquirer_name}** (`{fit_row.acquirer_id}`)",
            f"- Fit score: **{fit_row.fit_score:.3f}** "
            f"({'passes hard filters' if fit_row.passes_hard_filters else 'hard filters failed'})",
            f"- Therapeutic gap match: `{fit_row.matched_therapeutic_gap or 'none'}`",
            f"- Modality match: `{fit_row.matched_modality or 'none'}`",
            f"- Priority overlap: {', '.join(fit_row.matched_priorities) if fit_row.matched_priorities else 'none'}",
            f"- Valuation context: `{fit_row.valuation_source}`",
            f"- Budget headroom: "
            f"{_fmt_millions(fit_row.budget_headroom_millions) if fit_row.budget_headroom_millions is not None else 'n/a'}",
        ]
        if fit_row.hard_fail_reasons:
            lines.append(f"- Hard fails: {', '.join(fit_row.hard_fail_reasons)}")

        lines.extend(
            [
                "",
                "### Indicative Deal Structure",
                f"- Structure: `{indicative_terms.structure_type}`",
                f"- Reference enterprise value: {_fmt_millions(indicative_terms.reference_enterprise_value_millions)}",
                f"- Indicative upfront: {_fmt_millions(indicative_terms.upfront_millions)}",
                f"- Potential milestones: {_fmt_millions(indicative_terms.milestone_total_millions)}",
                f"- Royalty rate: {indicative_terms.royalty_rate:.0%}",
                f"- Clinical cost share: {indicative_terms.cdev_cost_share:.0%}",
            ]
        )
        if indicative_terms.milestones:
            lines.append("- Milestone schedule:")
            for milestone in indicative_terms.milestones:
                trigger = milestone.trigger.value
                if milestone.trigger_phase:
                    trigger = f"{trigger}:{milestone.trigger_phase}"
                lines.append(
                    f"  - {milestone.description}: {_fmt_millions(milestone.amount_millions)} "
                    f"on `{trigger}`"
                )

        lines.extend(
            [
                "",
                "### Deal Economics Snapshot",
                f"- Standalone asset rNPV: {_fmt_millions(float(standalone_output.rnpv.rnpv_millions))}",
                f"- Post-deal asset rNPV: {_fmt_millions(float(post_deal_output.rnpv.rnpv_millions))}",
                f"- PV of indicative consideration: {_fmt_millions(pv_of_terms)}",
                f"- Explanation: {fit_row.explanation}",
            ]
        )
        return "\n".join(lines)


def _fmt_millions(value: float) -> str:
    return f"${value:,.1f}M"
