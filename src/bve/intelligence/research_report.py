"""
Wave 6D — Research report generator.

Design:
  1) Assemble deterministic context from stored records
  2) Render through a Jinja template
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from pydantic import BaseModel, Field

from bve.intelligence.competitive_landscape_agent import CompetitiveLandscapeAgent
from bve.intelligence.cross_asset_propagation import (
    PropagationCalibrator,
    PropagationDatasetBuilder,
    PropagationGuardrails,
)
from bve.intelligence.knowledge_graph import NodeType
from bve.intelligence.knowledge_layer import DossierRecord, KnowledgeStore, SourceTrace
from bve.intelligence.literature_review_agent import LiteratureReviewAgent


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


_TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "reporting" / "templates"
_TEMPLATE_NAME = "research_report.md.j2"
_REPORT_VERSION = "v1.2"
_MODEL_VERSION = "deterministic-research-report-1.2"


class ResearchReport(BaseModel):
    """Persistable research report artifact."""

    report_id: str
    asset_id: str
    company_id: Optional[str] = None
    report_version: str = _REPORT_VERSION
    model_version: str = _MODEL_VERSION
    generated_at: datetime
    executive_summary: str
    investment_thesis: str
    clinical_evidence: str
    competitive_analysis: str
    financial_model: str
    risk_factors: str
    calibration_metrics: str
    company_sotp_snapshot: Optional[dict[str, Any]] = None
    rendered_markdown: str
    cited_dossier_ids: list[str] = Field(default_factory=list)
    cited_literature_review_ids: list[str] = Field(default_factory=list)
    cited_competitive_landscape_ids: list[str] = Field(default_factory=list)
    cited_signal_ids: list[str] = Field(default_factory=list)
    cited_run_ids: list[str] = Field(default_factory=list)
    cited_event_ids: list[str] = Field(default_factory=list)
    cited_raw_document_ids: list[str] = Field(default_factory=list)
    input_snapshot: dict[str, Any] = Field(default_factory=dict)


class ResearchReportContext(BaseModel):
    """Assembled data context used by the template renderer."""

    report_id: str
    asset_id: str
    company_id: Optional[str]
    report_version: str = _REPORT_VERSION
    model_version: str = _MODEL_VERSION
    generated_at: datetime
    executive_summary: str
    investment_thesis: str
    clinical_evidence: str
    competitive_analysis: str
    financial_model: str
    risk_factors: str
    calibration_metrics: str
    company_sotp_snapshot: Optional[dict[str, Any]] = None
    competitive_entries: list[dict[str, Any]] = Field(default_factory=list)
    cited_dossier_ids: list[str] = Field(default_factory=list)
    cited_literature_review_ids: list[str] = Field(default_factory=list)
    cited_competitive_landscape_ids: list[str] = Field(default_factory=list)
    cited_signal_ids: list[str] = Field(default_factory=list)
    cited_run_ids: list[str] = Field(default_factory=list)
    cited_event_ids: list[str] = Field(default_factory=list)
    cited_raw_document_ids: list[str] = Field(default_factory=list)
    input_snapshot: dict[str, Any] = Field(default_factory=dict)


class ResearchReportGenerator:
    """Deterministic report assembler and Jinja renderer."""

    def __init__(
        self,
        *,
        template_dir: Optional[Path] = None,
        template_name: str = _TEMPLATE_NAME,
        max_competitors: int = 10,
    ) -> None:
        self.template_dir = template_dir or _TEMPLATE_DIR
        self.template_name = template_name
        self.max_competitors = max_competitors

    def assemble_context(
        self,
        store: KnowledgeStore,
        *,
        asset_id: str,
        company_id: Optional[str] = None,
        generated_at: Optional[datetime] = None,
    ) -> ResearchReportContext:
        generated_at = generated_at or _utcnow()
        dossier = self._load_or_build_dossier(store, asset_id=asset_id, company_id=company_id)
        literature = self._load_or_generate_literature(
            store,
            asset_id=asset_id,
            company_id=company_id,
            generated_at=generated_at,
        )
        landscape = self._load_or_generate_landscape(
            store,
            asset_id=asset_id,
            company_id=company_id,
            generated_at=generated_at,
        )
        company_sotp_snapshot = self._load_company_sotp_snapshot(
            store,
            company_id=company_id,
            asset_id=asset_id,
            generated_at=generated_at,
        )
        moa_summary = self._load_moa_summary(store, asset_id=asset_id)
        calibration = self._calibration_metrics(store, asset_id=asset_id)
        latest_diff = dossier.recent_changes[0] if dossier.recent_changes else None
        risk_items = self._risk_items(
            literature=literature,
            landscape=landscape,
            store=store,
            asset_id=asset_id,
        )

        executive_summary = self._executive_summary(
            asset_id=asset_id,
            dossier=dossier,
            latest_diff=latest_diff,
            landscape=landscape,
        )
        investment_thesis = self._investment_thesis(
            moa_summary=moa_summary,
            dossier=dossier,
        )
        clinical_evidence = self._clinical_evidence(literature=literature)
        competitive_analysis = self._competitive_analysis(landscape=landscape)
        financial_model = self._financial_model(
            dossier=dossier,
            latest_diff=latest_diff,
            company_sotp_snapshot=company_sotp_snapshot,
        )
        risk_factors = "\n".join([f"- {item}" for item in risk_items])
        calibration_metrics = self._calibration_text(calibration=calibration)

        cited_dossier_ids = [dossier.id]
        cited_literature_review_ids = [str(literature.get("review_id"))] if literature.get("review_id") else []
        cited_competitive_landscape_ids = [
            str(landscape.get("landscape_id"))
        ] if landscape.get("landscape_id") else []
        cited_signal_ids = sorted(set(literature.get("cited_signal_ids") or []))
        cited_run_ids = sorted({diff.run_id for diff in dossier.recent_changes})
        cited_event_ids = sorted({evt.id for evt in dossier.recent_events})
        cited_raw_document_ids = sorted(set(literature.get("cited_raw_document_ids") or []))
        input_snapshot = self._build_input_snapshot(
            store=store,
            dossier=dossier,
            generated_at=generated_at,
            company_sotp_snapshot=company_sotp_snapshot,
        )

        report_id = self._report_id(
            asset_id=asset_id,
            company_id=company_id,
            generated_at=generated_at,
            cited_dossier_ids=cited_dossier_ids,
            cited_literature_review_ids=cited_literature_review_ids,
            cited_competitive_landscape_ids=cited_competitive_landscape_ids,
        )

        competitive_entries = list(landscape.get("entries") or [])[: self.max_competitors]
        return ResearchReportContext(
            report_id=report_id,
            asset_id=asset_id,
            company_id=company_id,
            report_version=_REPORT_VERSION,
            model_version=_MODEL_VERSION,
            generated_at=generated_at,
            executive_summary=executive_summary,
            investment_thesis=investment_thesis,
            clinical_evidence=clinical_evidence,
            competitive_analysis=competitive_analysis,
            financial_model=financial_model,
            risk_factors=risk_factors,
            calibration_metrics=calibration_metrics,
            company_sotp_snapshot=company_sotp_snapshot,
            competitive_entries=competitive_entries,
            cited_dossier_ids=cited_dossier_ids,
            cited_literature_review_ids=cited_literature_review_ids,
            cited_competitive_landscape_ids=cited_competitive_landscape_ids,
            cited_signal_ids=cited_signal_ids,
            cited_run_ids=cited_run_ids,
            cited_event_ids=cited_event_ids,
            cited_raw_document_ids=cited_raw_document_ids,
            input_snapshot=input_snapshot,
        )

    def render(self, context: ResearchReportContext) -> str:
        env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(enabled_extensions=()),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        template = env.get_template(self.template_name)
        return template.render(report=context.model_dump(mode="json"))

    def generate(
        self,
        store: KnowledgeStore,
        *,
        asset_id: str,
        company_id: Optional[str] = None,
        generated_at: Optional[datetime] = None,
        persist: bool = False,
        source_trace: Optional[SourceTrace] = None,
    ) -> ResearchReport:
        context = self.assemble_context(
            store,
            asset_id=asset_id,
            company_id=company_id,
            generated_at=generated_at,
        )
        rendered_markdown = self.render(context)
        report = ResearchReport(
            report_id=context.report_id,
            asset_id=context.asset_id,
            company_id=context.company_id,
            report_version=context.report_version,
            model_version=context.model_version,
            generated_at=context.generated_at,
            executive_summary=context.executive_summary,
            investment_thesis=context.investment_thesis,
            clinical_evidence=context.clinical_evidence,
            competitive_analysis=context.competitive_analysis,
            financial_model=context.financial_model,
            risk_factors=context.risk_factors,
            calibration_metrics=context.calibration_metrics,
            company_sotp_snapshot=context.company_sotp_snapshot,
            rendered_markdown=rendered_markdown,
            cited_dossier_ids=context.cited_dossier_ids,
            cited_literature_review_ids=context.cited_literature_review_ids,
            cited_competitive_landscape_ids=context.cited_competitive_landscape_ids,
            cited_signal_ids=context.cited_signal_ids,
            cited_run_ids=context.cited_run_ids,
            cited_event_ids=context.cited_event_ids,
            cited_raw_document_ids=context.cited_raw_document_ids,
            input_snapshot=context.input_snapshot,
        )
        if persist:
            store.add_research_report(
                report,
                source_trace=source_trace or SourceTrace(
                    source_type="system",
                    source_ref="research_report_generator",
                ),
            )
        return report

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
    def _load_or_generate_literature(
        store: KnowledgeStore,
        *,
        asset_id: str,
        company_id: Optional[str],
        generated_at: datetime,
    ) -> dict[str, Any]:
        existing = store.get_literature_reviews(company_id=company_id, asset_id=asset_id, limit=1)
        if existing:
            return existing[0]
        generated = LiteratureReviewAgent().generate(
            store,
            asset_id=asset_id,
            company_id=company_id,
            generated_at=generated_at,
        )
        return generated.model_dump(mode="json")

    @staticmethod
    def _load_or_generate_landscape(
        store: KnowledgeStore,
        *,
        asset_id: str,
        company_id: Optional[str],
        generated_at: datetime,
    ) -> dict[str, Any]:
        existing = store.get_competitive_landscapes(company_id=company_id, asset_id=asset_id, limit=1)
        if existing:
            return existing[0]
        generated = CompetitiveLandscapeAgent().generate(
            store,
            asset_id=asset_id,
            company_id=company_id,
            generated_at=generated_at,
        )
        return generated.model_dump(mode="json")

    @staticmethod
    def _load_moa_summary(store: KnowledgeStore, *, asset_id: str) -> dict[str, Any]:
        node = store.find_node_by_external_id(NodeType.ASSET, asset_id)
        if node is None:
            return {}
        props = dict(node.properties or {})
        return dict(props.get("moa_summary") or {})

    @staticmethod
    def _load_company_sotp_snapshot(
        store: KnowledgeStore,
        *,
        company_id: Optional[str],
        asset_id: str,
        generated_at: datetime,
    ) -> Optional[dict[str, Any]]:
        as_of = generated_at.date()
        if company_id:
            snapshot = store.get_company_sotp_snapshot_for_company_id_on_or_before(
                company_id=company_id,
                as_of=as_of,
            )
            if snapshot is not None:
                return snapshot
        node = store.find_node_by_external_id(NodeType.ASSET, asset_id)
        if node is not None:
            props = dict(node.properties or {})
            ticker = props.get("ticker")
            if ticker:
                return store.get_company_sotp_snapshot_for_ticker_on_or_before(
                    ticker=str(ticker),
                    as_of=as_of,
                )
        return None

    @staticmethod
    def _executive_summary(
        *,
        asset_id: str,
        dossier: DossierRecord,
        latest_diff,
        landscape: dict[str, Any],
    ) -> str:
        snapshot = dossier.latest_valuation_snapshot or {}
        rnpv = snapshot.get("rnpv_millions")
        nav_ps = snapshot.get("nav_per_share")
        top_entry = (landscape.get("entries") or [{}])[0]
        top_threat = top_entry.get("drug")
        top_risk = top_entry.get("risk_score")

        pieces = [f"Asset {asset_id} currently tracks rNPV={rnpv} and NAV/share={nav_ps}."]
        if latest_diff is not None:
            pieces.append(f"Latest valuation change delta_npv={latest_diff.delta_npv:+.2f}.")
        if top_threat:
            pieces.append(f"Highest competitive threat: {top_threat} (risk_score={top_risk}).")
        return " ".join(pieces)

    @staticmethod
    def _investment_thesis(*, moa_summary: dict[str, Any], dossier: DossierRecord) -> str:
        target_class = moa_summary.get("target_class", "undetermined")
        novelty = moa_summary.get("novelty_score", "n/a")
        confidence = moa_summary.get("moa_confidence", "n/a")
        assumptions = dossier.current_assumptions or {}
        return (
            f"Mechanistic thesis centers on target_class={target_class}, "
            f"novelty_score={novelty}, moa_confidence={confidence}. "
            f"Current tracked assumptions={len(assumptions)}."
        )

    @staticmethod
    def _clinical_evidence(*, literature: dict[str, Any]) -> str:
        return (
            f"Efficacy: {literature.get('efficacy_summary', 'n/a')} "
            f"Safety: {literature.get('safety_summary', 'n/a')} "
            f"Mechanism: {literature.get('mechanism_summary', 'n/a')} "
            f"Biomarkers: {literature.get('biomarker_summary', 'n/a')} "
            f"Trial outcomes: {literature.get('trial_outcomes_summary', 'n/a')}"
        )

    @staticmethod
    def _competitive_analysis(*, landscape: dict[str, Any]) -> str:
        entries = list(landscape.get("entries") or [])
        if not entries:
            return "No competitive entries were identified from KG relationships."
        top = sorted(entries, key=lambda row: float(row.get("risk_score", 0.0)), reverse=True)[:3]
        lines = []
        for row in top:
            lines.append(
                f"{row.get('drug')} (risk={row.get('risk_score')}, "
                f"mechanism_similarity={row.get('mechanism_similarity')}, "
                f"distance_to_market={row.get('distance_to_market')})"
            )
        return "; ".join(lines)

    @staticmethod
    def _financial_model(
        *,
        dossier: DossierRecord,
        latest_diff,
        company_sotp_snapshot: Optional[dict[str, Any]],
    ) -> str:
        snapshot = dossier.latest_valuation_snapshot or {}
        assumptions = dossier.current_assumptions or {}
        base = (
            f"Latest valuation snapshot: rnpv_millions={snapshot.get('rnpv_millions')}, "
            f"nav_per_share={snapshot.get('nav_per_share')}. "
            f"Tracked assumptions={len(assumptions)}."
        )
        if company_sotp_snapshot is not None:
            base = (
                f"{base} Company SOTP: ticker={company_sotp_snapshot.get('ticker')}, "
                f"ranked_discount={company_sotp_snapshot.get('ranked_sotp_discount')}, "
                f"action_policy={company_sotp_snapshot.get('action_policy')}, "
                f"sotp_equity_value_millions={company_sotp_snapshot.get('sotp_equity_value_millions')}, "
                f"enterprise_value_millions={company_sotp_snapshot.get('enterprise_value_millions')}, "
                f"balance_sheet_snapshot_date={company_sotp_snapshot.get('balance_sheet_snapshot_date')}."
            )
        if latest_diff is None:
            return base
        return (
            f"{base} Most recent run={latest_diff.run_id} changed NPV by "
            f"{latest_diff.delta_npv:+.2f}."
        )

    @staticmethod
    def _risk_items(
        *,
        literature: dict[str, Any],
        landscape: dict[str, Any],
        store: KnowledgeStore,
        asset_id: str,
    ) -> list[str]:
        items: list[str] = []
        for gap in literature.get("knowledge_gaps") or []:
            items.append(f"Evidence gap: {gap}")

        for row in sorted(
            list(landscape.get("entries") or []),
            key=lambda item: float(item.get("risk_score", 0.0)),
            reverse=True,
        )[:3]:
            if float(row.get("risk_score", 0.0)) >= 0.75:
                items.append(
                    f"High competitor threat: {row.get('drug')} "
                    f"(risk={row.get('risk_score')}, distance={row.get('distance_to_market')})"
                )

        deferred = store.get_review_decisions(asset_id=asset_id, decision="deferred", limit=3)
        for dec in deferred:
            items.append(f"Deferred review {dec.id}: {dec.rationale}")

        if not items:
            items.append("No high-priority unresolved risks detected from current records.")
        return items

    @staticmethod
    def _calibration_metrics(store: KnowledgeStore, *, asset_id: str) -> dict[str, Any]:
        scores_row = store._conn.execute(
            "SELECT COUNT(*) AS n_total, SUM(CASE WHEN active = 1 THEN 1 ELSE 0 END) AS n_active "
            "FROM event_scores",
        ).fetchone()
        forecast_row = store._conn.execute(
            "SELECT COUNT(*) AS n_resolved, AVG(outcome_correct) AS accuracy "
            "FROM forecast_records WHERE resolved = 1",
        ).fetchone()
        reviews_row = store._conn.execute(
            "SELECT COUNT(*) AS n_reviews, "
            "SUM(CASE WHEN decision = 'accepted' THEN 1 ELSE 0 END) AS n_accepted "
            "FROM review_decisions WHERE asset_id = ?",
            (asset_id,),
        ).fetchone()
        return {
            "event_scores_total": int(scores_row["n_total"] or 0),
            "event_scores_active": int(scores_row["n_active"] or 0),
            "resolved_forecasts": int(forecast_row["n_resolved"] or 0),
            "forecast_directional_accuracy": round(float(forecast_row["accuracy"]), 3)
            if forecast_row["accuracy"] is not None
            else None,
            "reviews_total": int(reviews_row["n_reviews"] or 0),
            "reviews_accepted": int(reviews_row["n_accepted"] or 0),
        }

    @staticmethod
    def _calibration_text(*, calibration: dict[str, Any]) -> str:
        return (
            f"event_scores_active={calibration['event_scores_active']} / "
            f"{calibration['event_scores_total']}; "
            f"resolved_forecasts={calibration['resolved_forecasts']}; "
            f"forecast_directional_accuracy={calibration['forecast_directional_accuracy']}; "
            f"reviews_accepted={calibration['reviews_accepted']} / {calibration['reviews_total']}."
        )

    @staticmethod
    def _build_input_snapshot(
        *,
        store: KnowledgeStore,
        dossier: DossierRecord,
        generated_at: datetime,
        company_sotp_snapshot: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        valuation_parameters = dict(dossier.current_assumptions or {})

        event_scores = store.list_event_scores(active_only=False)
        event_scores_sorted = sorted(
            event_scores,
            key=lambda row: (
                str(row.get("event_type") or ""),
                str(row.get("trial_phase") or ""),
                str(row.get("endpoint_type") or ""),
            ),
        )

        dataset_builder = PropagationDatasetBuilder()
        calibrator = PropagationCalibrator(guardrails=PropagationGuardrails())
        calibrations = calibrator.calibrate(dataset_builder.build(store))
        propagation_parameters = {
            propagation_type.value: calibration.model_dump(mode="json")
            for propagation_type, calibration in sorted(
                calibrations.items(),
                key=lambda item: item[0].value,
            )
        }

        return {
            "captured_at": generated_at.isoformat(),
            "valuation_parameters": valuation_parameters,
            "event_scores": event_scores_sorted,
            "propagation_parameters": propagation_parameters,
            "company_sotp_snapshot": company_sotp_snapshot,
        }

    @staticmethod
    def _report_id(
        *,
        asset_id: str,
        company_id: Optional[str],
        generated_at: datetime,
        cited_dossier_ids: list[str],
        cited_literature_review_ids: list[str],
        cited_competitive_landscape_ids: list[str],
    ) -> str:
        key = (
            f"research_report|{asset_id}|{company_id or ''}|{generated_at.isoformat()}|"
            f"{_REPORT_VERSION}|{_MODEL_VERSION}|{','.join(cited_dossier_ids)}|"
            f"{','.join(cited_literature_review_ids)}|{','.join(cited_competitive_landscape_ids)}"
        )
        return str(uuid.uuid5(uuid.NAMESPACE_URL, key))
