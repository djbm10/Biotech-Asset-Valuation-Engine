"""Deterministic investment memo generator."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, Field

from bve.intelligence.knowledge_layer import (
    DossierRecord,
    KnowledgeStore,
    MemoRecord,
    SourceTrace,
)
from bve.intelligence.research_report import ResearchReportGenerator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


_TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "reporting" / "templates"
_TEMPLATE_NAME = "investment_memo.md.j2"
_MEMO_VERSION = "v1.0"
_MODEL_VERSION = "deterministic-investment-memo-1.0"


class InvestmentMemo(BaseModel):
    """Persistable investment memo artifact."""

    memo_id: str
    asset_id: str
    company_id: Optional[str] = None
    memo_version: str = _MEMO_VERSION
    model_version: str = _MODEL_VERSION
    generated_at: datetime
    investment_thesis: str
    bull_case: str
    bear_case: str
    catalysts: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    valuation_summary: str
    rendered_markdown: str
    cited_report_ids: list[str] = Field(default_factory=list)
    cited_event_ids: list[str] = Field(default_factory=list)
    cited_run_ids: list[str] = Field(default_factory=list)
    source_trace: SourceTrace = Field(
        default_factory=lambda: SourceTrace(
            source_type="investment_memo_agent",
            source_ref="deterministic",
        )
    )

    def to_memo_record(self) -> MemoRecord:
        return MemoRecord(
            id=self.memo_id,
            company_id=self.company_id,
            asset_id=self.asset_id,
            title=f"Investment Memo — {self.asset_id}",
            memo_type="investment_memo",
            content_markdown=self.rendered_markdown,
            created_at=self.generated_at,
            source_signal_ids=[],
            source_run_ids=list(self.cited_run_ids),
            referenced_event_ids=list(self.cited_event_ids),
            referenced_diff_ids=list(self.cited_run_ids),
            referenced_review_ids=[],
            open_questions=[],
            source_trace=self.source_trace,
        )


class InvestmentMemoContext(BaseModel):
    memo_id: str
    asset_id: str
    company_id: Optional[str]
    memo_version: str
    model_version: str
    generated_at: datetime
    investment_thesis: str
    bull_case: str
    bear_case: str
    catalysts: list[str]
    risks: list[str]
    valuation_summary: str
    cited_report_ids: list[str]
    cited_event_ids: list[str]
    cited_run_ids: list[str]


class InvestmentMemoAgent:
    """Assembly-first, render-second memo generator."""

    def __init__(
        self,
        *,
        template_dir: Optional[Path] = None,
        template_name: str = _TEMPLATE_NAME,
    ) -> None:
        self.template_dir = template_dir or _TEMPLATE_DIR
        self.template_name = template_name

    def assemble_context(
        self,
        store: KnowledgeStore,
        *,
        asset_id: str,
        company_id: Optional[str] = None,
        generated_at: Optional[datetime] = None,
    ) -> InvestmentMemoContext:
        generated_at = generated_at or _utcnow()
        dossier = self._load_or_build_dossier(store, asset_id=asset_id, company_id=company_id)
        report = self._load_or_generate_report(
            store,
            asset_id=asset_id,
            company_id=company_id,
            generated_at=generated_at,
        )
        recent_events = store.get_events(company_id=company_id, asset_id=asset_id, limit=5)
        recent_diffs = store.get_valuation_diffs(company_id=company_id, asset_id=asset_id, limit=5)
        recent_reviews = store.get_review_decisions(company_id=company_id, asset_id=asset_id, limit=5)

        cited_report_ids: list[str] = []
        report_id = report.get("report_id") or report.get("id")
        if report_id:
            cited_report_ids.append(str(report_id))

        cited_event_ids = [evt.id for evt in recent_events]
        cited_run_ids = [d.run_id for d in recent_diffs]

        investment_thesis = str(
            report.get("investment_thesis")
            or f"Base thesis tracks {asset_id} with evidence-led valuation updates."
        )
        bull_case = self._bull_case(report=report, dossier=dossier, diffs=recent_diffs)
        bear_case = self._bear_case(report=report, reviews=recent_reviews)
        catalysts = self._catalysts(recent_events)
        risks = self._risks(report=report, reviews=recent_reviews)
        valuation_summary = self._valuation_summary(dossier=dossier, diffs=recent_diffs)

        memo_id = self._memo_id(
            asset_id=asset_id,
            company_id=company_id,
            generated_at=generated_at,
            report_ids=cited_report_ids,
        )
        return InvestmentMemoContext(
            memo_id=memo_id,
            asset_id=asset_id,
            company_id=company_id,
            memo_version=_MEMO_VERSION,
            model_version=_MODEL_VERSION,
            generated_at=generated_at,
            investment_thesis=investment_thesis,
            bull_case=bull_case,
            bear_case=bear_case,
            catalysts=catalysts,
            risks=risks,
            valuation_summary=valuation_summary,
            cited_report_ids=cited_report_ids,
            cited_event_ids=cited_event_ids,
            cited_run_ids=cited_run_ids,
        )

    def render(self, context: InvestmentMemoContext) -> str:
        env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(enabled_extensions=()),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        template = env.get_template(self.template_name)
        return template.render(memo=context.model_dump(mode="json"))

    def generate(
        self,
        store: KnowledgeStore,
        *,
        asset_id: str,
        company_id: Optional[str] = None,
        generated_at: Optional[datetime] = None,
        persist: bool = False,
        source_trace: Optional[SourceTrace] = None,
    ) -> InvestmentMemo:
        context = self.assemble_context(
            store,
            asset_id=asset_id,
            company_id=company_id,
            generated_at=generated_at,
        )
        rendered = self.render(context)
        memo = InvestmentMemo(
            memo_id=context.memo_id,
            asset_id=context.asset_id,
            company_id=context.company_id,
            memo_version=context.memo_version,
            model_version=context.model_version,
            generated_at=context.generated_at,
            investment_thesis=context.investment_thesis,
            bull_case=context.bull_case,
            bear_case=context.bear_case,
            catalysts=context.catalysts,
            risks=context.risks,
            valuation_summary=context.valuation_summary,
            rendered_markdown=rendered,
            cited_report_ids=context.cited_report_ids,
            cited_event_ids=context.cited_event_ids,
            cited_run_ids=context.cited_run_ids,
            source_trace=source_trace
            or SourceTrace(source_type="investment_memo_agent", source_ref="deterministic"),
        )
        if persist:
            store.add_memo(memo.to_memo_record())
        return memo

    @staticmethod
    def _load_or_build_dossier(
        store: KnowledgeStore,
        *,
        asset_id: str,
        company_id: Optional[str],
    ) -> DossierRecord:
        dossiers = store.get_dossiers(company_id=company_id, asset_id=asset_id, limit=1)
        if dossiers:
            return dossiers[0]
        return store.generate_dossier(company_id=company_id, asset_id=asset_id, persist=False)

    @staticmethod
    def _load_or_generate_report(
        store: KnowledgeStore,
        *,
        asset_id: str,
        company_id: Optional[str],
        generated_at: datetime,
    ) -> dict[str, Any]:
        reports = store.get_research_reports(company_id=company_id, asset_id=asset_id, limit=1)
        if reports:
            return reports[0]
        report = ResearchReportGenerator().generate(
            store,
            asset_id=asset_id,
            company_id=company_id,
            generated_at=generated_at,
            persist=False,
        )
        return report.model_dump(mode="json")

    @staticmethod
    def _bull_case(*, report: dict[str, Any], dossier: DossierRecord, diffs: list[Any]) -> str:
        pos = report.get("executive_summary") or "Evidence quality continues to improve."
        if diffs:
            pos += f" Latest run delta_npv={diffs[0].delta_npv:+.2f}."
        if dossier.latest_valuation_snapshot:
            rnpv = dossier.latest_valuation_snapshot.get("rnpv_millions")
            pos += f" Current rNPV snapshot={rnpv}."
        return str(pos)

    @staticmethod
    def _bear_case(*, report: dict[str, Any], reviews: list[Any]) -> str:
        risk = report.get("risk_factors") or "Execution and regulatory uncertainty remains."
        rejected = sum(1 for r in reviews if getattr(r, "decision", "") == "rejected")
        if rejected:
            risk += f" Recent rejected proposals={rejected}."
        return str(risk)

    @staticmethod
    def _catalysts(events: list[Any]) -> list[str]:
        out: list[str] = []
        for evt in events[:5]:
            out.append(f"{evt.observed_at.date().isoformat()} — {evt.event_type.value}")
        return out

    @staticmethod
    def _risks(*, report: dict[str, Any], reviews: list[Any]) -> list[str]:
        risks: list[str] = []
        if report.get("risk_factors"):
            first = str(report["risk_factors"]).splitlines()[0].strip("- ").strip()
            if first:
                risks.append(first)
        deferred = sum(1 for r in reviews if getattr(r, "decision", "") == "deferred")
        if deferred:
            risks.append(f"{deferred} deferred review decisions remain unresolved.")
        if not risks:
            risks.append("No explicit risk factors available in current records.")
        return risks

    @staticmethod
    def _valuation_summary(*, dossier: DossierRecord, diffs: list[Any]) -> str:
        snapshot = dossier.latest_valuation_snapshot or {}
        rnpv = snapshot.get("rnpv_millions")
        nav_ps = snapshot.get("nav_per_share")
        parts = [f"Snapshot rNPV={rnpv}, NAV/share={nav_ps}."]
        if diffs:
            parts.append(f"Latest valuation diff={diffs[0].delta_npv:+.2f}.")
        return " ".join(parts)

    @staticmethod
    def _memo_id(
        *,
        asset_id: str,
        company_id: Optional[str],
        generated_at: datetime,
        report_ids: list[str],
    ) -> str:
        seed = "|".join(
            [
                asset_id,
                company_id or "",
                generated_at.isoformat(),
                ",".join(sorted(report_ids)),
            ]
        )
        return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))
